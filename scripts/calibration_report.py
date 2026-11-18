"""Print how match scores relate to your decisions, to help choose the Discover score threshold.

Usage: python scripts/calibration_report.py <username>
Read-only. Needs a few decisions per outcome to say anything.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.calibration import calibration_report
from core.config import load_settings
from core.db import db_conn


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    settings = load_settings()
    with db_conn(settings.app.db_path) as conn:
        user = conn.execute("SELECT id FROM users WHERE username = ?", (argv[1].strip().lower(),)).fetchone()
        if user is None:
            print(f"No user named {argv[1]!r}")
            return 1
        rows = calibration_report(conn, int(user["id"]))
    if not rows:
        print("No scored jobs yet.")
        return 0
    print(f"{'outcome':<12}{'jobs':>6}{'lowest':>8}{'median':>8}{'highest':>9}")
    for row in rows:
        print(f"{row['outcome']:<12}{row['count']:>6}{row['lowest']:>8}{row['median']:>8.0f}{row['highest']:>9}")
    chosen = [row for row in rows if row["outcome"] in {"accepted", "submitted", "interview", "offer"}]
    if chosen:
        print(f"\nThe lowest score you accepted or applied to is {min(row['lowest'] for row in chosen)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
