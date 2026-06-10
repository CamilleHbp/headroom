import httpx
import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from headroom.proxy.server import ProxyConfig, create_app
from headroom.subscription.codex_rate_limits import (
    get_codex_rate_limit_state,
    parse_codex_rate_limits,
)
from headroom.subscription.codex_usage_compat import codex_usage_payload_from_snapshot


@pytest.fixture(autouse=True)
def reset_codex_rate_limit_state():
    state = get_codex_rate_limit_state()
    with state._lock:
        state._latest = None
    yield
    with state._lock:
        state._latest = None


def test_codex_usage_payload_from_header_snapshot_uses_backend_usage_shape():
    snapshot = parse_codex_rate_limits(
        {
            "x-codex-primary-used-percent": "42.5",
            "x-codex-primary-window-minutes": "300",
            "x-codex-primary-reset-at": "1779440000",
            "x-codex-secondary-used-percent": "12",
            "x-codex-secondary-window-minutes": "10080",
            "x-codex-credits-has-credits": "true",
            "x-codex-credits-balance": "$5.00",
        }
    )

    payload = codex_usage_payload_from_snapshot(snapshot)

    assert payload["rate_limit"]["primary_window"]["used_percent"] == 42.5
    assert payload["rate_limit"]["primary_window"]["limit_window_seconds"] == 18_000
    assert payload["rate_limit"]["secondary_window"]["limit_window_seconds"] == 604_800
    assert payload["rate_limit"]["allowed"] is True
    assert payload["rate_limit"]["limit_reached"] is False
    assert payload["credits"]["balance"] == "$5.00"
    assert payload["additional_rate_limits"] == []
    assert payload["rate_limit_reached_type"] is None


def test_codex_usage_route_serves_empty_payload_without_auth(monkeypatch, tmp_path):
    class FakeAsyncClient:
        def __init__(self):
            self.calls: list[tuple[str, str]] = []

        async def request(self, method, url, **kwargs):  # noqa: ANN001
            self.calls.append((method, url))
            return httpx.Response(401, json={"detail": "Unauthorized"})

        async def aclose(self):
            return None

    monkeypatch.setenv("CODEX_HOME", str(tmp_path))

    with TestClient(create_app(ProxyConfig())) as client:
        fake_http_client = FakeAsyncClient()
        client.app.state.proxy.http_client = fake_http_client

        response = client.get("/v1/wham/usage")

    assert response.status_code == 200
    assert response.headers["x-headroom-codex-usage-source"] == "empty"
    assert response.json()["rate_limit"] is None
    assert fake_http_client.calls == []


def test_codex_usage_route_uses_local_codex_auth_when_request_has_no_auth(
    monkeypatch,
    tmp_path,
):
    (tmp_path / "auth.json").write_text(
        """
        {
          "tokens": {
            "access_token": "test-access-token",
            "account_id": "acct_123"
          }
        }
        """,
        encoding="utf-8",
    )

    class FakeAsyncClient:
        def __init__(self):
            self.calls: list[tuple[str, str, dict[str, str]]] = []

        async def request(self, method, url, **kwargs):  # noqa: ANN001
            self.calls.append((method, url, dict(kwargs["headers"])))
            return httpx.Response(200, json={"rate_limit": {"allowed": True}})

        async def aclose(self):
            return None

    monkeypatch.setenv("CODEX_HOME", str(tmp_path))

    with TestClient(create_app(ProxyConfig())) as client:
        fake_http_client = FakeAsyncClient()
        client.app.state.proxy.http_client = fake_http_client

        response = client.get("/v1/wham/usage")

    assert response.status_code == 200
    assert response.json()["rate_limit"]["allowed"] is True
    assert fake_http_client.calls == [
        (
            "GET",
            "https://chatgpt.com/backend-api/wham/usage",
            {
                "authorization": "Bearer test-access-token",
                "ChatGPT-Account-ID": "acct_123",
            },
        )
    ]


def test_codex_usage_routes_normalize_v1_prefixed_usage_paths():
    class FakeAsyncClient:
        def __init__(self):
            self.calls: list[tuple[str, str]] = []

        async def request(self, method, url, **kwargs):  # noqa: ANN001
            self.calls.append((method, url))
            return httpx.Response(200, json={"rate_limit": None})

        async def aclose(self):
            return None

    with TestClient(create_app(ProxyConfig())) as client:
        fake_http_client = FakeAsyncClient()
        client.app.state.proxy.http_client = fake_http_client

        headers = {"ChatGPT-Account-ID": "acct_123"}
        assert client.get("/v1/wham/usage", headers=headers).status_code == 200
        assert client.get("/v1/api/codex/usage", headers=headers).status_code == 200
        assert client.get("/backend-api/wham/usage", headers=headers).status_code == 200

    assert fake_http_client.calls == [
        ("GET", "https://chatgpt.com/backend-api/wham/usage"),
        ("GET", "https://chatgpt.com/api/codex/usage"),
        ("GET", "https://chatgpt.com/backend-api/wham/usage"),
    ]


def test_codex_usage_route_falls_back_to_latest_snapshot(monkeypatch):
    from headroom.providers import proxy_routes

    class FakeAsyncClient:
        async def request(self, method, url, **kwargs):  # noqa: ANN001
            return httpx.Response(503, json={"error": "upstream unavailable"})

        async def aclose(self):
            return None

    monkeypatch.setattr(
        proxy_routes,
        "_codex_usage_snapshot_response",
        lambda: JSONResponse(
            {"rate_limit": {"primary_window": {"used_percent": 10}}},
            headers={"x-headroom-codex-usage-source": "snapshot"},
        ),
    )

    with TestClient(create_app(ProxyConfig())) as client:
        client.app.state.proxy.http_client = FakeAsyncClient()

        response = client.get("/v1/wham/usage", headers={"ChatGPT-Account-ID": "acct_123"})

    assert response.status_code == 200
    assert response.headers["x-headroom-codex-usage-source"] == "snapshot"
    assert response.json()["rate_limit"]["primary_window"]["used_percent"] == 10
