"""Typed per-user UI preferences: swipe mapping, deck filter and glass intensity (ADR-013)."""

from __future__ import annotations

import logging
import sqlite3
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from core.repositories.preferences import read_sections, write_sections

logger = logging.getLogger(__name__)

SwipeAction = Literal["skip", "generate_resume", "generate_resume_and_cover_letter", "waitlist", "details", "none"]


class SwipeMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: SwipeAction = "skip"
    right: SwipeAction = "generate_resume"
    up: SwipeAction = "waitlist"
    down: SwipeAction = "details"

    @model_validator(mode="after")
    def _distinct_actions(self) -> SwipeMapping:
        used = [a for a in (self.left, self.right, self.up, self.down) if a != "none"]
        if len(used) != len(set(used)):
            raise ValueError("each action can be assigned to one direction only (use 'none' to leave one unassigned)")
        return self


class DeckPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_score: int = Field(
        default=70, ge=0, le=100, description="Only jobs at or above this match score enter the deck"
    )
    mouse_drag: bool = True
    buttons: bool = True


class UiPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    glass: Literal["auto", "subtle", "medium", "medium_plus", "strong"] = "auto"


class UserPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    swipe: SwipeMapping = Field(default_factory=lambda: SwipeMapping())
    deck: DeckPreferences = Field(default_factory=lambda: DeckPreferences())
    ui: UiPreferences = Field(default_factory=lambda: UiPreferences())


_SECTIONS: dict[str, type[BaseModel]] = {"swipe": SwipeMapping, "deck": DeckPreferences, "ui": UiPreferences}


def get_preferences(conn: sqlite3.Connection, user_id: int) -> UserPreferences:
    """Stored sections merged over the defaults; an unreadable section falls back to its defaults."""
    stored = read_sections(conn, user_id)
    values: dict[str, BaseModel] = {}
    for key, model in _SECTIONS.items():
        raw = stored.get(key)
        if raw is None:
            continue
        try:
            values[key] = model.model_validate_json(raw)
        except ValidationError:
            logger.warning("Ignoring invalid stored preference section %s for user %s", key, user_id)
    return UserPreferences(**values)  # type: ignore[arg-type]


def save_preferences(conn: sqlite3.Connection, user_id: int, preferences: UserPreferences) -> UserPreferences:
    write_sections(conn, user_id, {key: getattr(preferences, key).model_dump_json() for key in _SECTIONS})
    return preferences
