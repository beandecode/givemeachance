"""Jobs, searches and evaluations in the /api/v1 contract."""

from __future__ import annotations

from flask import Flask, current_app

from app.api import ApiContext, api_route
from app.api_models import (
    JobDescriptionUpdate,
    JobDetail,
    JobListQuery,
    JobSummary,
    ManualJobRequest,
    Page,
    RerunEvaluationRequest,
    SearchRequest,
    Task,
    TriageRequest,
    TriageResult,
)
from core.errors import ApiError
from core.job_service import get_job_detail, list_jobs, set_job_archived, set_job_description
from core.journey_service import build_job_journey
from core.task_service import submit_task
from core.triage_service import triage_job, undo_triage


def _submit(ctx: ApiContext, task_type: str, payload: dict) -> dict:
    return submit_task(
        ctx.conn,
        current_app.extensions["task_runner"],
        task_type=task_type,
        payload=payload,
        owner_user_id=ctx.user_id,
        correlation_id=ctx.correlation_id,
    )


def _detail_or_404(ctx: ApiContext, job_id: int) -> dict:
    detail = get_job_detail(ctx.conn, ctx.user_id, job_id)
    if detail is None:
        raise ApiError(404, 3003, "job not found")
    return {**detail, "journey": build_job_journey(ctx.conn, detail)}


def register_api_jobs_routes(app: Flask) -> None:
    @api_route(
        app,
        "GET",
        "/api/v1/jobs",
        summary="Own jobs with filters",
        tag="jobs",
        query=JobListQuery,
        response=Page[JobSummary],
    )
    def workspace_jobs(ctx: ApiContext, query: JobListQuery):
        return list_jobs(ctx.conn, ctx.user_id, **query.model_dump())

    @api_route(
        app,
        "GET",
        "/api/v1/jobs/<int:job_id>",
        summary="Job with match report, decision and documents",
        tag="jobs",
        response=JobDetail,
    )
    def api_job_detail(ctx: ApiContext, job_id: int):
        return _detail_or_404(ctx, job_id)

    @api_route(
        app,
        "PUT",
        "/api/v1/jobs/<int:job_id>/description",
        summary="Replace a job's text with the full posting (re-evaluate afterwards)",
        tag="jobs",
        body=JobDescriptionUpdate,
        response=JobDetail,
    )
    def api_set_job_description(ctx: ApiContext, job_id: int, body: JobDescriptionUpdate):
        if not set_job_description(ctx.conn, ctx.user_id, job_id, body.description.strip()):
            raise ApiError(404, 3003, "job not found")
        return _detail_or_404(ctx, job_id)

    @api_route(
        app,
        "POST",
        "/api/v1/jobs/<int:job_id>/archive",
        summary="Hide a job from the default list",
        tag="jobs",
        response=JobDetail,
    )
    def api_archive_job(ctx: ApiContext, job_id: int):
        if not set_job_archived(ctx.conn, ctx.user_id, job_id, archived=True):
            raise ApiError(404, 3003, "job not found")
        return _detail_or_404(ctx, job_id)

    @api_route(
        app,
        "DELETE",
        "/api/v1/jobs/<int:job_id>/archive",
        summary="Show an archived job again",
        tag="jobs",
        response=JobDetail,
    )
    def api_unarchive_job(ctx: ApiContext, job_id: int):
        if not set_job_archived(ctx.conn, ctx.user_id, job_id, archived=False):
            raise ApiError(404, 3003, "job not found")
        return _detail_or_404(ctx, job_id)

    @api_route(
        app,
        "PUT",
        "/api/v1/jobs/<int:job_id>/triage",
        summary="Swipe decision: skip, waitlist or accept (accept starts the documents)",
        tag="jobs",
        body=TriageRequest,
        response=TriageResult,
    )
    def api_triage_job(ctx: ApiContext, job_id: int, body: TriageRequest):
        return triage_job(
            ctx.conn,
            current_app.extensions["task_runner"],
            user_id=ctx.user_id,
            job_id=job_id,
            action=body.action,
            generate=body.generate,
            correlation_id=ctx.correlation_id,
            reason=body.reason,
        )

    @api_route(
        app,
        "DELETE",
        "/api/v1/jobs/<int:job_id>/triage",
        summary="Undo a swipe decision (cancels documents that have not started)",
        tag="jobs",
        response=JobDetail,
    )
    def api_undo_triage(ctx: ApiContext, job_id: int):
        undo_triage(ctx.conn, user_id=ctx.user_id, job_id=job_id)
        return _detail_or_404(ctx, job_id)

    @api_route(
        app,
        "POST",
        "/api/v1/searches",
        summary="Search the job board with saved preferences (task)",
        tag="jobs",
        body=SearchRequest,
        response=Task,
        status=202,
    )
    def api_start_search(ctx: ApiContext, body: SearchRequest):
        return _submit(ctx, "manual_search", body.model_dump())

    @api_route(
        app,
        "POST",
        "/api/v1/jobs/manual",
        summary="Add and evaluate a pasted job description (task)",
        tag="jobs",
        body=ManualJobRequest,
        response=Task,
        status=202,
    )
    def api_add_manual_job(ctx: ApiContext, body: ManualJobRequest):
        return _submit(ctx, "manual_jd_match", body.model_dump())

    @api_route(
        app,
        "POST",
        "/api/v1/evaluations/rerun",
        summary="Re-evaluate own jobs with the latest profile (task)",
        tag="jobs",
        body=RerunEvaluationRequest,
        response=Task,
        status=202,
    )
    def api_rerun_evaluations(ctx: ApiContext, body: RerunEvaluationRequest):
        return _submit(ctx, "re_evaluate", body.model_dump())
