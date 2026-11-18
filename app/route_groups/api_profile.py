"""Session, app configuration and Master Profile endpoints of the /api/v1 contract."""

from __future__ import annotations

import json

from flask import Flask, Response, current_app, request, session

from app.api import ApiContext, api_route
from app.api_models import (
    AppConfig,
    Profile,
    ProfileEdit,
    ProfileReview,
    ProfileSupplementRequest,
    ProfileSynthesisRequest,
    ProfileVersion,
    Session,
    SignIn,
    SignUp,
    Task,
)
from core.db.connection import begin_write
from core.demo import (
    DEMO_READ_ONLY_MESSAGE,
    SAMPLE_ONLY_MESSAGE,
    SAMPLE_RESUME_DIR,
    SAMPLE_RESUMES,
    demo_live_enabled,
    demo_mode_enabled,
    sample_resume_inputs,
)
from core.errors import ApiError
from core.guest_service import client_key, create_guest, is_guest
from core.login_throttle import clear_failures, is_locked, record_failure
from core.profile_input_service import (
    ALLOWED_UPLOAD_TYPES,
    MAX_FILE_SIZE,
    MAX_TOTAL_SIZE,
    ProfileInputError,
    build_profile_synthesis_inputs,
    validate_profile_synthesis_inputs,
)
from core.repositories.profiles import (
    get_latest_candidate_profile,
    insert_candidate_profile,
    list_profile_versions,
    update_candidate_profile_review,
)
from core.request_context import is_admin_user, registration_open
from core.task_service import submit_task
from core.users import authenticate_user, create_user
from core.workspace_service import profile_resource

LOCKED_MESSAGE = "too many failed sign-in attempts; try again in 15 minutes"
INVALID_MESSAGE = "invalid username or password"
REGISTRATION_CLOSED_MESSAGE = "registration is closed; ask the owner for an account"


def _start_session(user_row) -> None:
    """New session on every sign-in, so a cookie obtained before login is worthless afterwards."""
    session.clear()
    session.permanent = True
    session["user_id"] = int(user_row["id"])


def _sign_in(conn, username: str, password: str):
    """Return (user_row, None, 200) or (None, error message, HTTP status)."""
    if is_locked(conn, username):
        return None, LOCKED_MESSAGE, 429
    user_row = authenticate_user(conn, username=username, password=password)
    if user_row is None:
        record_failure(conn, username)
        return None, INVALID_MESSAGE, 401
    clear_failures(conn, username)
    return user_row, None, 200


# Sign-in/out and sign-up must work without a session; the write-login guard skips these endpoints.
SESSION_ENDPOINTS = {"api_create_session", "api_delete_session", "api_create_account"}


def _session_payload(user) -> dict:
    if user is None:
        return {"user": None}
    return {"user": {"id": int(user["id"]), "username": str(user["username"]), "is_admin": is_admin_user(user)}}


def _submit(ctx: ApiContext, task_type: str, payload: dict) -> dict:
    return submit_task(
        ctx.conn,
        current_app.extensions["task_runner"],
        task_type=task_type,
        payload=payload,
        owner_user_id=ctx.user_id,
        correlation_id=ctx.correlation_id,
    )


def register_api_profile_routes(app: Flask) -> None:
    @api_route(
        app,
        "GET",
        "/api/v1/session",
        tag="session",
        auth=False,
        summary="Who is signed in (user is null when nobody is)",
        response=Session,
    )
    def api_get_session(ctx: ApiContext):
        return _session_payload(ctx.user)

    @api_route(
        app,
        "POST",
        "/api/v1/session",
        tag="session",
        auth=False,
        summary="Sign in (429 after repeated failures)",
        body=SignIn,
        response=Session,
    )
    def api_create_session(ctx: ApiContext, body: SignIn):
        user, error, status = _sign_in(ctx.conn, body.username.strip(), body.password)
        if user is None:
            ctx.conn.commit()  # keep the recorded failure: the error below rolls the request's transaction back
            raise ApiError(status, 1001 if status == 401 else 1005, error or "sign-in failed")
        _start_session(user)
        return _session_payload(user)

    @api_route(
        app,
        "POST",
        "/api/v1/account",
        tag="session",
        auth=False,
        status=201,
        summary="Create an account and sign in (403 unless REGISTRATION_MODE=open)",
        body=SignUp,
        response=Session,
    )
    def api_create_account(ctx: ApiContext, body: SignUp):
        if not registration_open():
            raise ApiError(403, 1003, REGISTRATION_CLOSED_MESSAGE)
        try:
            user = create_user(ctx.conn, username=body.username, password=body.password)
        except ValueError as error:
            if "already exists" in str(error) or "reserved" in str(error):
                raise ApiError(409, 3004, "that username isn't available") from error
            raise ApiError(400, 2001, str(error)) from error
        _start_session(user)
        return _session_payload(user)

    @api_route(
        app,
        "POST",
        "/api/v1/demo/guest",
        tag="session",
        auth=False,
        status=201,
        summary="Live demo only: start a guest workspace with the sample profile (deleted after 24 hours)",
        response=Session,
    )
    def api_start_guest(ctx: ApiContext):
        if not demo_live_enabled():
            raise ApiError(403, 1004, DEMO_READ_ONLY_MESSAGE)
        if is_guest(ctx.user):
            return _session_payload(ctx.user)
        # remote_addr is the visitor's address when TRUSTED_PROXY_HOPS matches the proxies in front (ProxyFix).
        guest = create_guest(ctx.conn, client_key(str(current_app.secret_key), request.remote_addr))
        _start_session(guest)
        return _session_payload(guest)

    @api_route(app, "DELETE", "/api/v1/session", tag="session", auth=False, summary="Sign out", response=Session)
    def api_delete_session(ctx: ApiContext):
        session.clear()
        return {"user": None}

    @api_route(
        app,
        "GET",
        "/api/v1/config",
        tag="session",
        auth=False,
        summary="Public app configuration for the client",
        response=AppConfig,
    )
    def api_config(ctx: ApiContext):
        guest = is_guest(ctx.user)
        return {
            "registration_open": registration_open() and not demo_mode_enabled(),
            "demo_mode": demo_mode_enabled() and not guest,
            "demo_live": demo_live_enabled(),
            "guest": guest,
            "llm_provider": "gemini" if ctx.settings.llm.provider == "gemini_api" else "mock",
            "job_source": ctx.settings.data_sources.primary,
            "search_results_per_run": ctx.settings.pipeline.daily_limit,
        }

    @api_route(
        app,
        "GET",
        "/api/v1/demo/sample-resumes/<kind>",
        tag="session",
        auth=False,
        summary="Open the demo's sample résumé as text, PDF, Word or image (demo only)",
        raw_response=tuple(mime for _, mime in SAMPLE_RESUMES.values()),
    )
    def api_sample_resume(ctx: ApiContext, kind: str):
        if not demo_mode_enabled() or kind not in SAMPLE_RESUMES:
            raise ApiError(404, 3003, "sample résumé not found")
        name, mime_type = SAMPLE_RESUMES[kind]
        data = (SAMPLE_RESUME_DIR / name).read_bytes()
        disposition = "inline" if kind in {"text", "pdf", "image"} else "attachment"
        return Response(data, mimetype=mime_type, headers={"Content-Disposition": f'{disposition}; filename="{name}"'})

    @api_route(
        app,
        "GET",
        "/api/v1/profile/versions",
        tag="profile",
        summary="All Master Profile versions, newest first",
        response=list[ProfileVersion],
    )
    def api_profile_versions(ctx: ApiContext):
        return [dict(row) for row in list_profile_versions(ctx.conn, ctx.user_id)]

    @api_route(
        app,
        "POST",
        "/api/v1/profile/<int:profile_id>/review",
        tag="profile",
        summary="Approve a profile version or mark it as needing changes",
        body=ProfileReview,
        response=Profile,
    )
    def api_review_profile(ctx: ApiContext, profile_id: int, body: ProfileReview):
        row = update_candidate_profile_review(
            ctx.conn,
            profile_id=profile_id,
            user_id=ctx.user_id,
            review_status=body.review_status,
            review_note=body.review_note,
        )
        if row is None:
            raise ApiError(404, 3003, "profile not found")
        return profile_resource(row)

    @api_route(
        app,
        "PATCH",
        "/api/v1/profile",
        tag="profile",
        status=201,
        body=ProfileEdit,
        response=Profile,
        summary="Save the user's own edit as a new, approved profile version",
    )
    def api_edit_profile(ctx: ApiContext, body: ProfileEdit):
        begin_write(ctx.conn)
        latest = get_latest_candidate_profile(ctx.conn, user_id=ctx.user_id)
        source = {"origin": "user_edit", "edited_from_profile_id": int(latest["id"]) if latest is not None else None}
        row = insert_candidate_profile(
            ctx.conn,
            source_bundle_json=json.dumps(source),
            master_profile_json=json.dumps(body.master_profile, ensure_ascii=False),
            model_name="user_edit",
            user_id=ctx.user_id,
        )
        # The owner wrote this version, so it counts as reviewed.
        reviewed = update_candidate_profile_review(
            ctx.conn,
            profile_id=int(row["id"]),
            user_id=ctx.user_id,
            review_status="approved",
            review_note="edited by the owner",
        )
        return profile_resource(reviewed)

    @api_route(
        app,
        "POST",
        "/api/v1/profile/synthesize",
        tag="profile",
        status=202,
        summary="Build a new profile version from resume text, details and files (task)",
        body=ProfileSynthesisRequest,
        response=Task,
    )
    def api_synthesize_profile(ctx: ApiContext, body: ProfileSynthesisRequest):
        if is_guest(ctx.user):
            if body.sample is None:
                raise ApiError(403, 1004, SAMPLE_ONLY_MESSAGE)
            input_bundle, attachments = sample_resume_inputs(body.sample)
            return _submit(ctx, "synthesize_profile", {"input_bundle": input_bundle, "attachments": attachments})
        if body.sample is not None:
            raise ApiError(400, 2002, "sample résumés are only available in the live demo")
        try:
            # Reuses the size/type/base64 checks of the legacy JSON route on the same request body.
            input_bundle, attachments = build_profile_synthesis_inputs(
                request,
                allowed_upload_types=ALLOWED_UPLOAD_TYPES,
                max_file_size=MAX_FILE_SIZE,
                max_total_size=MAX_TOTAL_SIZE,
            )
            validate_profile_synthesis_inputs(input_bundle, attachments)
        except ProfileInputError as exc:
            raise ApiError(exc.status_code, 2006 if exc.status_code == 413 else 2002, exc.message) from exc
        return _submit(ctx, "synthesize_profile", {"input_bundle": input_bundle, "attachments": attachments})

    @api_route(
        app,
        "POST",
        "/api/v1/profile/supplement",
        tag="profile",
        status=202,
        summary="Answer missing-information questions into a new profile version (task)",
        body=ProfileSupplementRequest,
        response=Task,
    )
    def api_supplement_profile(ctx: ApiContext, body: ProfileSupplementRequest):
        return _submit(ctx, "supplement_profile", body.model_dump())
