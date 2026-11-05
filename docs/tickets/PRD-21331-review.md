# PRD-21331 · Code review

Status: frozen @ eb5b25e

## Round 1 · 2026-11-05 · reviewed dev/PRD-21331 @ eb5b25e (base main @ 4f07e54)

Verdict: approved

### Findings

No must-fix findings.

1. [suggestion] Self-test / Handoff — `gitleaks` and `docker build` could not be independently re-run in the review sandbox either (no `gitleaks` binary, no reachable Docker daemon — same constraints the dev leg hit). Manual inspection of `api_client.py`, `config.py`, `server.py`, `Dockerfile`, `docker-compose.yml`, and the test fixtures found no hardcoded credentials, only placeholder examples (`token-123`, `placeholder-token-123`, `your-sentry-auth-token`). `docker build` will be exercised for real by `/api/vendor-register` on INT registration (it rebuilds the image from `main` before deploying), so a broken `Dockerfile` would surface there, not silently ship.

### Verification notes (what was checked, beyond reading the diff)

- `uv sync && uv run pytest -q`: **72 passed**, 0 failed — matches the `[DEV]` stub and the Self-test table.
- `grep -rnP '[\x{4e00}-\x{9fff}]' --exclude-dir=.git --exclude-dir=.venv .`: no output (no Chinese characters anywhere in the repo).
- README "MSPbots Connector" section (`README.md:17`–`85`) is a byte-identical substring match against `reference/readme-connector-section.md`, and sits before the "Authentication headers" table (`README.md:87`), per SOP §0.5.
- Tool inventory: all 13 tools in `src/sentry_mcp/tools/{orgs,issues,events,members,releases}.py` match the tech design's "Data & API contract" table 1:1 (names, params, annotations) and the `tests/test_tools.py` `EXPECTED_TOOLS` snapshot (`test_tool_names_are_stable`, `test_tool_count_within_budget` asserting exactly 13).
- Credentials: read only from `X-Sentry-Auth-Token` / `X-Sentry-Base-URL` headers (`server.py:112-134`), no env-var fallback, no credential field in `config.py`'s `Settings`. Stored only in a `contextvars.ContextVar`, reset in `finally` (`server.py:134-140`); `SentryCredentials.__repr__` redacts the token (`api_client.py:103-104`). Isolation and redaction are covered by `tests/test_middleware.py::test_concurrent_requests_isolate_credentials` and `::test_credentials_repr_hides_token`, which pass.
- Error handling: `run_tool()` (`tools/_common.py:107-134`) never lets an exception escape; `_STATUS_TO_CODE` (`api_client.py:66-84`) matches AC15 and `tests/test_tools.py::test_status_to_code_mapping` 1:1, including the `0` (network/timeout) and `>=500` fallthrough cases. Writes (`PUT`/`POST`) are never retried (`api_client.py:161`, comment explains why); reads retry on `429`/`5xx`/network error honoring `Retry-After` / `X-Sentry-Rate-Limit-Reset` (`api_client.py:189-203`).
- Token-economy: `dump_json_capped` (`_json.py`) caps at 20000 chars with a graceful shrink-then-cut strategy and never silently drops `has_more`/continuation fields that would skip records; `tests/test_tools.py::test_dump_json_capped_truncates_large_list` exercises this path and passes.
- Checked against SOP §14 checklist (`~/.claude/skills/vendor-mcp-development/reference/vendor-mcp-development-sop.md`): `/health` is a purely local probe (`__main__.py:48-50`), DNS-rebinding protection is explicitly disabled with a one-line reason (`server.py:150`), the MCP app's lifespan is wired to the outer Starlette app with a comment explaining why (`__main__.py:54-61`), `Settings` uses `extra="ignore"` (`config.py:29`), Dockerfile is multi-stage/non-root/`curl`-installed/`HEALTHCHECK` (matches `hudu-mcp`'s shape per the tech design).
- Scope: change list matches the tech design's "Change list" section exactly (all new files; nothing outside `sentry-mcp` touched). No migration, no cross-repo dependency (`release order: any`), consistent with "Rollout & rollback" and "Risks & dependencies".
- `docs/tickets/PRD-21331.ac.json` validates (`ticket_store.py validate`: 22 cases) and matches the 22 test cases listed in the main doc's "Test cases" section; the 16 cases needing a real vendor account are recorded as `untested`, not forced to `pass`, per SOP.

Base confirmed via `git merge-base origin/main dev/PRD-21331` = `4f07e54`, matching the Handoff section's recorded base ("re-fetched immediately before the final commit, origin/main still 4f07e54").
