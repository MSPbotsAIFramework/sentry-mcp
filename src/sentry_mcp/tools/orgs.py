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
"""Organizations and projects the configured token can reach."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..api_client import SentryClient
from ._common import (
    READ_ONLY,
    ClientFactory,
    Cursor,
    OrgSlug,
    ProjectSlug,
    cursor_list,
    run_tool,
)


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def sentry_list_organizations(cursor: Cursor = None) -> str:
        """List the organizations the configured Sentry Auth Token can access."""

        async def action(client: SentryClient) -> dict:
            return await cursor_list(client, "organizations/", "organizations", {}, cursor)

        return await run_tool("sentry_list_organizations", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def sentry_list_projects(organization_slug: OrgSlug, cursor: Cursor = None) -> str:
        """List an organization's projects."""

        async def action(client: SentryClient) -> dict:
            return await cursor_list(client, f"organizations/{organization_slug}/projects/", "projects", {}, cursor)

        return await run_tool("sentry_list_projects", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def sentry_get_project(organization_slug: OrgSlug, project_slug: ProjectSlug) -> str:
        """Get one project's detail (platform, teams, dateCreated)."""

        async def action(client: SentryClient) -> Any:
            return await client.get(f"projects/{organization_slug}/{project_slug}/")

        return await run_tool("sentry_get_project", client_factory, action)
