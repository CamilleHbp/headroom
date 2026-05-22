"""Compatibility helpers for Codex clients that render quota from headers."""

from __future__ import annotations

from headroom.subscription.codex_rate_limits import (
    CodexRateLimitSnapshot,
    CodexRateLimitWindow,
    get_codex_rate_limit_state,
)


def _format_header_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _headers_from_window(prefix: str, window: CodexRateLimitWindow | None) -> dict[str, str]:
    if window is None:
        return {}

    headers: dict[str, str] = {}
    for suffix, value in (
        ("used-percent", window.used_percent),
        ("window-minutes", window.window_minutes),
        ("reset-at", window.resets_at),
    ):
        formatted = _format_header_value(value)
        if formatted is not None:
            headers[f"x-codex-{prefix}-{suffix}"] = formatted
    return headers


def headers_from_snapshot(snapshot: CodexRateLimitSnapshot | None) -> dict[str, str]:
    """Render a Codex rate-limit snapshot as legacy ``x-codex-*`` headers."""
    if snapshot is None:
        return {}

    headers: dict[str, str] = {}

    limit_name = _format_header_value(snapshot.limit_name)
    if limit_name is not None:
        headers["x-codex-limit-name"] = limit_name

    headers.update(_headers_from_window("primary", snapshot.primary))
    headers.update(_headers_from_window("secondary", snapshot.secondary))

    if snapshot.credits is not None:
        for suffix, value in (
            ("has-credits", snapshot.credits.has_credits),
            ("unlimited", snapshot.credits.unlimited),
            ("balance", snapshot.credits.balance),
        ):
            formatted = _format_header_value(value)
            if formatted is not None:
                headers[f"x-codex-credits-{suffix}"] = formatted

    promo_message = _format_header_value(snapshot.promo_message)
    if promo_message is not None:
        headers["x-codex-promo-message"] = promo_message

    return headers


def attach_latest_codex_rate_limit_headers(headers: dict[str, str]) -> None:
    """Fill missing Codex quota headers from Headroom's latest snapshot.

    Upstream headers are preserved. This only backfills missing values so a
    newer upstream contract cannot be overwritten by stale local state.
    """
    latest = get_codex_rate_limit_state().latest
    latest_headers = headers_from_snapshot(latest)
    if not latest_headers:
        return

    existing = {name.lower() for name in headers}
    for name, value in latest_headers.items():
        if name.lower() not in existing:
            headers[name] = value
