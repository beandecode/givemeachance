import pytest

from core.job_filters import classify_work_mode, filter_reason, has_filters
from core.schemas import AdzunaSearchParams, JobRecord, JobSearchConfig


def _job(**changes):
    base = {
        "id": "1",
        "title": "Backend Engineer",
        "company": "Acme",
        "location": "Toronto, ON",
        "description": "Build services in Python.",
        "posted_date": "2026-10-01",
        "source": "adzuna",
        "url": "https://example.com/1",
    }
    return JobRecord.model_validate({**base, **changes})


def test_no_filters_means_everything_passes():
    config = JobSearchConfig()
    assert not has_filters(config)
    assert filter_reason(_job(description="Top secret clearance required, onsite"), config) is None


def test_salary_filter_drops_only_a_posting_that_states_a_lower_maximum():
    config = JobSearchConfig(adzuna=AdzunaSearchParams(salary_min=100_000))
    assert filter_reason(_job(salary_max=90_000), config) == "salary"
    assert filter_reason(_job(salary_max=140_000), config) is None
    assert filter_reason(_job(), config) is None  # no stated salary: unknown passes


def test_title_words_match_whole_words_case_insensitively():
    config = JobSearchConfig(exclude_title_words=["sales", "Data Entry"])
    assert filter_reason(_job(title="Sales Engineer"), config) == "title_word"
    assert filter_reason(_job(title="Data entry clerk"), config) == "title_word"
    assert filter_reason(_job(title="Wholesales Systems Engineer"), config) is None


@pytest.mark.parametrize(
    ("text", "mode"),
    [
        ("Fully remote role", "remote"),
        ("Hybrid, 3 days in the office", "hybrid"),
        ("This is an on-site position", "onsite"),
        ("Build services in Python.", None),
    ],
)
def test_work_mode_is_read_from_the_posting(text, mode):
    assert classify_work_mode(_job(description=text)) == mode


def test_work_mode_filter_drops_other_modes_but_not_unknown_ones():
    config = JobSearchConfig(work_modes=["remote", "hybrid"])
    assert filter_reason(_job(description="On-site in Toronto"), config) == "work_mode"
    assert filter_reason(_job(description="Remote friendly"), config) is None
    assert filter_reason(_job(), config) is None


@pytest.mark.parametrize(
    ("knockout", "text"),
    [
        ("security_clearance", "Active Secret clearance required."),
        ("citizenship_required", "Applicants must be a Canadian citizen."),
        ("no_sponsorship", "We are unable to offer visa sponsorship."),
        ("no_sponsorship", "No sponsorship available."),
    ],
)
def test_knockouts_match_plain_statements(knockout, text):
    config = JobSearchConfig(knockouts=[knockout])
    assert filter_reason(_job(description=text), config) == "knockout"


def test_a_knockout_that_is_not_chosen_is_ignored():
    config = JobSearchConfig(knockouts=["security_clearance"])
    assert filter_reason(_job(description="No sponsorship available."), config) is None
