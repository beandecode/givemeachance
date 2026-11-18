"""Shared authentication, request validation and HTTP response policy."""

from __future__ import annotations

from urllib.parse import urlsplit

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

from app.http import _resolve_correlation_id
from core.config import load_settings
from core.db import db_conn
from core.demo import (
    DEMO_READ_ONLY_MESSAGE,
    GUEST_REFUSED_MESSAGE,
    GUEST_WRITE_ENDPOINTS,
    START_GUEST_ENDPOINT,
    demo_live_enabled,
    demo_mode_enabled,
)
from core.errors import code_for_http_status
from core.guest_service import is_guest
from core.logging_setup import correlation_id_var
from core.request_context import resolve_request_user as _resolve_request_user


def register_guards(app: Flask) -> None:
    write_auth_exempt_endpoints = {
        "api_create_session",
        "api_create_account",
        "api_delete_session",
    }

    def api_error(message, status, error_code):
        return jsonify(
            {
                "error": message,
                "message": message,
                "status": "error",
                "error_code": error_code,
                "correlation_id": g.correlation_id,
            }
        ), status

    @app.before_request
    def _request_boundary():
        g.correlation_id = _resolve_correlation_id()
        correlation_id_var.set(g.correlation_id)
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None
        if request.routing_exception is not None:
            return None  # unknown route or method: let it surface as 404/405
        origin = request.headers.get("Origin") or request.headers.get("Referer")
        if origin:
            try:
                is_same_origin = urlsplit(origin).netloc == request.host
            except ValueError:
                is_same_origin = False
            if not is_same_origin:
                return api_error("cross-origin write requests are not allowed", 403, 1003)
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            return api_error("cross-origin write requests are not allowed", 403, 1003)
        if request.is_json:
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                return api_error("JSON body must be a valid object", 400, 2001)
        elif request.content_length or request.headers.get("Transfer-Encoding"):
            return api_error("Content-Type must be application/json", 415, 2004)

    @app.after_request
    def _response_boundary(response):
        response.headers.setdefault("X-Correlation-ID", getattr(g, "correlation_id", ""))
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.errorhandler(HTTPException)
    def _http_error(error):
        response = error.get_response()
        response.data = app.json.dumps(
            {
                "error": error.description,
                "message": error.description,
                "status": "error",
                "error_code": code_for_http_status(error.code or 500),
                "correlation_id": getattr(g, "correlation_id", ""),
            }
        )
        response.content_type = "application/json"
        return response

    @app.before_request
    def _write_login_guard():
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None
        if request.routing_exception is not None:
            return None  # unknown route or method: let it surface as 404/405

        endpoint = request.endpoint or ""
        if demo_mode_enabled():
            # Read-only, except in the live demo: anyone may start a guest workspace, and a guest may use the
            # endpoints on the allowlist.
            if not demo_live_enabled():
                return api_error(DEMO_READ_ONLY_MESSAGE, 403, 1004)
            if endpoint == START_GUEST_ENDPOINT:
                return None
            with db_conn(load_settings().app.db_path) as conn:
                guest = is_guest(_resolve_request_user(conn, allow_demo_fallback=False))
            if not guest:
                return api_error(DEMO_READ_ONLY_MESSAGE, 403, 1004)
            if endpoint not in GUEST_WRITE_ENDPOINTS:
                return api_error(GUEST_REFUSED_MESSAGE, 403, 1004)
            return None

        if endpoint in write_auth_exempt_endpoints:
            return None

        settings = load_settings()
        with db_conn(settings.app.db_path) as conn:
            user_row = _resolve_request_user(conn, allow_demo_fallback=False)

        if user_row is not None and str(user_row["username"]) != "demo" and not is_guest(user_row):
            return None

        return api_error("login required for write operations", 401, 1001)
