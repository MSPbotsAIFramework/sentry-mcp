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
"""Release and deploy history: read, and record a new one when asked."""

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import SentryClient
from ._common import (
    READ_ONLY,
    WRITES,
    WRITES_IDEMPOTENT,
    ClientFactory,
    Cursor,
    OrgSlug,
    ReleaseVersion,
    compact,
    cursor_list,
    run_tool,
)


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def sentry_list_releases(
        organization_slug: OrgSlug,
        project: Annotated[str | None, Field(description="Limit to this project slug.")] = None,
        query: Annotated[str | None, Field(description="Free-text filter on the version string.")] = None,
        cursor: Cursor = None,
    ) -> str:
        """List an organization's releases."""

        async def action(client: SentryClient) -> dict:
            params = compact({"project": project, "query": query})
            return await cursor_list(client, f"organizations/{organization_slug}/releases/", "releases", params, cursor)

        return await run_tool("sentry_list_releases", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def sentry_get_release(organization_slug: OrgSlug, version: ReleaseVersion) -> str:
        """Get one release's detail (projects, dateCreated, dateReleased, newGroups, commitCount)."""

        async def action(client: SentryClient) -> Any:
            return await client.get(f"organizations/{organization_slug}/releases/{version}/")

        return await run_tool("sentry_get_release", client_factory, action)

    @mcp.tool(annotations=WRITES_IDEMPOTENT)
    async def sentry_create_release(
        organization_slug: OrgSlug,
        version: ReleaseVersion,
        projects: Annotated[list[str], Field(description="Project slugs this release applies to.", min_length=1)],
        ref: Annotated[str | None, Field(description="VCS ref (e.g. commit sha) for this release.")] = None,
        url: Annotated[str | None, Field(description="URL for this release.")] = None,
        date_released: Annotated[str | None, Field(description="ISO 8601 timestamp this release went live.")] = None,
    ) -> str:
        """Create a release (upsert-by-version: calling again with the same version returns the existing one)."""

        async def action(client: SentryClient) -> Any:
            body = compact(
                {"version": version, "projects": projects, "ref": ref, "url": url, "dateReleased": date_released}
            )
            return await client.post(f"organizations/{organization_slug}/releases/", body)

        return await run_tool("sentry_create_release", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def sentry_create_deploy(
        organization_slug: OrgSlug,
        version: ReleaseVersion,
        environment: Annotated[str, Field(description='Deploy environment, e.g. "production".', min_length=1)],
        name: Annotated[str | None, Field(description="Deploy name.")] = None,
        url: Annotated[str | None, Field(description="URL for this deploy.")] = None,
        date_started: Annotated[str | None, Field(description="ISO 8601 timestamp the deploy started.")] = None,
        date_finished: Annotated[str | None, Field(description="ISO 8601 timestamp the deploy finished.")] = None,
        projects: Annotated[list[str] | None, Field(description="Project slugs this deploy applies to.")] = None,
    ) -> str:
        """Create a deploy record for an existing release."""

        async def action(client: SentryClient) -> Any:
            body = compact(
                {
                    "environment": environment,
                    "name": name,
                    "url": url,
                    "dateStarted": date_started,
                    "dateFinished": date_finished,
                    "projects": projects,
                }
            )
            return await client.post(f"organizations/{organization_slug}/releases/{version}/deploys/", body)

        return await run_tool("sentry_create_deploy", client_factory, action)
