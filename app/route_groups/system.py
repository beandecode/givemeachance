"""Liveness, readiness and the OpenAPI document."""

from __future__ import annotations

import sqlite3

from flask import Flask, jsonify

from app.openapi import build_openapi
from core.config import load_settings
from core.db import db_conn
from core.db.migrations import MIGRATIONS


def register_system_routes(app: Flask) -> None:
    @app.get("/health")
    @app.get("/healthz")
    def health():
        """Liveness: the process answers HTTP. Used by Docker health checks."""
        return jsonify({"status": "ok"})

    @app.get("/api/v1/openapi.json")
    def openapi_document():
        """The live /api/v1 contract (same content as docs/openapi.json)."""
        if "openapi_document" not in app.extensions:
            app.extensions["openapi_document"] = build_openapi(app)
        return jsonify(app.extensions["openapi_document"])

    @app.get("/readyz")
    def readyz():
        """Readiness: the database is reachable and fully migrated."""
        settings = load_settings()
        try:
            with db_conn(settings.app.db_path) as conn:
                conn.execute("SELECT 1").fetchone()
                applied = {row[0] for row in conn.execute("SELECT migration_id FROM schema_migrations")}
        except sqlite3.Error:
            return jsonify({"status": "unavailable", "database": "unreachable"}), 503
        pending = [migration_id for migration_id, _ in MIGRATIONS if migration_id not in applied]
        if pending:
            return jsonify({"status": "unavailable", "pending_migrations": pending}), 503
        return jsonify({"status": "ok"})
