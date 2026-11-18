from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Frozen(BaseModel):
    """Settings are read-only once loaded; derive changed copies with `model_copy(update=...)`."""

    model_config = ConfigDict(frozen=True)


class AppSettings(_Frozen):
    name: str
    db_path: str
    log_path: str


class PipelineSettings(_Frozen):
    daily_limit: int = Field(default=50, ge=1, le=500)
    max_description_length: int = Field(default=10000, ge=1, le=100000)


class DataSourceSettings(_Frozen):
    primary: str
    secondary: str


class MockDataSettings(_Frozen):
    adzuna_file: str
    jooble_file: str


class LLMSettings(_Frozen):
    provider: Literal["gemini_api", "mock_gemini"]
    model: str
    prompt_version: str = "v3"
    fullstack_enabled: bool = False
    # Optional models for the two document steps; unset means `model`. A stronger model can fact-check
    # and write documents (a few calls per job picked) while the cheap one still scores every job.
    document_model: str | None = None
    audit_model: str | None = None
    audit_documents: bool = True  # fact-check each generated document against the profile (one extra call)


class ApiLimitSettings(_Frozen):
    gemini_daily_limit: int = 50
    adzuna_daily_limit: int = 5
    gemini_global_daily_limit: int = 120
    adzuna_global_daily_limit: int = 30


class AdzunaSearchParams(BaseModel):
    country: str = Field(default="ca", pattern=r"^[a-z]{2}$")
    keywords: list[str] = Field(default_factory=lambda: ["software engineer"])
    location: str = "canada"
    results_per_page: int = 10
    max_pages: int = 1
    days_old: int = Field(default=14, ge=1, le=365)
    sort_by: Literal["date", "salary", "relevance"] = "date"
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    distance: int | None = Field(default=None, ge=0)
    company: str | None = None
    category: str | None = None
    full_time: bool | None = None
    part_time: bool | None = None
    permanent: bool | None = None
    contract: bool | None = None
    what_and: str | None = None
    what_or: str | None = None
    what_phrase: str | None = None
    what_exclude: str | None = None

    @model_validator(mode="after")
    def enforce_fixed_paging(self):
        if self.salary_min is not None and self.salary_max is not None and self.salary_min > self.salary_max:
            raise ValueError("salary_min cannot be greater than salary_max")
        self.keywords = [word.strip() for word in self.keywords if word.strip()]
        if not self.keywords:
            raise ValueError("at least one keyword is required")
        for first, second in (("full_time", "part_time"), ("permanent", "contract")):
            if getattr(self, first) is not None and getattr(self, first) == getattr(self, second):
                setattr(self, first, None)
                setattr(self, second, None)
        # Product decision: paging is fixed for deterministic daily usage.
        self.results_per_page = 10
        self.max_pages = 1
        return self


JobLevel = Literal["junior", "mid", "senior", "staff_plus", "management"]
WorkMode = Literal["remote", "hybrid", "onsite"]
Knockout = Literal["security_clearance", "citizenship_required", "no_sponsorship"]


class JobSearchConfig(BaseModel):
    adzuna: AdzunaSearchParams = Field(default_factory=AdzunaSearchParams)
    target_levels: list[JobLevel] = Field(
        default_factory=list,
        description="Levels worth scoring; titles that name another level are skipped. Empty means all levels.",
    )
    work_modes: list[WorkMode] = Field(
        default_factory=list,
        description="Work modes worth scoring; a posting that names another mode is skipped. Empty means any.",
    )
    exclude_title_words: list[str] = Field(
        default_factory=list, max_length=20, description="Postings whose title contains one of these words are skipped"
    )
    knockouts: list[Knockout] = Field(
        default_factory=list,
        description="Skip postings that say they need a security clearance or citizenship, or offer no sponsorship",
    )

    @field_validator("exclude_title_words")
    @classmethod
    def _clean_words(cls, words: list[str]) -> list[str]:
        cleaned = [" ".join(word.split())[:40] for word in words]
        return list(dict.fromkeys(word for word in cleaned if word))


class Settings(_Frozen):
    app: AppSettings
    pipeline: PipelineSettings
    data_sources: DataSourceSettings
    mock_data: MockDataSettings
    llm: LLMSettings
    api_limits: ApiLimitSettings = Field(default_factory=ApiLimitSettings)


class JobRecord(BaseModel):
    external_id: str = Field(alias="id")
    title: str
    company: str
    location: str
    salary_min: int | None = None
    salary_max: int | None = None
    description: str
    posted_date: str
    source: str
    url: str


class EvaluationResult(BaseModel):
    match_score: int
    total_score: int | None = None
    dimension_scores: dict[str, int] = Field(default_factory=dict)
    match_reasons: list[str] = Field(default_factory=list)
    strengths: list[str]
    gaps: list[str]
    risk_flags: list[str] = Field(default_factory=list)
    recommendation_level: Literal["strong_yes", "yes", "maybe", "no"] = "maybe"
    confidence: Literal["high", "medium", "low"] = "medium"
    missing_information: list[str] = Field(default_factory=list)
    fit_reason: str
    should_apply: bool
    model_name: str

    @model_validator(mode="after")
    def sync_total_score(self):
        if self.total_score is None:
            self.total_score = self.match_score
        else:
            self.match_score = int(self.total_score)
        self.match_score = int(max(0, min(100, self.match_score)))
        self.total_score = self.match_score

        normalized_dimensions: dict[str, int] = {}
        for key, value in self.dimension_scores.items():
            try:
                normalized_dimensions[str(key)] = int(max(0, min(100, int(value))))
            except (TypeError, ValueError):
                continue
        self.dimension_scores = normalized_dimensions

        self.strengths = [str(item).strip() for item in self.strengths if str(item).strip()][:8]
        self.gaps = [str(item).strip() for item in self.gaps if str(item).strip()][:8]
        self.match_reasons = [str(item).strip() for item in self.match_reasons if str(item).strip()][:8]
        self.risk_flags = [str(item).strip() for item in self.risk_flags if str(item).strip()][:8]
        self.missing_information = [str(item).strip() for item in self.missing_information if str(item).strip()][:10]
        return self
