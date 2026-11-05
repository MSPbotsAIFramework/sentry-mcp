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
"""Shared argument types, cursor pagination and the error-handling wrapper."""

import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.types import ToolAnnotations
from pydantic import Field

from .._json import dump_json_capped, error_envelope
from ..api_client import SentryClient, SentryError
from ..config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

logger = logging.getLogger("sentry_mcp.tools")

ClientFactory = Callable[[], SentryClient | None]

# No DESTRUCTIVE tool in v1: Sentry's documented issue lifecycle is
# resolve/ignore, not delete (see "Decisions made by DEV01").
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
WRITES_IDEMPOTENT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)

NOT_CONFIGURED = error_envelope(
    "not_configured", "Sentry credentials are missing for this request (X-Sentry-Auth-Token).", False
)

OrgSlug = Annotated[str, Field(description="Organization slug, from sentry_list_organizations.", min_length=1)]
ProjectSlug = Annotated[str, Field(description="Project slug, from sentry_list_projects.", min_length=1)]
IssueId = Annotated[str, Field(description="Issue id, from sentry_list_issues or sentry_get_issue.", min_length=1)]
EventId = Annotated[str, Field(description="Event id, from sentry_list_issue_events.", min_length=1)]
ReleaseVersion = Annotated[str, Field(description="Release version string.", min_length=1)]
Cursor = Annotated[str | None, Field(description="Opaque pagination cursor from a previous call's next_cursor.")]
Limit = Annotated[int | None, Field(description=f"Records per page (default {DEFAULT_PAGE_SIZE}, max {MAX_PAGE_SIZE}).", ge=1, le=MAX_PAGE_SIZE)]


def compact(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


def require(body: dict) -> dict:
    if not body:
        raise ValueError("Nothing to update: pass at least one field to change.")
    return body


_LINK_ENTRY = re.compile(r'<([^>]*)>\s*((?:;\s*[a-zA-Z]+="[^"]*")*)')
_LINK_PARAM = re.compile(r'([a-zA-Z]+)="([^"]*)"')


def _next_cursor(link_header: str | None) -> str | None:
    """Sentry's own opaque cursor from the Link response header's rel="next" entry.

    Format: ``<url>; rel="previous"; results="false"; cursor="0:0:1", <url>; rel="next"; results="true"; cursor="0:100:0"``.
    ``results="false"`` means that direction has no more records, so only a
    ``results="true"`` next entry is worth returning to the caller.
    """
    if not link_header:
        return None
    for _url, params_str in _LINK_ENTRY.findall(link_header):
        params = dict(_LINK_PARAM.findall(params_str))
        if params.get("rel") == "next" and params.get("results") == "true":
            return params.get("cursor")
    return None


async def cursor_list(
    client: SentryClient,
    path: str,
    key: str,
    params: dict[str, Any],
    cursor: str | None,
    size_param: str | None = None,
    size: int | None = None,
) -> dict:
    """GET a cursor-paginated list endpoint and return {<key>, next_cursor}.

    Sentry's list endpoints return a plain JSON array; the next page's cursor
    (if any) comes from the ``Link`` response header, not the body.
    """
    query = compact(params)
    if cursor:
        query["cursor"] = cursor
    if size_param and size:
        query[size_param] = size
    payload, resp = await client.request("GET", path, params=query)
    items = payload if isinstance(payload, list) else (payload.get(key) if isinstance(payload, dict) else [])
    items = items if isinstance(items, list) else []
    return compact({key: items, "next_cursor": _next_cursor(resp.headers.get("Link"))})


async def run_tool(
    name: str,
    client_factory: ClientFactory,
    action: Callable[[SentryClient], Awaitable[Any]],
) -> str:
    """Resolve the caller's client, run ``action``, and always return a string.

    Errors never escape as exceptions: they become the standard error envelope.
    """
    client = client_factory()
    if client is None:
        return NOT_CONFIGURED
    started = time.monotonic()
    try:
        result = await action(client)
    except SentryError as e:
        logger.info("tool=%s outcome=error status=%s ms=%d", name, e.status_code, _ms(started))
        return e.to_envelope()
    except ValueError as e:
        logger.info("tool=%s outcome=invalid_argument ms=%d", name, _ms(started))
        return error_envelope("invalid_argument", str(e), False)
    except Exception as e:  # noqa: BLE001 - tools must never raise
        logger.warning("tool=%s outcome=unexpected error=%s ms=%d", name, type(e).__name__, _ms(started))
        return error_envelope("upstream_error", f"Unexpected error: {type(e).__name__}", True)
    logger.info("tool=%s outcome=ok ms=%d", name, _ms(started))
    if result is None:
        result = {"done": True}
    return result if isinstance(result, str) else dump_json_capped(result)


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
