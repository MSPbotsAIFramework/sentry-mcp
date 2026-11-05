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
"""The individual events (occurrences) behind an issue."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..api_client import SentryClient
from ._common import READ_ONLY, ClientFactory, Cursor, EventId, IssueId, Limit, OrgSlug, cursor_list, run_tool


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def sentry_list_issue_events(
        organization_slug: OrgSlug, issue_id: IssueId, cursor: Cursor = None, per_page: Limit = None
    ) -> str:
        """List the events that make up one issue."""

        async def action(client: SentryClient) -> dict:
            return await cursor_list(
                client,
                f"organizations/{organization_slug}/issues/{issue_id}/events/",
                "events",
                {},
                cursor,
                "per_page",
                per_page,
            )

        return await run_tool("sentry_list_issue_events", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def sentry_get_issue_event(organization_slug: OrgSlug, issue_id: IssueId, event_id: EventId) -> str:
        """Get one event's full detail: exception/stacktrace entries, tags, user, contexts."""

        async def action(client: SentryClient) -> Any:
            return await client.get(f"organizations/{organization_slug}/issues/{issue_id}/events/{event_id}/")

        return await run_tool("sentry_get_issue_event", client_factory, action)
