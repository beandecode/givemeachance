from core.config import load_settings
from core.db import db_conn, init_db
from core.re_evaluation_service import collect_re_evaluate_job_ids, run_re_evaluation
from core.users import create_user


def _insert_job(conn, source_job_id: str, owner_user_id: int):
    conn.execute(
        """
        INSERT INTO jobs (
            source,
            source_job_id,
            title,
            company,
            location,
            salary_min,
            salary_max,
            description,
            description_hash,
            posted_date,
            url,
            raw_payload,
            owner_user_id,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            "test",
            source_job_id,
            f"Title {source_job_id}",
            "Acme",
            "Toronto",
            None,
            None,
            "Description",
            f"hash-{source_job_id}",
            "2026-04-17",
            f"https://example.com/{source_job_id}",
            "{}",
            owner_user_id,
        ),
    )
    return int(conn.execute("SELECT id FROM jobs WHERE source_job_id = ?", (source_job_id,)).fetchone()["id"])


def _insert_evaluation(conn, job_id: int, confidence: str, risk_flags: str):
    conn.execute(
        """
        INSERT INTO evaluations (
            job_id,
            match_score,
            strengths,
            gaps,
            fit_reason,
            should_apply,
            total_score,
            dimension_scores_json,
            match_reasons,
            risk_flags,
            recommendation_level,
            confidence_level,
            missing_information,
            model_name,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            job_id,
            80,
            "[]",
            "[]",
            "good fit",
            1,
            80,
            "{}",
            "[]",
            risk_flags,
            "yes",
            confidence,
            "[]",
            "mock-model",
        ),
    )


def test_collect_re_evaluate_job_ids_respects_scope_and_visibility():
    settings = load_settings()
    init_db(settings.app.db_path)

    with db_conn(settings.app.db_path) as conn:
        user_a = create_user(conn, username="re_eval_user_a", password="password123")
        user_b = create_user(conn, username="re_eval_user_b", password="password123")

        job_a1 = _insert_job(conn, "a1", owner_user_id=int(user_a["id"]))
        job_a2 = _insert_job(conn, "a2", owner_user_id=int(user_a["id"]))
        job_b1 = _insert_job(conn, "b1", owner_user_id=int(user_b["id"]))

        _insert_evaluation(conn, job_a1, confidence="low", risk_flags="[]")
        _insert_evaluation(conn, job_a2, confidence="high", risk_flags='["missing evidence"]')
        _insert_evaluation(conn, job_b1, confidence="low", risk_flags='["risk"]')

        scoped_user = {"id": int(user_a["id"]), "is_admin": 0}

        all_ids = collect_re_evaluate_job_ids(
            conn,
            scope="all",
            days=7,
            limit=10,
            explicit_job_ids=[],
            current_user=scoped_user,
        )
        assert set(all_ids) == {job_a1, job_a2}

        low_confidence_ids = collect_re_evaluate_job_ids(
            conn,
            scope="low_confidence",
            days=7,
            limit=10,
            explicit_job_ids=[],
            current_user=scoped_user,
        )
        assert low_confidence_ids == [job_a1]

        high_risk_ids = collect_re_evaluate_job_ids(
            conn,
            scope="high_risk",
            days=7,
            limit=10,
            explicit_job_ids=[],
            current_user=scoped_user,
        )
        assert high_risk_ids == [job_a2]


def test_run_re_evaluation_blocks_when_profile_not_ready(monkeypatch):
    import core.re_evaluation_service as service

    settings = load_settings()
    init_db(settings.app.db_path)

    monkeypatch.setattr(
        service,
        "assess_latest_profile_readiness",
        lambda conn, user_id=None: {
            "allowed": False,
            "high_priority_missing_count": 2,
            "blocking_reasons": ["missing profile"],
        },
    )

    with db_conn(settings.app.db_path) as conn:
        result = run_re_evaluation(
            conn,
            settings=settings,
            scope="all",
            days=7,
            limit=10,
            explicit_job_ids=[],
            decided_by="test",
            quota_subject="user:1",
            current_user={"id": 1, "is_admin": 0},
            force_when_high_missing=False,
        )

    assert result["ok"] is False
    assert result["status_code"] == 409
    assert result["error"] == "profile is not ready for re-evaluation"
