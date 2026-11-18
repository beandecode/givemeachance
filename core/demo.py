"""Public demo (DEMO_MODE): a read-only sample workspace; with DEMO_LIVE also guest workspaces on real providers.

Without DEMO_LIVE every write is refused with 1004 and the providers must be mock with zero quota. With DEMO_LIVE a
visitor can start a guest workspace (core/guest_service.py) whose writes are limited to `GUEST_WRITE_ENDPOINTS` and
whose provider calls are bounded by the configured daily limits (ADR-018).
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from core.request_normalization import parse_optional_bool
from core.schemas import Settings

GUEST_REFUSED_MESSAGE = "This is turned off in the live demo: accounts and hand edits to the profile cannot be changed."
SAMPLE_ONLY_MESSAGE = "In the live demo a profile is built from a sample résumé, never from your own."

# One fictional résumé in every format the app reads (scripts/make_sample_resumes.py). A guest builds a profile from
# one of these, so file upload and "Fill the gaps" can be tried for real without personal data.
SAMPLE_RESUME_DIR = Path(__file__).resolve().parents[1] / "data/mock/sample_resume"
SAMPLE_RESUMES: dict[str, tuple[str, str]] = {
    "text": ("casey-chen.txt", "text/plain"),
    "pdf": ("casey-chen.pdf", "application/pdf"),
    "docx": ("casey-chen.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "image": ("casey-chen.png", "image/png"),
}


def sample_resume_inputs(kind: str) -> tuple[dict, list[dict]]:
    """The synthesis input for a sample résumé, as if the visitor had pasted or attached it."""
    from core.profile_input_service import docx_text

    name, mime_type = SAMPLE_RESUMES[kind]
    data = (SAMPLE_RESUME_DIR / name).read_bytes()
    bundle = {"resume_text": "", "extra_context": "", "links": [], "user_details": {}}
    attachments: list[dict] = []
    if kind == "text":
        bundle["resume_text"] = data.decode("utf-8")
    elif kind == "docx":
        bundle["resume_text"] = docx_text(data)
    else:
        encoded = base64.b64encode(data).decode("ascii")
        attachments.append({"name": name, "mime_type": mime_type, "size": len(data), "data_base64": encoded})
    return bundle, attachments


DEMO_READ_ONLY_MESSAGE = "This is a read-only demo: changes are disabled."
_MOCK_SOURCES = {"mock_adzuna", "mock_jooble", "none", "null", "disabled"}


def demo_mode_enabled() -> bool:
    return bool(parse_optional_bool(os.getenv("DEMO_MODE")))


def demo_live_enabled() -> bool:
    return demo_mode_enabled() and bool(parse_optional_bool(os.getenv("DEMO_LIVE")))


# What a guest may change: their own jobs, decisions, documents and search, and a profile built from a sample
# résumé (synthesize with `sample`, approve, answer the gap questions). Accounts and hand edits of the profile stay
# refused, so a visitor can neither sign in nor store their own résumé. A test keeps both sets complete.
GUEST_WRITE_ENDPOINTS = frozenset(
    {
        "api_add_manual_job",
        "api_archive_job",
        "api_cancel_task",
        "api_delete_session",
        "api_edit_document",
        "api_generate_document",
        "api_rerun_evaluations",
        "api_review_profile",
        "api_save_preferences",
        "api_set_job_description",
        "api_start_search",
        "api_supplement_profile",
        "api_synthesize_profile",
        "api_triage_job",
        "api_unarchive_job",
        "api_undo_triage",
        "api_update_application",
        "api_update_journey",
        "workspace_save_search_preferences",
    }
)
GUEST_REFUSED_ENDPOINTS = frozenset(
    {
        "api_create_account",
        "api_create_session",
        "api_edit_profile",
    }
)
START_GUEST_ENDPOINT = "api_start_guest"
MAX_LIVE_GLOBAL_LIMIT = 500


def assert_demo_safe(settings: Settings) -> None:
    """Refuse to start a demo that could spend more than it was given: zero quota unless live, bounded when live."""
    if demo_live_enabled():
        limits = settings.api_limits.model_dump()
        problems = [
            f"api_limits.{name} is {limits[name]}, expected 1 to {MAX_LIVE_GLOBAL_LIMIT}"
            for name in ("gemini_global_daily_limit", "adzuna_global_daily_limit")
            if not 0 < limits[name] <= MAX_LIVE_GLOBAL_LIMIT
        ]
        problems += [
            f"api_limits.{name} is {limits[name]}, expected at most its global limit"
            for name in ("gemini_daily_limit", "adzuna_daily_limit")
            if limits[name] > limits[name.replace("_daily", "_global_daily")]
        ]
        if problems:
            raise RuntimeError("DEMO_LIVE needs bounded daily limits: " + "; ".join(problems))
        return
    problems = []
    if settings.llm.provider != "mock_gemini":
        problems.append(f"llm.provider is {settings.llm.provider!r}, expected 'mock_gemini'")
    for name in ("primary", "secondary"):
        source = str(getattr(settings.data_sources, name)).strip().lower()
        if source not in _MOCK_SOURCES:
            problems.append(f"data_sources.{name} is {source!r}, expected a mock source")
    for name, value in settings.api_limits.model_dump().items():
        if value != 0:
            problems.append(f"api_limits.{name} is {value}, expected 0")
    if problems:
        raise RuntimeError("DEMO_MODE needs mock providers and zero quota: " + "; ".join(problems))
