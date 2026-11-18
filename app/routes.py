"""Composition root for stable HTTP routes; no business logic belongs here."""

from flask import Flask

from app.api import register_api_error_handlers
from app.guards import register_guards
from app.route_groups.api_documents import register_api_documents_routes
from app.route_groups.api_jobs import register_api_jobs_routes
from app.route_groups.api_profile import register_api_profile_routes
from app.route_groups.spa import register_spa_routes
from app.route_groups.system import register_system_routes
from app.route_groups.workspace import register_workspace_routes


def register_routes(app: Flask) -> None:
    register_guards(app)
    register_api_error_handlers(app)
    register_system_routes(app)
    register_workspace_routes(app)
    register_api_jobs_routes(app)
    register_api_documents_routes(app)
    register_api_profile_routes(app)
    register_spa_routes(app)
