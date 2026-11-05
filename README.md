# Sentry MCP Server

An [MCP](https://modelcontextprotocol.io) server for the [Sentry](https://sentry.io) API (v0),
the error-tracking/observability platform. It lets an AI agent see which organizations and
projects a token can reach, find and triage error issues (list, inspect, change status /
assignment / bookmark / priority), drill into the events behind an issue, look up organization
members, and read or record release and deploy history.

- Transport: MCP Streamable HTTP at `POST /mcp`, health probe at `GET /health`
- Stateless and multi-tenant: credentials arrive on every request as HTTP headers and are
  never stored; every tool is listed from the first `tools/list`
- Python 3.12, [uv](https://docs.astral.sh/uv/), FastMCP, httpx
- License: Apache-2.0, Copyright 2026 MSPbots.ai

<div align="center">

## MSPbots Connector

**The MCP Gateway built for MSPs: visible, controlled, and your data stays where it belongs.**

[**Get started at connect.mspbots.ai →**](https://connect.mspbots.ai)

</div>

---

MSPbots Connector gives your AI clients one MCP URL to reach your entire MSP stack (RMM, PSA, documentation, security, finance), and gives you control over who can call which tool and a record of everything that was called.

**Hosted service: [connect.mspbots.ai](https://connect.mspbots.ai)** · Free to use.

### Why Connector

![MSPbots Connector](https://stgoss.mspbots.ai/files/mcp/mspbots-mcp.png)

| | |
|---|---|
| **Visible** | Every tool call is logged: who, which vendor, when. Usage dashboard, CSV export, SIEM streaming. |
| **Controlled** | Role-based, per-tool allowlist. Deny by default. |
| **Protected** | Credentials encrypted per record. AI clients never see your vendor passwords or tokens. |
| **MSP-native** | Built for the MSP stack only: RMM, PSA, documentation, security, finance. |

### Quick start

1. **Sign up** at [connect.mspbots.ai](https://connect.mspbots.ai).
2. **Connect your vendors.** Pick from 150+ connectors and authorize each one on the vendor's own page, or bring your own API keys. No extra vendor accounts needed.
3. **Set access.** Create roles and decide which tools each role may call. Nothing is allowed until you allow it.
4. **Add your MCP URL to your AI client.** Copy the URL from your Connector dashboard into Claude, ChatGPT, Cursor, VS Code, Gemini, Codex, or any MCP-capable client.
5. **Ask your AI to do real work**, and watch every call appear in the audit log.

### Features

**Unified gateway**
- One MCP URL for all your AI clients
- 150+ connectors across the MSP stack
- Custom MCP servers supported, free
- Authorization happens on each vendor's own page; the AI never sees passwords or tokens
- Bring your own credentials: use the vendor API keys you already have
- Multiple accounts per app; connect once, reuse across AI clients
- Tool search: finds the right action for the task
- One sign-in; vendor credentials are injected behind the scenes and OAuth tokens refresh automatically

**Visibility**
- Audit log for every tool call (who, which vendor, when)
- Usage dashboard: call volume, top vendors, error rate, per-user activity
- Export audit logs to CSV, or stream to Loki, Graylog, or LogScale (SIEM)
- Optional recording of tool arguments and result summaries (off by default, enabled per organization)

**Control**
- Per-role, per-tool allowlist, deny by default
- owner / admin / member roles
- SCIM provisioning with Entra ID, Okta, JumpCloud, and Google Workspace

**Security**
- Credentials encrypted one record at a time (AES-256-GCM, per-record key)
- AI clients authenticate with OAuth 2.1 + PKCE
- Vendor responses are scanned for prompt-injection patterns and returned as structured data. This is one layer of defense, not a guarantee against every attack.
- Static egress IP for customer firewall and API allowlisting

### Pricing

**Free.**

Links: [connect.mspbots.ai](https://connect.mspbots.ai) · [mspbots.ai](https://mspbots.ai)

---

## Authentication headers

| Header | Required | Type | Default | Allowed values | Description | Example |
|---|---|---|---|---|---|---|
| `X-Sentry-Auth-Token` | Yes | string | none | - | Sentry Auth Token (Settings → Auth Tokens, or an internal integration token). Needs scopes `org:read`, `project:read`, `project:releases`, `event:read`, `event:write`, `member:read`. | `your-sentry-auth-token` |
| `X-Sentry-Base-URL` | No | string | `https://sentry.io` | https URL | API host for a self-hosted/on-premise Sentry instance (a bare host gets `https://`; a trailing `/api/0` is removed) | `https://sentry.example.com` |

Where to get a token: in Sentry, open **Settings → Auth Tokens** (or create an internal
integration under **Settings → Developer Settings** and use its token) and create one with the
scopes above. If self-hosted Sentry restricts API access by IP, allow the public egress IP of
the environment that runs this server.

A request to `/mcp` without `X-Sentry-Auth-Token` gets HTTP 401 naming the missing header; an
`X-Sentry-Base-URL` that is not a valid https URL gets HTTP 400.

## Tools

All tools return a JSON string. List tools return `{<key>, next_cursor?}`: pass `next_cursor`
from a previous result to continue (Sentry's own opaque cursor, not an offset). **write** marks
tools that change data.

| Area | Tools |
|---|---|
| Organizations & projects | `sentry_list_organizations`, `sentry_list_projects` (**organization_slug**), `sentry_get_project` (**organization_slug**, **project_slug**) |
| Issues | `sentry_list_issues` (**organization_slug**, project, query, sort, cursor, limit), `sentry_get_issue` (**organization_slug**, **issue_id**); **write**: `sentry_update_issue` (**organization_slug**, **issue_id**, status, assigned_to, is_bookmarked, priority) |
| Issue events | `sentry_list_issue_events` (**organization_slug**, **issue_id**), `sentry_get_issue_event` (**organization_slug**, **issue_id**, **event_id**) |
| Members | `sentry_list_members` (**organization_slug**) |
| Releases & deploys | `sentry_list_releases` (**organization_slug**), `sentry_get_release` (**organization_slug**, **version**); **write**: `sentry_create_release` (**organization_slug**, **version**, **projects**), `sentry_create_deploy` (**organization_slug**, **version**, **environment**) |

There is no delete tool: Sentry's issue lifecycle is resolve/ignore, not delete, and this
connector does not expose organization/project administration.

`sentry_list_issues` defaults `query` to `is:unresolved` when omitted; pass `query=""` to see
issues of every status. `sentry_create_release` is upsert-by-version: calling it again with the
same `version` returns the existing release instead of erroring.

Errors come back as a JSON envelope instead of an exception:

```json
{"error": {"code": "not_found", "message": "Sentry returned HTTP 404 for organizations/acme/issues/999/", "retryable": false}}
```

`code` is one of `not_configured`, `unauthorized`, `not_found`, `invalid_argument`,
`rate_limited`, `upstream_error`. Read tools are retried with backoff on 429, 5xx and network
errors; write tools (`sentry_update_issue`, `sentry_create_release`, `sentry_create_deploy`) are
never retried by this client, so an issue update or a deploy record is never double-applied.

## Run locally

```bash
uv sync
uv run python -m sentry_mcp          # listens on 0.0.0.0:8080
```

or with Docker:

```bash
docker build --platform linux/amd64 -t sentry-mcp:dev .
docker run --rm -p 8080:8080 sentry-mcp:dev
```

Configuration (environment variables, all optional): `MCP_HTTP_HOST` (default `0.0.0.0`),
`MCP_HTTP_PORT` (default `8080`), `LOG_LEVEL` (default `INFO`). Credentials are never read
from the environment.

## Testing example

```bash
# list tools
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Sentry-Auth-Token: your-sentry-auth-token" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# unresolved issues in one organization
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Sentry-Auth-Token: your-sentry-auth-token" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"sentry_list_issues","arguments":{"organization_slug":"acme"}}}'
```

Unit tests (no network access needed):

```bash
uv run pytest
```

## Decisions made by DEV01

First-version scope decisions with no ticket-specific requirement to go on; see the design
document (`docs/tickets/PRD-21331.md`) for the full reasoning and alternatives considered:

- Bearer auth token (`X-Sentry-Auth-Token`) over an OAuth2 app — Sentry's own docs recommend
  token auth for integrations.
- Optional `X-Sentry-Base-URL`, default `https://sentry.io` — unlike this org's other
  single-host connectors, Sentry has a mainstream self-hosted deployment model.
- Organization-scoped issue/event endpoints, not the project-scoped pair Sentry's own docs say
  "has been replaced."
- `organization_slug` is an explicit argument on every tool, not inferred from the credential.
- No Monitors & Alerts, Dashboards, Discover & Performance, Replays, Profiling, Integrations
  management, SCIM, client keys, service hooks, member role writes, or issue-delete tool — see
  the design document's non-goals and "Decisions made by DEV01" section.

## License

Apache License 2.0 - see [LICENSE](LICENSE) and [NOTICE](NOTICE).
