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
"""FastMCP factory and the per-request credential middleware."""

import contextvars
import re
import uuid
from collections.abc import Callable
from urllib.parse import urlsplit

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ._arguments import EnvelopeFastMCP
from .api_client import SentryClient, SentryCredentials
from .config import DEFAULT_BASE_URL, Settings

HEADER_AUTH_TOKEN = "X-Sentry-Auth-Token"
HEADER_BASE_URL = "X-Sentry-Base-URL"
REQUIRED_HEADERS = [HEADER_AUTH_TOKEN]

_PLACEHOLDER = re.compile(r"^\$\{.*\}$")
_API_SUFFIX = re.compile(r"/api(/0)?/?$", re.IGNORECASE)
_LOCAL_HOSTS = {"localhost", "127.0.0.1"}

# Per-request isolation: the middleware sets these for the duration of one
# HTTP request and resets them in `finally`. Nothing credential-related is
# ever stored at module level.
_credentials_var: contextvars.ContextVar[SentryCredentials | None] = contextvars.ContextVar(
    "sentry_credentials", default=None
)
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("sentry_request_id", default="-")

INSTRUCTIONS = (
    "Sentry is the error-tracking/observability platform: per organization it holds "
    "projects, error issues (grouped exceptions), the events that make up each "
    "issue, members, and release/deploy history.\n"
    "Usage:\n"
    "- Discover the organization first: sentry_list_organizations; its slug feeds "
    "every other tool as organization_slug (a token is not guaranteed to be "
    "scoped to exactly one organization).\n"
    "- Triage: sentry_list_issues (query defaults to is:unresolved) -> "
    "sentry_get_issue -> sentry_list_issue_events -> sentry_get_issue_event for "
    "the full stack trace. sentry_update_issue changes status/assignment/"
    "bookmark/priority; sentry_list_members resolves a name to assignedTo.\n"
    "- Releases: sentry_list_releases / sentry_get_release are read-only; "
    "sentry_create_release is upsert-by-version (safe to call again with the "
    "same version); sentry_create_deploy logs a deploy against an existing "
    "release.\n"
    "- Lists page with Sentry's own opaque cursor; pass next_cursor from the "
    "previous result to continue.\n"
    "There is no delete-issue tool: Sentry's issue lifecycle is resolve/ignore, "
    "not delete."
)


def get_client_from_context() -> SentryClient | None:
    """The client for the current request, or None outside a request."""
    credentials = _credentials_var.get()
    if credentials is None:
        return None
    return SentryClient(credentials)


def _clean(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text or _PLACEHOLDER.match(text):
        return None
    return text


def normalize_base_url(value: str) -> str | None:
    """https origin of the Sentry instance, without /api/0; None when unusable."""
    text = value.strip()
    if "://" not in text:
        text = f"https://{text}"
    parts = urlsplit(text)
    if not parts.hostname:
        return None
    if parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in _LOCAL_HOSTS):
        return None
    path = _API_SUFFIX.sub("", parts.path.rstrip("/"))
    return f"{parts.scheme}://{parts.netloc}{path}".rstrip("/")


class GatewayCredentialsMiddleware:
    """Reads X-Sentry-Auth-Token (required) and X-Sentry-Base-URL (optional) on /mcp requests."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        auth_token = _clean(request.headers.get(HEADER_AUTH_TOKEN))
        if not auth_token:
            await JSONResponse(
                {
                    "error": "Missing credentials",
                    "message": f"Missing header(s): {HEADER_AUTH_TOKEN}",
                    "required_headers": REQUIRED_HEADERS,
                },
                status_code=401,
            )(scope, receive, send)
            return

        raw_base = _clean(request.headers.get(HEADER_BASE_URL))
        base_url = DEFAULT_BASE_URL if raw_base is None else normalize_base_url(raw_base)
        if base_url is None:
            await JSONResponse(
                {"error": "Invalid base URL", "message": f"{HEADER_BASE_URL} must be the https URL of the Sentry instance"},
                status_code=400,
            )(scope, receive, send)
            return

        request_id = (request.headers.get("x-request-id") or "").strip()[:64] or uuid.uuid4().hex[:12]
        creds_token = _credentials_var.set(SentryCredentials(base_url, auth_token))
        rid_token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _credentials_var.reset(creds_token)
            request_id_var.reset(rid_token)


def create_mcp_server(settings: Settings | None = None) -> FastMCP:
    """Build the FastMCP server and register every tool."""
    mcp = EnvelopeFastMCP(
        name="sentry-mcp",
        instructions=INSTRUCTIONS,
        # The service sits behind the gateway, so Host is never localhost;
        # DNS-rebinding protection would reject those requests with 421.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        stateless_http=True,
    )

    client_factory: Callable[[], SentryClient | None] = get_client_from_context

    from .tools import events, issues, members, orgs, releases

    for module in (orgs, issues, events, members, releases):
        module.register(mcp, client_factory)

    return mcp
