import re

from app import create_app
from app.route_groups.spa import CONTENT_SECURITY_POLICY


def test_case_study_is_served_with_its_files_and_the_strict_csp():
    client = create_app().test_client()
    for path in ("/case-study", "/case-study/"):
        with client.get(path) as page:
            assert page.status_code == 200
            assert b"GivemeaChance" in page.data
            assert page.headers["Content-Security-Policy"] == CONTENT_SECURITY_POLICY
            assert b"style=" not in page.data and b"<script" not in page.data  # the policy would block both
    with client.get("/case-study") as page:
        html = page.data.decode()
    refs = re.findall(r'(?:href|src)="(/case-study/[^"]+)"', html)  # absolute: /case-study has no slash
    assert len(refs) == 4
    for ref in refs:
        with client.get(ref) as asset:
            assert asset.status_code == 200, ref
    for path in ("/case-study/case-study.css", "/case-study/discover.png", "/case-study/Manrope-Variable.woff2"):
        with client.get(path) as asset:
            assert asset.status_code == 200, path


def test_case_study_serves_nothing_outside_its_folder():
    client = create_app().test_client()
    for path in ("/case-study/../run.py", "/case-study/missing.png", "/case-study/%2e%2e/run.py"):
        with client.get(path) as response:
            assert response.status_code == 404, path
