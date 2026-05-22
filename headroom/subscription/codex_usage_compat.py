"""Codex backend usage endpoint compatibility payloads."""

from __future__ import annotations

from typing import Any

from headroom.subscription.codex_rate_limits import (
    CodexCreditsSnapshot,
    CodexRateLimitSnapshot,
    CodexRateLimitWindow,
)


def _window_payload(window: CodexRateLimitWindow | None) -> dict[str, Any] | None:
    if window is None:
        return None
    limit_window_seconds = (
        window.window_minutes * 60 if window.window_minutes is not None else None
    )
    return {
        "used_percent": window.used_percent,
        "reset_at": window.resets_at,
        "limit_window_seconds": limit_window_seconds,
    }


def _credits_payload(credits: CodexCreditsSnapshot | None) -> dict[str, Any] | None:
    if credits is None:
        return None
    return {
        "has_credits": credits.has_credits,
        "unlimited": credits.unlimited,
        "balance": credits.balance,
    }


def codex_usage_payload_from_snapshot(
    snapshot: CodexRateLimitSnapshot | None,
) -> dict[str, Any]:
    """Render captured ``x-codex-*`` headers as ChatGPT backend usage JSON."""

    if snapshot is None:
        return {
            "rate_limit": None,
            "credits": None,
            "plan_type": None,
            "rate_limit_name": None,
            "rate_limit_reached_type": None,
            "additional_rate_limits": [],
            "spend_control": None,
            "promo": None,
        }

    return {
        "rate_limit": {
            "primary_window": _window_payload(snapshot.primary),
            "secondary_window": _window_payload(snapshot.secondary),
            "allowed": True,
            "limit_reached": False,
        },
        "credits": _credits_payload(snapshot.credits),
        "plan_type": None,
        "rate_limit_name": snapshot.limit_name,
        "rate_limit_reached_type": None,
        "additional_rate_limits": [],
        "spend_control": None,
        "promo": None,
    }
