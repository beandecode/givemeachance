"""Property-based fuzzing of /api/v1 from its own OpenAPI document (schemathesis).

Every generated request must get a documented status and a response matching its schema;
in particular, no 500s and no responses that break the declared models.
"""

import pytest
import schemathesis
from hypothesis import HealthCheck, settings

from app import create_app
from tests.support import register

_SESSION: dict[str, str] = {}


@pytest.fixture
def api_schema():
    app = create_app()
    client = register(app, prefix="fuzz")
    schema = schemathesis.openapi.from_wsgi("/api/v1/openapi.json", app)
    _SESSION["cookie"] = client.get_cookie("session").value
    return schema


# Signing out mid-run would turn the rest of the run into 401s and hide real problems.
schema = schemathesis.pytest.from_fixture("api_schema").exclude(path="/api/v1/session", method="DELETE")


@schema.parametrize()
@settings(max_examples=25, deadline=None, suppress_health_check=list(HealthCheck))
def test_api_conforms_to_its_contract(case):
    case.call_and_validate(headers={"Cookie": f"session={_SESSION['cookie']}"})
