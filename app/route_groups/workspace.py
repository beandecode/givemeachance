"""Personal workspace resources of the /api/v1 contract; see docs/api.md."""

from __future__ import annotations

from flask import Flask

from app.api import ApiContext, api_route
from app.api_models import Journey, JourneyUpdate, Overview, ProfileSnapshot, SearchPreferences, SearchSuggestion
from core.journey_service import get_journey, set_journey_skipped
from core.preferences_service import UserPreferences, get_preferences, save_preferences
from core.schemas import JobSearchConfig
from core.search_preferences import (
    get_effective_search_config,
    suggest_search_config,
    upsert_user_search_preferences,
)
from core.suggestions_service import search_suggestions
from core.workspace_service import overview, profile_snapshot


def register_workspace_routes(app: Flask) -> None:
    @api_route(
        app,
        "GET",
        "/api/v1/overview",
        summary="Personal summary, profile gate and today's quota",
        tag="workspace",
        response=Overview,
    )
    def workspace_overview(ctx: ApiContext):
        return overview(ctx.conn, ctx.settings, ctx.user_id)

    @api_route(
        app,
        "GET",
        "/api/v1/profile",
        summary="Latest Master Profile and readiness",
        tag="profile",
        response=ProfileSnapshot,
    )
    def workspace_profile(ctx: ApiContext):
        return profile_snapshot(ctx.conn, ctx.user_id)

    @api_route(
        app,
        "GET",
        "/api/v1/search-preferences",
        summary="Effective job search settings",
        tag="search",
        response=SearchPreferences,
    )
    def workspace_search_preferences(ctx: ApiContext):
        config, source = get_effective_search_config(ctx.conn, ctx.user_id)
        return {"config": config, "source": source}

    @api_route(
        app,
        "PUT",
        "/api/v1/search-preferences",
        summary="Replace own job search settings",
        tag="search",
        body=JobSearchConfig,
        response=SearchPreferences,
    )
    def workspace_save_search_preferences(ctx: ApiContext, body: JobSearchConfig):
        upsert_user_search_preferences(ctx.conn, ctx.user_id, body)
        return {"config": body, "source": "user"}

    @api_route(
        app,
        "GET",
        "/api/v1/search-preferences/suggested",
        summary="Search settings prefilled from the latest Master Profile (not saved)",
        tag="search",
        response=SearchPreferences,
    )
    def api_suggested_search_preferences(ctx: ApiContext):
        return {"config": suggest_search_config(ctx.conn, ctx.user_id), "source": "suggested"}

    @api_route(
        app,
        "GET",
        "/api/v1/preferences",
        summary="Swipe mapping, deck filter and look settings",
        tag="workspace",
        response=UserPreferences,
    )
    def api_get_preferences(ctx: ApiContext):
        return get_preferences(ctx.conn, ctx.user_id)

    @api_route(
        app,
        "PUT",
        "/api/v1/preferences",
        summary="Replace own swipe mapping, deck filter and look settings",
        tag="workspace",
        body=UserPreferences,
        response=UserPreferences,
    )
    def api_save_preferences(ctx: ApiContext, body: UserPreferences):
        return save_preferences(ctx.conn, ctx.user_id, body)

    @api_route(
        app,
        "GET",
        "/api/v1/journey",
        summary="Setup steps, the current one, and why the Discover deck is empty",
        tag="workspace",
        response=Journey,
    )
    def api_get_journey(ctx: ApiContext):
        return get_journey(ctx.conn, ctx.user_id)

    @api_route(
        app,
        "PUT",
        "/api/v1/journey",
        summary="Hide or show the setup guide",
        tag="workspace",
        body=JourneyUpdate,
        response=Journey,
    )
    def api_update_journey(ctx: ApiContext, body: JourneyUpdate):
        set_journey_skipped(ctx.conn, ctx.user_id, body.skipped)
        return get_journey(ctx.conn, ctx.user_id)

    @api_route(
        app,
        "GET",
        "/api/v1/search-suggestions",
        summary="Search settings suggested by the reasons you gave for skipping jobs (never applied automatically)",
        tag="search",
        response=list[SearchSuggestion],
    )
    def api_search_suggestions(ctx: ApiContext):
        return search_suggestions(ctx.conn, ctx.user_id)
