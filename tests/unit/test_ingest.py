import pytest

from core.config import load_settings
from core.db import db_conn, init_db
from core.ingest import run_ingest


def test_ingest_inserts_new_and_skips_duplicates():
    settings = load_settings()
    init_db(settings.app.db_path)

    with db_conn(settings.app.db_path) as conn:
        first = run_ingest(conn, settings, run_key="test-run-1")
        second = run_ingest(conn, settings, run_key="test-run-2")

    assert first["inserted_count"] == 3
    assert second["inserted_count"] == 0


def test_ingest_skips_titles_of_levels_the_user_did_not_pick():
    from core.schemas import JobSearchConfig

    settings = load_settings()
    init_db(settings.app.db_path)

    with db_conn(settings.app.db_path) as conn:
        none_match = run_ingest(
            conn, settings, run_key="levels-1", search_config=JobSearchConfig(target_levels=["staff_plus"])
        )
        mid_only = run_ingest(conn, settings, run_key="levels-2", search_config=JobSearchConfig(target_levels=["mid"]))

    assert (none_match["inserted_count"], none_match["skipped_by_level"]) == (0, 4)
    assert (mid_only["inserted_count"], mid_only["skipped_by_level"]) == (3, 0)


def test_adzuna_fetches_a_full_page_and_counts_only_accepted_jobs(monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    from adapters.jobs.adzuna_api import AdzunaApiAdapter
    from core.schemas import AdzunaSearchParams, JobSearchConfig
    from core.seniority import title_allowed

    monkeypatch.setenv("ADZUNA_APP_ID", "id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "key")
    titles = ["Senior Engineer", "Staff Engineer", "Backend Engineer", "Engineering Manager", "Data Engineer"]
    requested: list[dict] = []

    def fake_request(self, endpoint):
        requested.append(parse_qs(urlsplit(endpoint).query))
        return {
            "results": [
                {"id": str(n), "title": title, "description": "x" * 500, "redirect_url": f"https://e.com/{n}"}
                for n, title in enumerate(titles)
            ]
        }

    monkeypatch.setattr(AdzunaApiAdapter, "_request_json", fake_request)
    adapter = AdzunaApiAdapter(search_config=JobSearchConfig(adzuna=AdzunaSearchParams(keywords=["engineer"])))

    jobs = adapter.fetch_jobs(limit=2, accept=lambda job: title_allowed(job.title, ["mid"]))

    assert [job.title for job in jobs] == ["Backend Engineer", "Data Engineer"]
    assert requested[0]["results_per_page"] == ["10"]  # not 2: the filter needs a full page to choose from


def test_a_rejected_adzuna_request_never_puts_the_key_in_an_error_or_a_log_line(monkeypatch, caplog):
    import logging
    from io import BytesIO
    from urllib.error import HTTPError

    import adapters.jobs.adzuna_api as adzuna
    from core.schemas import AdzunaSearchParams, JobSearchConfig

    monkeypatch.setenv("ADZUNA_APP_ID", "APPID0001")
    monkeypatch.setenv("ADZUNA_APP_KEY", "APPKEY-SECRET-0002")

    def rejected(url, timeout):
        raise HTTPError(url, 401, "Unauthorized", {}, BytesIO(b""))

    monkeypatch.setattr(adzuna, "urlopen", rejected)
    adapter = adzuna.AdzunaApiAdapter(search_config=JobSearchConfig(adzuna=AdzunaSearchParams(keywords=["python"])))

    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError) as failure:
        adapter.fetch_jobs(limit=5)

    everything = str(failure.value) + caplog.text
    assert "APPKEY-SECRET-0002" not in everything and "APPID0001" not in everything
    assert any(getattr(r, "provider", "") == "adzuna" and r.status == "401" for r in caplog.records)


def test_adzuna_reads_the_full_posting_of_accepted_jobs_only(monkeypatch):
    import adapters.jobs.adzuna_api as adzuna
    from core.schemas import AdzunaSearchParams, JobSearchConfig

    monkeypatch.setenv("ADZUNA_APP_ID", "id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "key")
    results = [
        {
            "id": str(n),
            "title": title,
            "description": "x" * 497 + "...",
            "redirect_url": f"https://www.adzuna.ca/details/{n}",
        }
        for n, title in enumerate(["Data Scientist", "Staff Data Scientist", "Data Analyst"])
    ]
    monkeypatch.setattr(adzuna.AdzunaApiAdapter, "_request_json", lambda self, endpoint: {"results": results})
    fetched: list[str] = []

    def full_text(url, preview):
        fetched.append(url)
        return None if url.endswith("/2") else f"Full posting for {url}. " * 40

    monkeypatch.setattr(adzuna, "fetch_full_description", full_text)
    adapter = adzuna.AdzunaApiAdapter(search_config=JobSearchConfig(adzuna=AdzunaSearchParams(keywords=["data"])))

    jobs = adapter.fetch_jobs(limit=5, accept=lambda job: not job.title.startswith("Staff"))

    assert fetched == ["https://www.adzuna.ca/details/0", "https://www.adzuna.ca/details/2"]  # not the rejected one
    assert jobs[0].description.startswith("Full posting for https://www.adzuna.ca/details/0")
    assert jobs[1].description.endswith("...")  # no full text: the preview stays, scoring will skip it
