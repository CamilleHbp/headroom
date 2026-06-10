"""Compatibility payloads for Codex usage polling endpoints."""

from __future__ import annotations

from typing import Any

from headroom.subscription.codex_rate_limits import CodexRateLimitSnapshot


def _window_payload(window: Any) -> dict[str, Any] | None:
    if window is None:
        return None
    return {
        "used_percent": window.used_percent,
        "limit_window_seconds": window.window_minutes * 60
        if window.window_minutes is not None
        else None,
        "resets_at": window.resets_at,
        "seconds_until_reset": window.seconds_until_reset,
    }


def codex_usage_payload_from_snapshot(
    snapshot: CodexRateLimitSnapshot | None,
) -> dict[str, Any]:
    """Return a ChatGPT usage-shaped response from passive Codex headers."""

    if snapshot is None:
        return {
            "rate_limit": None,
            "credits": None,
            "additional_rate_limits": [],
            "rate_limit_reached_type": None,
        }

    primary = _window_payload(snapshot.primary)
    secondary = _window_payload(snapshot.secondary)
    used_percent = primary["used_percent"] if primary is not None else None
    limit_reached = used_percent is not None and used_percent >= 100.0

    credits = None
    if snapshot.credits is not None:
        credits = {
            "has_credits": snapshot.credits.has_credits,
            "unlimited": snapshot.credits.unlimited,
            "balance": snapshot.credits.balance,
        }

    return {
        "rate_limit": {
            "allowed": not limit_reached,
            "limit_reached": limit_reached,
            "primary_window": primary,
            "secondary_window": secondary,
        },
        "credits": credits,
        "additional_rate_limits": [],
        "rate_limit_reached_type": "primary" if limit_reached else None,
        "promo_message": snapshot.promo_message,
        "limit_name": snapshot.limit_name,
    }
