"""Request and response models of the /api/v1 contract (exported to docs/openapi.json)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from core.schemas import JobSearchConfig


class PageQuery(BaseModel):
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0, le=1_000_000)


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class Readiness(BaseModel):
    """Whether the latest Master Profile passes the search gate."""

    allowed: bool
    profile_id: int | None = None
    profile_version: int | None = None
    review_status: str | None = None
    completeness_score: float = 0
    high_priority_missing_count: int = 0
    blocking_reasons: list[str] = []
    suggested_actions: list[str] = []
    checked_at: str


class UsageItem(BaseModel):
    provider: str
    usage_date: str
    limit: int
    used: int
    remaining: int
    percent_used: int
    subject: str | None = None


class OverviewCounts(BaseModel):
    jobs: int
    evaluated: int
    applications: int


class Overview(BaseModel):
    counts: OverviewCounts
    readiness: Readiness
    usage: list[UsageItem]


class Profile(BaseModel):
    id: int
    profile_version: int
    model_name: str
    created_at: str
    review_status: str
    review_note: str = ""
    reviewed_at_utc: str | None = None
    master_profile: dict[str, Any] | None = Field(None, description="Free-form Master Profile JSON")


class ProfileSnapshot(BaseModel):
    profile: Profile | None
    readiness: Readiness


ApplicationStatus = Literal["draft", "ready", "submitted", "interview", "offer", "hired", "rejected", "withdrawn"]


TriageAction = Literal["skipped", "waitlisted", "accepted"]
TriageFilter = Literal["pending", "skipped", "waitlisted", "accepted"]


class JobListQuery(PageQuery):
    status: ApplicationStatus | None = None
    min_score: int | None = Field(None, ge=0, le=100)
    q: str | None = Field(None, max_length=100, description="Matches title or company")
    include_archived: bool = False
    triage: TriageFilter | None = Field(None, description="pending = no swipe decision yet (the Discover deck)")
    scored: bool | None = Field(None, description="false = jobs that have no match score yet, true = scored jobs")
    sort: Literal["newest", "score"] = "newest"


class JourneyStep(BaseModel):
    key: str
    status: Literal["done", "current", "todo"]
    reason_code: str | None = Field(None, description="Stable code for what is missing; the web app maps it to copy")
    cta_label: str
    cta_route: str


class JourneyCounts(BaseModel):
    jobs: int
    scored: int
    deck: int = Field(description="Unscored excluded: pending jobs at or above the deck score threshold")
    pending: int = Field(description="Scored jobs with no swipe decision yet")
    accepted: int
    documents: int
    applied: int


class Journey(BaseModel):
    """Where the user is in setup: profile, search settings, jobs, picks, a document and a first application."""

    completed: bool
    skipped: bool = Field(description="The user chose to hide the guide")
    current: str | None
    steps: list[JourneyStep]
    counts: JourneyCounts
    discover: Literal["has_cards", "no_jobs", "none_scored", "below_threshold", "all_decided"] = Field(
        description="Why the Discover deck is empty, or has_cards"
    )


class JourneyUpdate(BaseModel):
    skipped: bool


class JobJourney(BaseModel):
    """Steps for one job: score, write, review, applied, follow up."""

    current: str | None
    steps: list[JourneyStep]
    warning_count: int
    follow_up_at: str | None
    follow_up_overdue: bool


class JobSummary(BaseModel):
    id: int
    title: str
    company: str
    location: str
    source: str
    url: str
    posted_date: str
    created_at: str
    salary_min: int | None = None
    salary_max: int | None = None
    relevance: int | None = Field(
        None, description="Cheap 0-100 fit from title and skills; set on jobs found by a search"
    )
    match_score: int | None = None
    years_asked_min: int | None = Field(
        None,
        description="Years of experience the posting asks for (highest stated minimum), read from its text; "
        "null when it states none. Separate from the match score",
    )
    years_asked_max: int | None = Field(
        None, description='Upper end when the posting gives a range ("3 to 5 years"), else null'
    )
    recommendation_level: str | None = None
    confidence: str | None = None
    source_profile_id: int | None = None
    source_profile_version: int | None = None
    application_status: ApplicationStatus
    application_note: str = ""
    archived_at: str | None = None
    triage: TriageAction | None = None
    triage_generate: Literal["resume", "resume_and_cover_letter"] | None = None
    has_resume: bool = False
    has_cover_letter: bool = False


class MatchReport(BaseModel):
    total_score: int
    match_score: int
    dimension_scores: dict[str, int]
    match_reasons: list[str]
    strengths: list[str]
    gaps: list[str]
    risk_flags: list[str]
    recommendation_level: str
    confidence: str
    missing_information: list[str]
    fit_reason: str
    should_apply: bool
    model_name: str
    created_at: str
    source_profile_id: int | None
    source_profile_version: int | None


class GenerationDecision(BaseModel):
    viewed_match_at: str | None
    generate_resume: bool
    generate_cover_letter: bool


DocumentOrigin = Literal["generated", "edited"]


class DocumentSummary(BaseModel):
    id: int
    version: int
    created_at: str
    source_profile_id: int | None
    origin: DocumentOrigin
    version_count: int


class JobDocuments(BaseModel):
    resume: DocumentSummary | None
    cover_letter: DocumentSummary | None


class JobDetail(JobSummary):
    description: str
    description_is_snippet: bool = Field(
        description="True when the text is only the short preview a job board search returns"
    )
    match: MatchReport | None
    match_uses_latest_profile: bool = Field(
        description="False means the match predates the latest profile: re-evaluate"
    )
    decision: GenerationDecision | None
    documents: JobDocuments
    application_updated_at: str | None
    follow_up_at: str | None
    journey: JobJourney


class JobDescriptionUpdate(BaseModel):
    description: str = Field(min_length=200, max_length=20000, description="The whole job posting")


class SearchRequest(BaseModel):
    force_when_high_missing: bool = False
    fetch_limit: int | None = Field(
        None,
        ge=1,
        le=500,
        description="Most new jobs to add; null or above the server cap means the cap (`search_results_per_run`)",
    )
    score_limit: int | None = Field(
        None,
        ge=0,
        le=500,
        description="Score only the first N new jobs; 0 fetches without scoring; null scores all of them",
    )


class ManualJobRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=20000)
    company: str = Field("", max_length=200)
    location: str = Field("", max_length=200)
    url: str = Field("", max_length=2000)
    salary_min: int | None = Field(None, ge=0)
    salary_max: int | None = Field(None, ge=0)


class RerunEvaluationRequest(BaseModel):
    scope: Literal["all", "recent_days", "low_confidence", "high_risk", "unscored"] = "all"
    days: int = Field(30, ge=1, le=365)
    limit: int = Field(100, ge=1, le=500)
    job_ids: list[int] = Field(default_factory=list, max_length=500)
    force_when_high_missing: bool = False


TaskState = Literal["queued", "running", "succeeded", "failed", "cancelled", "expired"]


class Task(BaseModel):
    task_id: str
    task_type: str
    owner_user_id: int
    state: TaskState
    correlation_id: str
    created_at_utc: str | None = None
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    progress_percent: int
    progress_stage: str
    error_code: int | None = None
    error_message_safe: str | None = None
    result_ref: str | None = None
    cancel_requested: bool
    job_id: int | None = Field(None, description="Job the task works on (document generation), else null")


class SearchPreferences(BaseModel):
    config: JobSearchConfig
    source: Literal["user", "default", "suggested"]


DocumentKind = Literal["resume", "cover_letter"]


class GenerateDocumentRequest(BaseModel):
    kind: DocumentKind
    style: str = Field("ats", max_length=40, description="Resume style hint")
    tone: str = Field("formal", max_length=40, description="Cover letter tone hint")


SkipReason = Literal["too_senior", "too_junior", "wrong_field", "location", "pay", "other"]


class TriageRequest(BaseModel):
    action: TriageAction
    generate: Literal["resume", "resume_and_cover_letter"] | None = Field(
        None, description="With action accepted: which documents to write (default resume)"
    )
    reason: SkipReason | None = Field(
        None, description="With action skipped: why (optional); repeated reasons become search suggestions"
    )


class SearchSuggestion(BaseModel):
    kind: Literal["remove_level", "exclude_word"]
    value: str = Field(description="The level to stop searching (remove_level) or the title word to exclude")
    count: int = Field(description="How many of your skips back this suggestion")


class TriageResult(BaseModel):
    job_id: int
    action: TriageAction
    generate: Literal["resume", "resume_and_cover_letter"] | None
    tasks: list[Task]
    queued_for_later: bool = Field(description="True when the task limit was reached; start the rest later")


class DocumentVersion(BaseModel):
    id: int
    job_id: int
    version: int
    source_profile_id: int | None
    created_at: str
    origin: DocumentOrigin
    length: int


class JobDocumentVersions(BaseModel):
    resume: list[DocumentVersion]
    cover_letter: list[DocumentVersion]


class Document(BaseModel):
    id: int
    kind: DocumentKind
    job_id: int
    version: int
    content_md: str
    evidence_map: dict[str, Any]
    source_profile_id: int | None
    created_at: str
    origin: DocumentOrigin


class DocumentEdit(BaseModel):
    content_md: str = Field(min_length=1, max_length=50_000)


class ApplicationCard(BaseModel):
    job_id: int
    title: str
    company: str
    location: str
    match_score: int | None
    status: ApplicationStatus
    note: str
    updated_at: str | None
    has_documents: bool
    follow_up_at: str | None


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus | None = None
    note: str | None = Field(None, max_length=2000)
    follow_up_at: str | None = Field(
        None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="YYYY-MM-DD; send null to clear the follow-up date, omit to leave it unchanged",
    )


class ApplicationState(BaseModel):
    job_id: int
    status: ApplicationStatus
    note: str
    updated_at: str | None
    follow_up_at: str | None


class TaskListQuery(PageQuery):
    active: bool = Field(False, description="Only queued or running tasks (resume progress after a reload)")


class SessionUser(BaseModel):
    id: int
    username: str
    is_admin: bool


class Session(BaseModel):
    user: SessionUser | None


class SignIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class SignUp(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=256)


class AppConfig(BaseModel):
    registration_open: bool
    demo_mode: bool  # true while the caller sees the read-only sample workspace
    demo_live: bool  # the demo offers guest workspaces on real providers
    guest: bool  # the caller is in a guest workspace
    llm_provider: Literal["gemini", "mock"]
    job_source: str
    search_results_per_run: int


class ProfileVersion(BaseModel):
    id: int
    profile_version: int
    model_name: str
    created_at: str
    review_status: str
    review_note: str | None = None
    reviewed_at_utc: str | None = None


class ProfileReview(BaseModel):
    review_status: Literal["approved", "needs_changes"]
    review_note: str = Field("", max_length=2000)


class ProfileEdit(BaseModel):
    master_profile: dict[str, Any] = Field(description="The full edited Master Profile JSON")


class UserDetails(BaseModel):
    candidate_name: str = ""
    current_title: str = ""
    location: str = ""
    years_experience: str = ""
    email: str = ""
    phone: str = ""
    work_authorization: str = ""
    target_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    key_skills: str = ""


class Attachment(BaseModel):
    name: str = Field(max_length=200)
    mime_type: Literal["application/pdf", "image/png", "image/jpeg", "image/webp"]
    data_base64: str = Field(description="File content, base64; ≤10 MB each, ≤30 MB total")


class ProfileSynthesisRequest(BaseModel):
    resume_text: str = Field("", max_length=100_000)
    extra_context: str = Field("", max_length=20_000)
    links: list[str] = Field(default_factory=list, max_length=20)
    user_details: UserDetails = Field(default_factory=UserDetails)
    attachments: list[Attachment] = Field(default_factory=list, max_length=10)
    sample: Literal["text", "pdf", "docx", "image"] | None = Field(
        None,
        description="Live demo only: build from the sample résumé in this format; everything else is ignored",
    )


class ProfileSupplementRequest(BaseModel):
    profile_id: int | None = Field(None, gt=0)
    selected_fields: list[str] = Field(min_length=1, max_length=50)
    answers: dict[str, str] = Field(default_factory=dict)
    additional_context: str = Field("", max_length=20_000)


class ExportQuery(BaseModel):
    format: Literal["pdf", "docx"] = "pdf"
