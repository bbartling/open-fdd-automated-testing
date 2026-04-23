---
name: openfdd-operator
description: Use when working inside the open-fdd-afdd-stack repo with OpenClaw or another coding agent. Covers first-session bootstrap, AI-assisted data modeling, BACnet discovery-to-graph validation, FDD verification, overnight bench work, reset semantics checks, and safe transition from fake bench to live HVAC deployments.
---

# Open-FDD operator skill

Use this skill when the repo is `open-fdd-afdd-stack` or when the task involves Open-FDD bench operations, AI-assisted modeling, BACnet validation, FDD validation, fault tuning, or OpenClaw orchestration around this stack.

## Read first

On a fresh session, read these in order:

1. `openclaw/HANDOFF_PROTOCOL.md`
2. `openclaw/references/first-session-checklist.md`
3. `openclaw/references/testing-layers.md`
4. `docs/openclaw_integration.md`
5. `docs/operations/openclaw_context_bootstrap.md`
6. `docs/operations/testing_plan.md`

If the task is AI-assisted data modeling, then also read:

- `docs/modeling/llm_workflow.md`
- `docs/modeling/ai_assisted_tagging.md`

If the task is BACnet / FDD validation, then also read:

- `docs/bacnet/fault_verification.md`
- `docs/howto/bacnet_discovery_via_crud.md`
- `docs/howto/verification.md`

If the system is live HVAC, also read:

- `openclaw/references/live-hvac-guardrails.md`

## Core operating rules

- Treat repo docs as durable shared truth.
- Treat local memory as private working memory, not as a source of truth to commit.
- Never commit secrets, `.env` contents, bearer tokens, or private memory files.
- For bench work, validate the entire chain: discovery, graph, timeseries, FDD output, and operator-facing evidence.
- For live HVAC, default to observation-only unless the user explicitly authorizes writes.
- When a reset/bootstrap action must run in another Docker-capable environment, ask the human to run it there and verify outcomes afterward through the API.

## What good work looks like

A strong Open-FDD validation session usually does some combination of:

- verify API reachability and auth
- confirm current deployment mode: bench vs live HVAC
- inspect current site/model state with export and summary endpoints
- validate BACnet discovery and graph promotion
- validate timeseries freshness and FDD cadence
- validate fault behavior against the known rule contract
- capture exact request/response snippets for regressions
- leave durable notes in repo docs or reports, not only in chat

## Durable outputs

Prefer writing findings to:

- `reports/`
- `repo_reviews/`
- `openclaw/issues_log.md` if the repo uses it
- docs pages when the lesson is reusable

Use local memory only for private continuity that should not be committed.
