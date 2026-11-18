from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from adapters.jobs.base import JobSourceAdapter
from core.schemas import JobRecord


class MockAdzunaAdapter(JobSourceAdapter):
    """Load deterministic mock data that simulates Adzuna API responses."""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

    def fetch_jobs(self, limit: int, accept: Callable[[JobRecord], bool] | None = None) -> list[JobRecord]:
        payload = json.loads(self.file_path.read_text(encoding="utf-8"))
        jobs = [JobRecord.model_validate(item) for item in payload]
        return [job for job in jobs if accept is None or accept(job)][:limit]
