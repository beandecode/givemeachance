"""Typed JSON API under /api/v1.

Each endpoint declares pydantic models for its query string, JSON body and response data;
`api_route` validates input, enforces the login rule, wraps the result in the envelope and
records the endpoint so `app/openapi.py` can describe it. Errors anywhere under /api/ use the
same envelope (docs/api.md#response-shapes, docs/error-codes.md).
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from flask import Flask, Response, g, jsonify, request
from pydantic import BaseModel, TypeAdapter, ValidationError
from werkzeug.exceptions import HTTPException

from core.config import load_settings
from core.db import db_conn
from core.demo import demo_mode_enabled
from core.errors import ApiError
from core.request_context import resolve_request_user
from core.schemas import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApiContext:
    """What a handler gets besides its path, query and body arguments."""

    conn: sqlite3.Connection
    settings: Settings
    user: sqlite3.Row | None
    correlation_id: str

    @property
    def user_id(self) -> int:
        if self.user is None:
            raise ApiError(401, 1001, "login required")
        return int(self.user["id"])


@dataclass(frozen=True)
class Endpoint:
    method: str
    rule: str
    name: str
    summary: str
    tag: str
    query: type[BaseModel] | None
    body: type[BaseModel] | None
    response: Any  # a type for TypeAdapter (model, list[model], ...), or None for no data
    status: int
    auth: bool
    raw_response: tuple[str, ...] | None  # media types when the handler returns a Flask Response (a file)


def api_endpoints(app: Flask) -> list[Endpoint]:
    """Endpoints registered with `api_route` on this app, in registration order."""
    return app.extensions.setdefault("api_endpoints", [])


def ok_envelope(data: Any, status: int = 200) -> tuple[Response, int]:
    return jsonify({"status": "ok", "correlation_id": g.correlation_id, "data": data}), status


def error_envelope(status: int, code: int, message: str, details: list[dict] | None = None) -> tuple[Response, int]:
    body: dict[str, Any] = {
        "status": "error",
        "error_code": code,
        "message": message,
        "correlation_id": getattr(g, "correlation_id", ""),
    }
    if details:
        body["details"] = details
    return jsonify(body), status


def _validation_details(exc: ValidationError) -> list[dict]:
    return [
        {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
        for error in exc.errors(include_url=False, include_input=False)
    ]


def _parse(model: type[BaseModel], data: Any) -> BaseModel:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ApiError(400, 2002, "invalid request", details=_validation_details(exc)) from exc


def api_route(
    app: Flask,
    method: str,
    rule: str,
    *,
    summary: str,
    tag: str,
    response: Any = None,
    query: type[BaseModel] | None = None,
    body: type[BaseModel] | None = None,
    status: int = 200,
    auth: bool = True,
    raw_response: tuple[str, ...] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register `handler(ctx, **path_args, [query=], [body=])` at `rule` (a Flask rule under /api/v1)."""
    response_adapter = TypeAdapter(response) if response is not None else None

    def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
        name = handler.__name__

        def view(**path_args: Any):
            settings = load_settings()
            with db_conn(settings.app.db_path) as conn:
                demo_mode = demo_mode_enabled()
                user = resolve_request_user(conn, allow_demo_fallback=demo_mode)
                if user is not None and str(user["username"]) == "demo" and not demo_mode:
                    user = None
                if auth and user is None:
                    raise ApiError(401, 1001, "login required")
                kwargs: dict[str, Any] = dict(path_args)
                if query is not None:
                    kwargs["query"] = _parse(query, request.args.to_dict())
                if body is not None:
                    kwargs["body"] = _parse(body, request.get_json(silent=True) or {})
                result = handler(ApiContext(conn, settings, user, g.correlation_id), **kwargs)
            if raw_response is not None:
                return result
            data = None
            if response_adapter is not None:
                # Validating enforces the declared contract; a mismatch is a server bug (500).
                data = response_adapter.dump_python(response_adapter.validate_python(result), mode="json")
            return ok_envelope(data, status)

        view.__name__ = name
        app.add_url_rule(rule, endpoint=name, view_func=view, methods=[method])
        api_endpoints(app).append(
            Endpoint(method, rule, name, summary, tag, query, body, response, status, auth, raw_response)
        )
        return handler

    return decorator


def register_api_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_error(error: ApiError):
        return error_envelope(error.status, error.code, error.message, error.details)

    @app.errorhandler(Exception)
    def _unhandled(error: Exception):
        if isinstance(error, HTTPException):
            return error  # handled by the HTTPException handler in app/guards.py
        if not request.path.startswith("/api/"):
            raise error  # legacy routes keep Flask's default behavior
        logger.exception("Unhandled error on %s %s", request.method, request.path)
        message = f"Something went wrong (ref {getattr(g, 'correlation_id', '')})"
        return error_envelope(500, 5001, message)
