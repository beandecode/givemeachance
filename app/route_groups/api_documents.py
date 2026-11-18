"""Documents, applications and tasks in the /api/v1 contract."""

from __future__ import annotations

import json
from typing import Any

from flask import Flask, Response, current_app

from app.api import ApiContext, api_route
from app.api_models import (
    ApplicationCard,
    ApplicationState,
    ApplicationUpdate,
    Document,
    DocumentEdit,
    ExportQuery,
    GenerateDocumentRequest,
    JobDocumentVersions,
    Task,
    TaskListQuery,
)
from app.api_models import Page as PageModel
from core.async_tasks import deserialize_task_result, get_async_task, request_cancel_task, serialize_async_task
from core.db.connection import begin_write
from core.errors import ApiError
from core.export import MEDIA_TYPES, export_document, export_filename
from core.journey_service import valid_follow_up
from core.repositories.applications import set_follow_up, upsert_application_status
from core.repositories.decisions import mark_match_viewed, upsert_generation_decision
from core.repositories.documents import (
    DOCUMENT_TABLES,
    get_owned_document,
    insert_document_version,
    list_document_versions,
)
from core.task_service import submit_task
from core.workspace_service import list_tasks


def _owned_job(ctx: ApiContext, job_id: int):
    job = ctx.conn.execute(
        "SELECT id, owner_user_id FROM jobs WHERE id = ? AND owner_user_id = ?", (job_id, ctx.user_id)
    ).fetchone()
    if job is None:
        raise ApiError(404, 3003, "job not found")
    return job


def _document(kind: str, row) -> dict[str, Any]:
    try:
        evidence_map = json.loads(str(row["evidence_map_json"] or "{}"))
    except json.JSONDecodeError:
        evidence_map = {}
    return {
        **{key: row[key] for key in row.keys() if key != "evidence_map_json"},
        "kind": kind,
        "evidence_map": evidence_map,
    }


def _check_kind(kind: str) -> None:
    if kind not in DOCUMENT_TABLES:
        raise ApiError(404, 3003, "unknown document kind")


def _application_state(ctx: ApiContext, job_id: int) -> dict[str, Any]:
    row = ctx.conn.execute(
        """SELECT j.id AS job_id, COALESCE(a.status, 'draft') AS status, COALESCE(a.status_note, '') AS note,
                  a.updated_at, a.follow_up_at
           FROM jobs j LEFT JOIN applications a ON a.job_id = j.id WHERE j.id = ?""",
        (job_id,),
    ).fetchone()
    return dict(row)


def _owned_task(ctx: ApiContext, task_id: str):
    row = get_async_task(ctx.conn, task_id)
    if row is None or int(row["owner_user_id"]) != ctx.user_id:
        raise ApiError(404, 3003, "task not found")
    return row


def register_api_documents_routes(app: Flask) -> None:
    @api_route(
        app,
        "POST",
        "/api/v1/jobs/<int:job_id>/documents",
        tag="documents",
        status=202,
        summary="Record the decision and generate a resume or cover letter (task)",
        body=GenerateDocumentRequest,
        response=Task,
    )
    def api_generate_document(ctx: ApiContext, job_id: int, body: GenerateDocumentRequest):
        _owned_job(ctx, job_id)
        if ctx.conn.execute("SELECT 1 FROM evaluations WHERE job_id = ?", (job_id,)).fetchone() is None:
            raise ApiError(409, 3004, "evaluate the job before generating documents")
        # Calling this endpoint is the user's explicit decision after viewing the match.
        mark_match_viewed(ctx.conn, job_id, decided_by="api")
        resume = body.kind == "resume"
        upsert_generation_decision(
            ctx.conn,
            job_id=job_id,
            generate_resume=True if resume else None,
            generate_cover_letter=None if resume else True,
            decided_by="api",
        )
        payload = {"job_id": job_id, "style": body.style} if resume else {"job_id": job_id, "tone": body.tone}
        return submit_task(
            ctx.conn,
            current_app.extensions["task_runner"],
            task_type="generate_resume" if resume else "generate_cover_letter",
            payload=payload,
            owner_user_id=ctx.user_id,
            correlation_id=ctx.correlation_id,
        )

    @api_route(
        app,
        "GET",
        "/api/v1/jobs/<int:job_id>/documents",
        tag="documents",
        summary="All versions of a job's documents, newest first",
        response=JobDocumentVersions,
    )
    def api_list_documents(ctx: ApiContext, job_id: int):
        _owned_job(ctx, job_id)
        return {kind: [dict(row) for row in list_document_versions(ctx.conn, kind, job_id)] for kind in DOCUMENT_TABLES}

    @api_route(
        app,
        "GET",
        "/api/v1/documents/<kind>/<int:document_id>",
        tag="documents",
        summary="One document version with its Markdown",
        response=Document,
    )
    def api_get_document(ctx: ApiContext, kind: str, document_id: int):
        _check_kind(kind)
        row = get_owned_document(ctx.conn, kind, document_id, ctx.user_id)
        if row is None:
            raise ApiError(404, 3003, "document not found")
        return _document(kind, row)

    @api_route(
        app,
        "PUT",
        "/api/v1/documents/<kind>/<int:document_id>",
        tag="documents",
        summary="Save an edited copy as a new version (the original is kept)",
        body=DocumentEdit,
        response=Document,
        status=201,
    )
    def api_edit_document(ctx: ApiContext, kind: str, document_id: int, body: DocumentEdit):
        _check_kind(kind)
        begin_write(ctx.conn)
        row = get_owned_document(ctx.conn, kind, document_id, ctx.user_id)
        if row is None:
            raise ApiError(404, 3003, "document not found")
        saved = insert_document_version(
            ctx.conn,
            kind,
            job_id=int(row["job_id"]),
            content_md=body.content_md,
            source_profile_id=row["source_profile_id"],
            evidence_map_json=row["evidence_map_json"],
            origin="edited",
        )
        return _document(kind, saved)

    @api_route(
        app,
        "GET",
        "/api/v1/applications",
        tag="applications",
        summary="Every non-archived job with its application status (kanban)",
        response=list[ApplicationCard],
    )
    def api_list_applications(ctx: ApiContext):
        rows = ctx.conn.execute(
            """SELECT j.id AS job_id, j.title, j.company, j.location, e.match_score,
                      COALESCE(a.status, 'draft') AS status, COALESCE(a.status_note, '') AS note, a.updated_at,
                      a.follow_up_at,
                      EXISTS(SELECT 1 FROM generated_resumes r WHERE r.job_id = j.id)
                        OR EXISTS(SELECT 1 FROM cover_letters c WHERE c.job_id = j.id) AS has_documents
               FROM jobs j
               LEFT JOIN evaluations e ON e.job_id = j.id
               LEFT JOIN applications a ON a.job_id = j.id
               WHERE j.owner_user_id = ? AND j.archived_at IS NULL
               ORDER BY COALESCE(a.updated_at, j.created_at) DESC
               LIMIT 500""",
            (ctx.user_id,),
        ).fetchall()
        return [{**dict(row), "has_documents": bool(row["has_documents"])} for row in rows]

    @api_route(
        app,
        "PATCH",
        "/api/v1/jobs/<int:job_id>/application",
        tag="applications",
        summary="Update application status and/or note",
        body=ApplicationUpdate,
        response=ApplicationState,
    )
    def api_update_application(ctx: ApiContext, job_id: int, body: ApplicationUpdate):
        _owned_job(ctx, job_id)
        changes_follow_up = "follow_up_at" in body.model_fields_set
        if body.status is None and body.note is None and not changes_follow_up:
            raise ApiError(400, 2003, "provide status, note or follow_up_at")
        current = _application_state(ctx, job_id)
        if body.status is not None or body.note is not None:
            upsert_application_status(
                ctx.conn,
                job_id,
                body.status if body.status is not None else current["status"],
                body.note if body.note is not None else current["note"],
            )
        if changes_follow_up:
            try:
                follow_up_at = valid_follow_up(body.follow_up_at)
            except ValueError:
                raise ApiError(400, 2003, "follow_up_at must be a real date (YYYY-MM-DD)") from None
            set_follow_up(ctx.conn, job_id, follow_up_at)
        return _application_state(ctx, job_id)

    @api_route(
        app,
        "GET",
        "/api/v1/tasks",
        tag="tasks",
        summary="Own task history, newest first",
        query=TaskListQuery,
        response=PageModel[Task],
    )
    def workspace_tasks(ctx: ApiContext, query: TaskListQuery):
        return list_tasks(ctx.conn, ctx.user_id, limit=query.limit, offset=query.offset, active=query.active)

    @api_route(app, "GET", "/api/v1/tasks/<task_id>", tag="tasks", summary="Task state and progress", response=Task)
    def api_get_task(ctx: ApiContext, task_id: str):
        return serialize_async_task(_owned_task(ctx, task_id))

    @api_route(
        app,
        "POST",
        "/api/v1/tasks/<task_id>/cancel",
        tag="tasks",
        summary="Cancel a queued task or ask a running one to stop",
        response=Task,
    )
    def api_cancel_task(ctx: ApiContext, task_id: str):
        _owned_task(ctx, task_id)
        row = request_cancel_task(ctx.conn, task_id)
        assert row is not None
        return serialize_async_task(row)

    @api_route(
        app,
        "GET",
        "/api/v1/tasks/<task_id>/result",
        tag="tasks",
        summary="Result of a succeeded task",
        response=dict[str, Any],
    )
    def api_task_result(ctx: ApiContext, task_id: str):
        row = _owned_task(ctx, task_id)
        if str(row["state"]) != "succeeded":
            raise ApiError(409, 3004, f"task is {row['state']}, not succeeded")
        return deserialize_task_result(row)

    @api_route(
        app,
        "GET",
        "/api/v1/documents/<kind>/<int:document_id>/export",
        tag="documents",
        summary="Download a document version as PDF or DOCX",
        query=ExportQuery,
        raw_response=tuple(MEDIA_TYPES.values()),
    )
    def api_export_document(ctx: ApiContext, kind: str, document_id: int, query: ExportQuery):
        _check_kind(kind)
        row = get_owned_document(ctx.conn, kind, document_id, ctx.user_id)
        if row is None:
            raise ApiError(404, 3003, "document not found")
        job = ctx.conn.execute("SELECT title, company FROM jobs WHERE id = ?", (row["job_id"],)).fetchone()
        label = "resume" if kind == "resume" else "cover-letter"
        title = f"{job['title']} at {job['company']} ({label.replace('-', ' ')} v{row['version']})"
        content = export_document(str(row["content_md"]), title, query.format)
        filename = export_filename(job["company"], job["title"], label, f"v{row['version']}", extension=query.format)
        return Response(
            content,
            mimetype=MEDIA_TYPES[query.format],
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
