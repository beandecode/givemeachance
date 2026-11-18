"""How match scores relate to what the user did with each job (swipes and applications), to tune the threshold."""

from __future__ import annotations

import sqlite3
from statistics import median
from typing import Any

# Furthest outcome wins: a job the user applied to and then got an interview for counts as "interview".
OUTCOMES = ("offer", "interview", "submitted", "accepted", "waitlisted", "skipped", "undecided")
_APPLICATION_OUTCOMES = {"hired": "offer", "offer": "offer", "interview": "interview", "submitted": "submitted"}


def calibration_report(conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    """One row per outcome that has scored jobs: count, lowest, median and highest match score."""
    rows = conn.execute(
        """SELECT e.match_score AS score, a.status AS application, t.action AS triage
           FROM jobs j JOIN evaluations e ON e.job_id = j.id
           LEFT JOIN applications a ON a.job_id = j.id
           LEFT JOIN job_triage t ON t.job_id = j.id AND t.user_id = j.owner_user_id
           WHERE j.owner_user_id = ?""",
        (user_id,),
    ).fetchall()
    scores: dict[str, list[int]] = {name: [] for name in OUTCOMES}
    for row in rows:
        outcome = _APPLICATION_OUTCOMES.get(str(row["application"])) or str(row["triage"] or "undecided")
        scores[outcome if outcome in scores else "undecided"].append(int(row["score"]))
    return [
        {"outcome": name, "count": len(values), "lowest": min(values), "median": median(values), "highest": max(values)}
        for name, values in scores.items()
        if values
    ]
