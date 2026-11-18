"""Serve the React SPA build (web/ → app/spa_dist) under /app with a client-side-routing fallback."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, Response, current_app, make_response, redirect, send_from_directory

# Everything the SPA loads is same-origin: no CDN, no inline scripts or <style> elements.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
    "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
IMMUTABLE = "public, max-age=31536000, immutable"  # Vite fingerprints everything under assets/


CASE_STUDY_DIR = Path(__file__).resolve().parents[1] / "case_study"


def spa_dir() -> Path:
    configured = current_app.config.get("SPA_DIR")
    return Path(configured) if configured else Path(__file__).resolve().parents[1] / "spa_dist"


def _secure(response: Response) -> Response:
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    response.headers["X-Frame-Options"] = "DENY"
    return response


def register_spa_routes(app: Flask) -> None:
    @app.get("/")
    def home():
        return redirect("/app/", 302)

    @app.get("/app")
    @app.get("/app/")
    @app.get("/app/<path:path>")
    def spa(path: str = ""):
        """The single-page app: real files are served as-is, any other path gets index.html."""
        root = spa_dir()
        if not (root / "index.html").is_file():
            response = make_response("The web app is not built. Run `npm run build` in web/.\n", 404)
            response.mimetype = "text/plain"
            return _secure(response)
        last_segment = path.rsplit("/", 1)[-1]
        if path.startswith("assets/") or "." in last_segment:
            # send_from_directory rejects traversal and answers 404 for missing files.
            response = send_from_directory(root, path)
            if path.startswith("assets/"):
                response.headers["Cache-Control"] = IMMUTABLE
            return _secure(response)
        response = send_from_directory(root, "index.html")
        response.headers["Cache-Control"] = "no-store"
        return _secure(response)

    @app.get("/case-study")
    @app.get("/case-study/")
    @app.get("/case-study/<path:path>")
    def case_study(path: str = ""):
        """The static case study page: plain files from app/case_study/, nothing else."""
        if path.rsplit("/", 1)[-1] not in {"", *(p.name for p in CASE_STUDY_DIR.iterdir() if p.is_file())}:
            return _secure(make_response("Not found\n", 404))
        response = send_from_directory(CASE_STUDY_DIR, path or "index.html")
        response.headers["Cache-Control"] = "no-cache" if not path or path.endswith(".html") else "public, max-age=3600"
        return _secure(response)
