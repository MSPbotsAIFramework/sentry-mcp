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
"""Organization members, to resolve a human name into an issue's assignedTo value."""

from mcp.server.fastmcp import FastMCP

from ..api_client import SentryClient
from ._common import READ_ONLY, ClientFactory, Cursor, OrgSlug, cursor_list, run_tool


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def sentry_list_members(organization_slug: OrgSlug, cursor: Cursor = None) -> str:
        """List an organization's members (id, email, name, orgRole, pending)."""

        async def action(client: SentryClient) -> dict:
            return await cursor_list(client, f"organizations/{organization_slug}/members/", "members", {}, cursor)

        return await run_tool("sentry_list_members", client_factory, action)
