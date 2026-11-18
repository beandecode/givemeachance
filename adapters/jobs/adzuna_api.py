from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from adapters.jobs.base import JobSourceAdapter
from core.api_limits import consume_api_quota, consume_dual_api_quota
from core.config import load_job_search_config
from core.job_fulltext import fetch_full_description
from core.logging_setup import log_provider_call
from core.schemas import JobRecord, JobSearchConfig
from core.time_utils import utc_today_iso

logger = logging.getLogger(__name__)


class AdzunaApiAdapter(JobSourceAdapter):
    """Adzuna live API adapter for Canada job search."""

    def __init__(
        self,
        db_path: str | None = None,
        daily_limit: int | None = None,
        global_daily_limit: int | None = None,
        quota_subject: str | None = None,
        search_config: JobSearchConfig | None = None,
    ):
        search = (search_config or load_job_search_config()).adzuna
        self.country = search.country
        self.keywords = search.keywords
        self.where = search.location
        self.results_per_page = search.results_per_page
        self.max_pages = search.max_pages
        self.days_old = search.days_old
        self.sort_by = search.sort_by
        self.salary_min = search.salary_min
        self.salary_max = search.salary_max
        self.distance = search.distance
        self.company = search.company
        self.category = search.category
        self.full_time = search.full_time
        self.part_time = search.part_time
        self.permanent = search.permanent
        self.contract = search.contract
        self.what_and = search.what_and
        self.what_or = search.what_or
        self.what_phrase = search.what_phrase
        self.what_exclude = search.what_exclude
        self.app_id = os.getenv("ADZUNA_APP_ID", "")
        self.app_key = os.getenv("ADZUNA_APP_KEY", "")
        self.db_path = db_path
        self.daily_limit = daily_limit
        self.global_daily_limit = global_daily_limit
        self.quota_subject = quota_subject or "system"
        if not self.app_id or not self.app_key:
            raise ValueError("Missing ADZUNA_APP_ID or ADZUNA_APP_KEY in environment.")

    def _request_json(self, endpoint: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(3):
            started = time.monotonic()
            try:
                with urlopen(endpoint, timeout=30) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                log_provider_call(logger, "adzuna", "search", attempt + 1, started, "ok")
                return payload
            except HTTPError as error:
                log_provider_call(logger, "adzuna", "search", attempt + 1, started, error.code)
                message = f"Adzuna API HTTP {error.code}; provider request failed"
                wrapped = RuntimeError(message)
                last_error = wrapped
                if error.code in {400, 401, 403, 404}:
                    raise wrapped from error
                if attempt < 2:
                    time.sleep(2**attempt)
            except URLError as error:
                log_provider_call(logger, "adzuna", "search", attempt + 1, started, type(error).__name__)
                last_error = error
                if attempt < 2:
                    time.sleep(2**attempt)
        if last_error is not None:
            raise last_error
        raise RuntimeError("Adzuna request failed with unknown error")

    def fetch_jobs(self, limit: int, accept: Callable[[JobRecord], bool] | None = None) -> list[JobRecord]:
        normalized: list[JobRecord] = []
        # With a filter, ask for a full page: some of it will be dropped before it counts toward `limit`.
        per_page = max(1, min(self.results_per_page, 50, limit if accept is None else 50))

        for keyword in self.keywords:
            for page in range(1, max(1, self.max_pages) + 1):
                if len(normalized) >= limit:
                    break

                query = {
                    "app_id": self.app_id,
                    "app_key": self.app_key,
                    "results_per_page": per_page,
                    "what": keyword,
                    "where": self.where,
                    "max_days_old": self.days_old,
                    "sort_by": self.sort_by,
                    "content-type": "application/json",
                }

                if self.salary_min is not None:
                    query["salary_min"] = self.salary_min
                if self.salary_max is not None:
                    query["salary_max"] = self.salary_max
                if self.distance is not None:
                    query["distance"] = self.distance
                if self.company:
                    query["company"] = self.company
                if self.category:
                    query["category"] = self.category
                # Adzuna flags are presence-based: send only "1" when explicitly enabled.
                if self.full_time is True:
                    query["full_time"] = "1"
                if self.part_time is True:
                    query["part_time"] = "1"
                if self.permanent is True:
                    query["permanent"] = "1"
                if self.contract is True:
                    query["contract"] = "1"
                if self.what_and:
                    query["what_and"] = self.what_and
                if self.what_or:
                    query["what_or"] = self.what_or
                if self.what_phrase:
                    query["what_phrase"] = self.what_phrase
                if self.what_exclude:
                    query["what_exclude"] = self.what_exclude

                if self.db_path is not None and self.daily_limit is not None:
                    if self.global_daily_limit is not None:
                        allowed, usage = consume_dual_api_quota(
                            db_path=self.db_path,
                            provider="adzuna",
                            subject=self.quota_subject,
                            subject_daily_limit=self.daily_limit,
                            global_daily_limit=self.global_daily_limit,
                            units=1,
                        )
                        if not allowed:
                            if normalized:
                                return normalized
                            if usage["reason"] == "subject_quota_reached":
                                raise RuntimeError(
                                    f"Adzuna user daily quota reached: {usage['subject_used']}/{usage['subject_limit']}"
                                )
                            raise RuntimeError(
                                f"Adzuna global daily quota reached: {usage['global_used']}/{usage['global_limit']}"
                            )
                    else:
                        allowed, used = consume_api_quota(
                            db_path=self.db_path,
                            provider="adzuna",
                            daily_limit=self.daily_limit,
                            units=1,
                        )
                        if not allowed:
                            if normalized:
                                return normalized
                            raise RuntimeError(f"Adzuna daily quota reached: {used}/{self.daily_limit}")

                endpoint = f"https://api.adzuna.com/v1/api/jobs/{self.country}/search/{page}?{urlencode(query)}"
                payload = self._request_json(endpoint)

                for item in payload.get("results", []):
                    if len(normalized) >= limit:
                        break

                    company = item.get("company") or {}
                    location = item.get("location") or {}

                    posted = item.get("created")
                    if posted:
                        try:
                            posted = datetime.fromisoformat(posted.replace("Z", "+00:00")).date().isoformat()
                        except ValueError:
                            posted = str(posted)[:10]
                    else:
                        posted = utc_today_iso()

                    record = JobRecord.model_validate(
                        {
                            "id": str(item.get("id") or item.get("redirect_url") or item.get("title")),
                            "title": item.get("title", "Untitled"),
                            "company": company.get("display_name", "Unknown"),
                            "location": location.get("display_name", "Unknown"),
                            "salary_min": int(item["salary_min"]) if item.get("salary_min") else None,
                            "salary_max": int(item["salary_max"]) if item.get("salary_max") else None,
                            "description": item.get("description", ""),
                            "posted_date": posted,
                            "source": "adzuna",
                            "url": item.get("redirect_url", ""),
                        }
                    )
                    if accept is None or accept(record):
                        # Read the whole posting before filters, scoring and storage see it (core/job_fulltext.py).
                        full = fetch_full_description(record.url, record.description)
                        if full is not None:
                            record = record.model_copy(update={"description": full})
                        normalized.append(record)

        return normalized
