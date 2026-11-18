from app import create_app
from app.route_groups.spa import CONTENT_SECURITY_POLICY


def _app_with_build(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><div id=root></div>")
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log('spa')")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    app = create_app()
    app.config["SPA_DIR"] = str(tmp_path)
    return app


def test_client_routes_fall_back_to_index_with_csp_and_no_cache(tmp_path):
    client = _app_with_build(tmp_path).test_client()
    for path in ("/app", "/app/", "/app/jobs", "/app/jobs/42"):
        with client.get(path) as response:
            assert response.status_code == 200, path
            assert b"<div id=root>" in response.data
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers["Content-Security-Policy"] == CONTENT_SECURITY_POLICY


def test_fingerprinted_assets_are_cached_and_missing_files_are_404(tmp_path):
    client = _app_with_build(tmp_path).test_client()
    with client.get("/app/assets/index-abc123.js") as asset:
        assert asset.status_code == 200
        assert "immutable" in asset.headers["Cache-Control"]
    expected = {"/app/favicon.svg": 200, "/app/assets/gone-123.js": 404, "/app/missing.png": 404, "/app/../run.py": 404}
    for path, status in expected.items():
        with client.get(path) as response:
            assert response.status_code == status, path


def test_missing_build_explains_how_to_build(tmp_path):
    app = create_app()
    app.config["SPA_DIR"] = str(tmp_path / "nothing-here")
    response = app.test_client().get("/app/jobs")
    assert response.status_code == 404
    assert b"npm run build" in response.data


def test_root_opens_the_react_app():
    client = create_app().test_client()
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"] == "/app/"
    assert client.get("/static/js/dashboard.js").status_code == 404
