import json
import re
from pathlib import Path

from openapi_spec_validator import validate

import app.route_groups.workspace as workspace
from app import create_app
from app.openapi import build_openapi
from tests.support import register

OPENAPI_FILE = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"


def _logged_in_client():
    return register(create_app(), "contract_user")


def test_committed_openapi_document_is_current_and_valid():
    document = build_openapi(create_app())

    validate(document)
    assert json.loads(OPENAPI_FILE.read_text()) == document, "run: python scripts/export_openapi.py"


def test_unknown_api_route_returns_error_envelope():
    response = _logged_in_client().get("/api/v1/does-not-exist")

    body = response.get_json()
    assert response.status_code == 404
    assert body["status"] == "error" and body["error_code"] == 3003 and body["correlation_id"]


def test_wrong_method_maps_to_method_not_allowed_code():
    response = _logged_in_client().delete("/api/v1/overview")

    assert response.status_code == 405
    assert response.get_json()["error_code"] == 2005


def test_invalid_query_reports_field_details():
    response = _logged_in_client().get("/api/v1/jobs?limit=0")

    body = response.get_json()
    assert response.status_code == 400
    assert body["error_code"] == 2002
    assert body["details"][0]["field"] == "limit"


def test_login_required_uses_envelope():
    response = create_app().test_client().get("/api/v1/overview")

    assert response.status_code == 401
    assert response.get_json()["error_code"] == 1001


def test_unexpected_errors_do_not_leak_internals(monkeypatch):
    client = _logged_in_client()

    def broken(*_args, **_kwargs):
        raise RuntimeError("no such table: secrets at /srv/private.db")

    monkeypatch.setattr(workspace, "overview", broken)
    response = client.get("/api/v1/overview", headers={"X-Correlation-ID": "req_leakcheck"})

    body = response.get_json()
    assert response.status_code == 500
    assert body["error_code"] == 5001
    assert body["message"] == "Something went wrong (ref req_leakcheck)"
    assert "secrets" not in response.get_data(as_text=True)


def test_unsupported_media_type_uses_its_own_code():
    client = _logged_in_client()

    response = client.put("/api/v1/search-preferences", data="adzuna=1", content_type="text/plain")

    assert response.status_code == 415
    assert response.get_json()["error_code"] == 2004


def test_unsupported_method_is_405_even_when_signed_out():
    response = create_app().test_client().put("/api/v1/config", json={})

    assert response.status_code == 405
    assert response.get_json()["error_code"] == 2005


def test_openapi_document_is_served_by_the_app():
    app = create_app()

    served = app.test_client().get("/api/v1/openapi.json").get_json()

    assert served == build_openapi(app)


def test_response_models_mark_every_field_required_and_refs_resolve():
    document = build_openapi(create_app())
    schemas = document["components"]["schemas"]
    referenced = set(re.findall(r"#/components/schemas/(\w+)", json.dumps(document)))
    assert referenced <= set(schemas), referenced - set(schemas)
    # Responses always carry every field, so generated clients never see "maybe undefined".
    assert set(schemas["Task"]["required"]) == set(schemas["Task"]["properties"])
    assert "keywords" in schemas["AdzunaSearchParams"]["required"]
    # The request variant keeps its defaults optional under its own name.
    assert "keywords" not in schemas["AdzunaSearchParamsInput"].get("required", [])
