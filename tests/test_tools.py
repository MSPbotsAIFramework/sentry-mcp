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
"""tools/list snapshot, error-envelope mapping, and json-capping. No network access."""

import asyncio
import json

import pytest

from sentry_mcp._json import MAX_CHARS, dump_json_capped
from sentry_mcp.api_client import SentryCredentials, SentryError
from sentry_mcp.server import INSTRUCTIONS, create_mcp_server

ORG = {"organization_slug"}
ORG_ISSUE = {"organization_slug", "issue_id"}

# Tool names are a public contract: existing agents and tenant connections
# depend on them. Changing this snapshot is a breaking change (SOP §13).
EXPECTED_TOOLS: dict[str, set[str]] = {
    "sentry_list_organizations": set(),
    "sentry_list_projects": ORG,
    "sentry_get_project": {"organization_slug", "project_slug"},
    "sentry_list_issues": ORG,
    "sentry_get_issue": ORG_ISSUE,
    "sentry_update_issue": ORG_ISSUE,
    "sentry_list_issue_events": ORG_ISSUE,
    "sentry_get_issue_event": {"organization_slug", "issue_id", "event_id"},
    "sentry_list_members": ORG,
    "sentry_list_releases": ORG,
    "sentry_get_release": {"organization_slug", "version"},
    "sentry_create_release": {"organization_slug", "version", "projects"},
    "sentry_create_deploy": {"organization_slug", "version", "environment"},
}
READ_TOOLS = {n for n in EXPECTED_TOOLS if n.startswith(("sentry_list_", "sentry_get_"))}
WRITE_TOOLS = set(EXPECTED_TOOLS) - READ_TOOLS


@pytest.fixture(scope="module")
def tools():
    return {t.name: t for t in asyncio.run(create_mcp_server().list_tools())}


def test_tool_names_are_stable(tools):
    assert set(tools) == set(EXPECTED_TOOLS)


def test_tool_count_within_budget(tools):
    # SOP §2: a single service should expose at most 20 tools.
    assert len(tools) == 13


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_required_params(tools, name):
    assert set(tools[name].inputSchema.get("required", [])) == EXPECTED_TOOLS[name]


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_description_budget(tools, name):
    description = (tools[name].description or "").strip()
    assert description, f"{name} has no description"
    assert len(description) <= 500
    assert len(description.splitlines()[0]) <= 100


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_annotations_match_side_effects(tools, name):
    annotations = tools[name].annotations
    assert annotations is not None
    assert annotations.readOnlyHint is (name in READ_TOOLS)
    # No destructive (delete) tool in v1: Sentry's issue lifecycle is resolve/ignore.
    assert not annotations.destructiveHint


def test_no_destructive_tool(tools):
    assert not any(t.annotations and t.annotations.destructiveHint for t in tools.values())


def test_instructions_budget():
    assert len(INSTRUCTIONS) <= 1500


def test_tool_names_prefixed(tools):
    assert all(name.startswith("sentry_") for name in tools)


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (400, "invalid_argument", False),
        (401, "unauthorized", False),
        (403, "unauthorized", False),
        (404, "not_found", False),
        (409, "invalid_argument", False),
        (429, "rate_limited", True),
        (500, "upstream_error", True),
        (0, "upstream_error", True),
    ],
)
def test_status_to_code_mapping(status, code, retryable):
    envelope = json.loads(SentryError(status, "boom").to_envelope())
    assert envelope == {"error": {"code": code, "message": "boom", "retryable": retryable}}


def test_tool_without_credentials_returns_not_configured():
    content, _ = asyncio.run(create_mcp_server().call_tool("sentry_list_organizations", {}))
    assert json.loads(content[0].text)["error"]["code"] == "not_configured"


def test_credentials_repr_redacts_token():
    creds = SentryCredentials(base_url="https://sentry.io", auth_token="very-secret-token")
    assert "very-secret-token" not in repr(creds)
    assert "redacted" in repr(creds)


def test_dump_json_capped_truncates_large_list():
    rows = [{"id": i, **{f"f{j}": f"value-{j:04d}" for j in range(120)}} for i in range(25)]
    data = {"issues": rows, "has_more": True, "next_cursor": "0:100:0"}
    text = dump_json_capped(data)
    assert len(text) <= MAX_CHARS
    out = json.loads(text)
    n = len(out["issues"])
    assert 0 < n < 25
    assert out["has_more"] is True and out["truncated"] is True
    assert "next_cursor" not in out  # continuing from it would skip the records that were cut
    assert [r["id"] for r in out["issues"]] == list(range(n))
