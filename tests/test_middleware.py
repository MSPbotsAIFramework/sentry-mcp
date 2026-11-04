# Copyright 2026 MSPbots.ai
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Credential middleware: 401 on missing token, base-URL default/validation, isolation."""

import asyncio

import pytest
from starlette.testclient import TestClient

from sentry_mcp.__main__ import build_http_app
from sentry_mcp.server import (
    GatewayCredentialsMiddleware,
    _credentials_var,
    create_mcp_server,
    get_client_from_context,
    normalize_base_url,
)

MCP_HEADERS = {"Accept": "application/json, text/event-stream"}
LIST_TOOLS = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
CREDS = {"X-Sentry-Auth-Token": "token-123"}


def _client() -> TestClient:
    return TestClient(build_http_app(create_mcp_server()))


def test_health_is_local():
    with _client() as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.parametrize("headers", [{}, {"X-Sentry-Auth-Token": "${SENTRY_TOKEN}"}, {"X-Sentry-Auth-Token": "  "}])
def test_missing_header_returns_401(headers):
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS | headers)
    assert resp.status_code == 401
    assert resp.json()["required_headers"] == ["X-Sentry-Auth-Token"]


def test_invalid_base_url_returns_400():
    with _client() as client:
        resp = client.post(
            "/mcp", json=LIST_TOOLS, headers=MCP_HEADERS | CREDS | {"X-Sentry-Base-URL": "http://self-hosted.example.com"}
        )
    assert resp.status_code == 400


@pytest.mark.parametrize(
    "value,expected",
    [
        ("https://sentry.example.com", "https://sentry.example.com"),
        ("sentry.example.com/", "https://sentry.example.com"),
        ("https://sentry.example.com/api/0", "https://sentry.example.com"),
        ("https://sentry.example.com/api/0/", "https://sentry.example.com"),
        ("https://example.com/sentry", "https://example.com/sentry"),
        ("http://sentry.example.com", None),
        ("https://", None),
    ],
)
def test_normalize_base_url(value, expected):
    assert normalize_base_url(value) == expected


def test_tools_list_over_http():
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS | CREDS)
    assert resp.status_code == 200
    for name in ("sentry_list_organizations", "sentry_update_issue", "sentry_create_deploy"):
        assert name in resp.text


def _run_middleware(headers: list[tuple[bytes, bytes]]) -> dict:
    seen: dict = {}

    async def app(scope, receive, send):
        seen["credentials"] = _credentials_var.get()
        seen["client"] = get_client_from_context()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    asyncio.run(GatewayCredentialsMiddleware(app)({"type": "http", "path": "/mcp", "headers": headers}, receive, send))
    return seen


def test_credentials_reach_request_context_and_are_reset():
    seen = _run_middleware([(b"x-sentry-auth-token", b" token-abc ")])
    client = seen["client"]
    assert client.base_url == "https://sentry.io/api/0"
    assert client._headers()["Authorization"] == "Bearer token-abc"
    assert _credentials_var.get() is None


def test_base_url_header_overrides_default():
    seen = _run_middleware([(b"x-sentry-auth-token", b"token-abc"), (b"x-sentry-base-url", b"https://self-hosted.example.com/api/0/")])
    assert seen["client"].base_url == "https://self-hosted.example.com/api/0"


def test_concurrent_requests_isolate_credentials():
    observed: list[tuple[str, str]] = []

    async def app(scope, receive, send):
        before = _credentials_var.get().auth_token
        await asyncio.sleep(0.01)
        observed.append((before, _credentials_var.get().auth_token))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    middleware = GatewayCredentialsMiddleware(app)

    def scope(token: bytes) -> dict:
        return {"type": "http", "path": "/mcp", "headers": [(b"x-sentry-auth-token", token)]}

    async def both():
        await asyncio.gather(middleware(scope(b"tenant-a"), receive, send), middleware(scope(b"tenant-b"), receive, send))

    asyncio.run(both())
    assert sorted(observed) == [("tenant-a", "tenant-a"), ("tenant-b", "tenant-b")]


def test_credentials_repr_hides_token():
    seen = _run_middleware([(b"x-sentry-auth-token", b"very-secret-token")])
    assert "very-secret-token" not in repr(seen["credentials"])
