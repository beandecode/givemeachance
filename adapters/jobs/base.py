from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from core.schemas import JobRecord


class JobSourceAdapter(ABC):
    """Abstract adapter interface for job providers."""

    @abstractmethod
    def fetch_jobs(self, limit: int, accept: Callable[[JobRecord], bool] | None = None) -> list[JobRecord]:
        """Return up to `limit` normalized job records; with `accept`, only records it approves count."""
        raise NotImplementedError
