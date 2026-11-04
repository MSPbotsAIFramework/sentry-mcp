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
"""Error issue triage: list, inspect, update."""

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import SentryClient
from ._common import (
    READ_ONLY,
    WRITES,
    ClientFactory,
    Cursor,
    IssueId,
    Limit,
    OrgSlug,
    compact,
    cursor_list,
    require,
    run_tool,
)

IssueStatus = Literal["resolved", "unresolved", "ignored", "resolvedInNextRelease"]
IssuePriority = Literal["low", "medium", "high"]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def sentry_list_issues(
        organization_slug: OrgSlug,
        project: Annotated[list[str] | None, Field(description="Limit to these project slugs.")] = None,
        query: Annotated[str | None, Field(description='Sentry search syntax, e.g. "is:unresolved level:error". Defaults to "is:unresolved"; pass "" for every status.')] = None,
        sort: Annotated[str | None, Field(description='Sort order, e.g. "date", "new", "priority", "freq".')] = None,
        cursor: Cursor = None,
        limit: Limit = None,
    ) -> str:
        """List issues matching Sentry's search syntax (default is:unresolved)."""

        async def action(client: SentryClient) -> dict:
            params = compact({"project": project, "query": query if query is not None else "is:unresolved", "sort": sort})
            return await cursor_list(
                client, f"organizations/{organization_slug}/issues/", "issues", params, cursor, "limit", limit
            )

        return await run_tool("sentry_list_issues", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def sentry_get_issue(organization_slug: OrgSlug, issue_id: IssueId) -> str:
        """Get one issue's detail: title, culprit, status, level, counts, firstSeen/lastSeen, assignedTo."""

        async def action(client: SentryClient) -> Any:
            return await client.get(f"organizations/{organization_slug}/issues/{issue_id}/")

        return await run_tool("sentry_get_issue", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def sentry_update_issue(
        organization_slug: OrgSlug,
        issue_id: IssueId,
        status: Annotated[IssueStatus | None, Field(description="New issue status.")] = None,
        assigned_to: Annotated[str | None, Field(description="Username, email, or team to assign the issue to.")] = None,
        is_bookmarked: Annotated[bool | None, Field(description="Bookmark (true) or unbookmark (false) the issue.")] = None,
        priority: Annotated[IssuePriority | None, Field(description="New issue priority.")] = None,
    ) -> str:
        """Change one or more of status/assignedTo/isBookmarked/priority. Fields not passed are left unchanged."""

        async def action(client: SentryClient) -> Any:
            body = require(
                compact(
                    {
                        "status": status,
                        "assignedTo": assigned_to,
                        "isBookmarked": is_bookmarked,
                        "priority": priority,
                    }
                )
            )
            return await client.put(f"organizations/{organization_slug}/issues/{issue_id}/", body)

        return await run_tool("sentry_update_issue", client_factory, action)
