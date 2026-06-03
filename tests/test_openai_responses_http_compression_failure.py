"""Regression tests for HTTP /v1/responses compression failures."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from starlette.requests import Request

from headroom.proxy.handlers.openai import OpenAIHandlerMixin


class _Metrics:
    async def record_failed(self, **_kwargs: Any) -> None:
        pass

    async def record_rate_limited(self, **_kwargs: Any) -> None:
        pass


class _SessionTrackerStore:
    def compute_session_id(self, *_args: Any, **_kwargs: Any) -> str:
        return "session-http-compression-timeout"


class _HTTPResponsesHandler(OpenAIHandlerMixin):
    OPENAI_API_URL = "https://api.openai.test"

    def __init__(self) -> None:
        self.config = SimpleNamespace(
            optimize=True,
            retry_max_attempts=1,
            retry_base_delay_ms=1,
            retry_max_delay_ms=1,
            connect_timeout_seconds=10,
            log_full_messages=False,
        )
        self.metrics = _Metrics()
        self.rate_limiter = None
        self.memory_handler = None
        self.anthropic_backend = None
        self.cost_tracker = None
        self.session_tracker_store = _SessionTrackerStore()
        self.retry_calls: list[dict[str, Any]] = []

    async def _next_request_id(self) -> str:
        return "req-http-compression-timeout"

    async def _compress_openai_responses_payload_in_executor(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> tuple[Any, bool, int, list[str], str, int, int, int, dict[str, float]]:
        raise asyncio.TimeoutError("compression timeout on a 1124935-byte request")

    async def _retry_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
    ) -> httpx.Response:
        self.retry_calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "body": body,
            }
        )
        return httpx.Response(
            200,
            json={
                "id": "resp-test",
                "output": [],
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 3,
                    "total_tokens": 15,
                },
            },
            headers={"content-type": "application/json"},
        )

    async def _record_request_outcome(self, _outcome: Any) -> None:
        pass


def _request_for_json(payload: dict[str, Any]) -> Request:
    body = json.dumps(payload).encode("utf-8")

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/v1/responses",
            "raw_path": b"/v1/responses",
            "query_string": b"",
            "headers": [
                (b"authorization", b"Bearer sk-test"),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        },
        receive,
    )


@pytest.mark.anyio
async def test_http_responses_compression_timeout_forwards_original_request() -> None:
    payload = {
        "model": "gpt-5",
        "input": [{"type": "message", "role": "user", "content": "hello"}],
    }
    handler = _HTTPResponsesHandler()

    response = await handler.handle_openai_responses(_request_for_json(payload))

    assert response.status_code == 200
    assert handler.retry_calls
    assert handler.retry_calls[0]["method"] == "POST"
    assert handler.retry_calls[0]["body"] == payload
