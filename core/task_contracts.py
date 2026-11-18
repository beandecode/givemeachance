"""Task payload validation independent of HTTP, workers and UI controls."""

from typing import Literal

from pydantic import BaseModel, Field, ValidationError


class GenerationPayload(BaseModel):
    job_id: int = Field(gt=0)
    profile_id: int | None = Field(default=None, gt=0)
    style: str = Field(default="ats", min_length=1, max_length=100)
    tone: str = Field(default="formal", min_length=1, max_length=100)
    decided_by: str = Field(default="task-runner", max_length=100)


class ReadinessOverride(BaseModel):
    force_when_high_missing: bool = False


class SearchPayload(ReadinessOverride):
    fetch_limit: int | None = Field(default=None, ge=1, le=500)
    score_limit: int | None = Field(default=None, ge=0, le=500)


class ReEvaluationPayload(ReadinessOverride):
    scope: Literal["all", "recent_days", "low_confidence", "high_risk", "unscored"] = "all"
    days: int = Field(default=30, ge=1, le=365)
    limit: int = Field(default=100, ge=1, le=500)
    job_ids: list[int] = Field(default_factory=list, max_length=500)
    decided_by: str = Field(default="task-runner", max_length=100)


class ManualJobPayload(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=100000)
    company: str = Field(default="Unknown Company", max_length=500)
    location: str = Field(default="unknown", max_length=500)
    url: str = Field(default="manual://pasted-jd", max_length=4000)
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)


class ProfileSynthesisPayload(BaseModel):
    input_bundle: dict
    attachments: list[dict] = Field(default_factory=list, max_length=10)


class ProfileSupplementPayload(BaseModel):
    profile_id: int | None = Field(default=None, gt=0)
    selected_fields: list[str] = Field(min_length=1, max_length=50)
    answers: dict[str, str] = Field(default_factory=dict)
    additional_context: str = Field(default="", max_length=20000)


TASK_PAYLOAD_SCHEMAS = {
    "generate_resume": GenerationPayload,
    "generate_cover_letter": GenerationPayload,
    "manual_search": SearchPayload,
    "re_evaluate": ReEvaluationPayload,
    "manual_jd_match": ManualJobPayload,
    "synthesize_profile": ProfileSynthesisPayload,
    "supplement_profile": ProfileSupplementPayload,
}


def validate_task_payload(task_type, payload):
    try:
        result = TASK_PAYLOAD_SCHEMAS[task_type].model_validate(payload).model_dump()
    except ValidationError as exc:
        raise ValueError("; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())) from exc
    if task_type == "manual_jd_match":
        if not result["title"].strip() or not result["description"].strip():
            raise ValueError("title and description are required")
        if (
            result["salary_min"] is not None
            and result["salary_max"] is not None
            and result["salary_min"] > result["salary_max"]
        ):
            raise ValueError("salary_min cannot be greater than salary_max")
    return result
