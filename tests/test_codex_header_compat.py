"""Tests for Codex quota header compatibility helpers."""

from headroom.subscription.codex_header_compat import (
    attach_latest_codex_rate_limit_headers,
    headers_from_snapshot,
)
from headroom.subscription.codex_rate_limits import (
    get_codex_rate_limit_state,
    parse_codex_rate_limits,
)


def test_headers_from_snapshot_renders_legacy_codex_headers() -> None:
    snapshot = parse_codex_rate_limits(
        {
            "x-codex-limit-name": "gpt-5.2-codex-sonic",
            "x-codex-primary-used-percent": "42.5",
            "x-codex-primary-window-minutes": "300",
            "x-codex-primary-reset-at": "1704069000",
            "x-codex-secondary-used-percent": "12.0",
            "x-codex-secondary-window-minutes": "10080",
            "x-codex-secondary-reset-at": "1704670200",
            "x-codex-credits-has-credits": "true",
            "x-codex-credits-unlimited": "false",
            "x-codex-credits-balance": "$5.00",
            "x-codex-promo-message": "Try our new model!",
        }
    )

    headers = headers_from_snapshot(snapshot)

    assert headers["x-codex-limit-name"] == "gpt-5.2-codex-sonic"
    assert headers["x-codex-primary-used-percent"] == "42.5"
    assert headers["x-codex-primary-window-minutes"] == "300"
    assert headers["x-codex-secondary-window-minutes"] == "10080"
    assert headers["x-codex-credits-has-credits"] == "true"
    assert headers["x-codex-credits-unlimited"] == "false"
    assert headers["x-codex-credits-balance"] == "$5.00"
    assert headers["x-codex-promo-message"] == "Try our new model!"


def test_attach_latest_codex_rate_limit_headers_preserves_upstream_values() -> None:
    get_codex_rate_limit_state().update_from_headers(
        {
            "x-codex-primary-used-percent": "42.5",
            "x-codex-primary-window-minutes": "300",
            "x-codex-secondary-used-percent": "12.0",
            "x-codex-secondary-window-minutes": "10080",
            "x-codex-credits-has-credits": "true",
            "x-codex-credits-unlimited": "true",
        }
    )
    response_headers = {
        "content-type": "text/event-stream",
        "x-codex-primary-used-percent": "43.0",
    }

    attach_latest_codex_rate_limit_headers(response_headers)

    assert response_headers["x-codex-primary-used-percent"] == "43.0"
    assert response_headers["x-codex-primary-window-minutes"] == "300"
    assert response_headers["x-codex-secondary-used-percent"] == "12.0"
    assert response_headers["x-codex-secondary-window-minutes"] == "10080"
    assert response_headers["x-codex-credits-has-credits"] == "true"
    assert response_headers["x-codex-credits-unlimited"] == "true"
