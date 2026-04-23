# Open-FDD docs gap review for future OpenClaw instances

Timestamp: 2026-04-22T13:00:00Z
Repo reviewed: `tmp/open-fdd-afdd-stack`
Branch reviewed: `pr-9`

## Summary

The repo already has useful docs for OpenClaw-assisted Open-FDD work, especially:

- `docs/openclaw_integration.md`
- `docs/operations/openclaw_context_bootstrap.md`
- `docs/operations/testing_plan.md`
- `docs/modeling/ai_assisted_tagging.md`
- `docs/modeling/llm_workflow.md`
- `docs/bacnet/fault_verification.md`

That said, there is still a real documentation packaging gap for future OpenClaw instances and future agents.

## Biggest gaps found

### 1. Docs reference missing `openclaw/` repo assets

Current published docs reference files like:

- `openclaw/HANDOFF_PROTOCOL.md`
- `openclaw/SKILL.md`
- `openclaw/references/testing_layers.md`
- `openclaw/references/session_status_summary.md`

But this repo clone does not currently contain an `openclaw/` directory at all.

That means the docs promise an agent bootstrap pack that is not actually present in the repo.

### 2. No committed skill/bootstrap pack for future agents

There is no repo-local agent package that tells a fresh OpenClaw instance:

- what this project is
- what order to read docs in
- how to operate safely on test bench vs live HVAC
- what to treat as durable repo truth vs local/private memory
- how to validate AI-assisted modeling, BACnet discovery, timeseries, FDD, provenance, and reset semantics

### 3. No live-HVAC transition guidance yet

The current docs are still bench-heavy. They are strong for fake devices and overnight bench verification, but weaker on:

- moving from DIY/fake bench to live building BAS
- handling risk boundaries in live HVAC
- validating model quality and FDD quality without unsafe writes
- tuning fault thresholds in production-like conditions
- separating observation-only workflows from control/write workflows

### 4. No explicit doc on agent memory boundaries

There is some good portability guidance, but not yet a concise repo doc that says:

- what belongs in repo docs
- what belongs in local OpenClaw memory
- what should never be committed
- how future agents should persist lessons without leaking secrets

### 5. No short “first 30 minutes” runbook for spawned agents

A future agent should have a single concise file that says:

1. read these docs first
2. confirm API/auth/base URL
3. confirm whether this is bench or live HVAC
4. confirm whether writes are allowed
5. choose the right validation lane
6. record findings in durable files

That file does not currently exist in the repo.

## Recommendation

Yes, I think the repo should add something like a committed skill/bootstrap pack.

Not because OpenClaw requires it, but because it makes future agents dramatically more reliable and portable.

My recommendation is:

- add a repo-local `openclaw/` directory
- include a compact `SKILL.md`
- include a few targeted reference files
- add one live-HVAC-oriented operations doc
- keep memory itself out of git, but document memory policy clearly

## What not to commit

Do not commit:

- actual OpenClaw `MEMORY.md`
- daily private memory logs
- `.env` secrets
- bearer tokens / auth tokens
- raw local session dumps with secrets

Instead, commit:

- reusable workflows
- validation runbooks
- safety rules
- expected deployment patterns
- known pitfalls
- report templates
- handoff conventions

## Suggested repo additions

### Option A, best near-term shape

```text
openclaw/
  SKILL.md
  HANDOFF_PROTOCOL.md
  references/
    first-session-checklist.md
    testing-layers.md
    live-hvac-guardrails.md
    session-status-summary.md
    memory-policy.md
```

### Option B, lighter weight if you want docs-only first

```text
docs/operations/
  openclaw_agent_bootstrap.md
  live_hvac_guardrails.md
  memory_and_secrets_policy.md
```

Option A is better if you want future OpenClaw instances to be able to spawn into this repo and immediately know what to do.

## Recommendation on `.skill` style

Yes, something like the `databook` project pattern is worth doing here, but keep it simple.

Recommended approach:

- use a single committed `openclaw/SKILL.md` as the agent bootstrap entrypoint
- keep the skill concise
- move details into `openclaw/references/*.md`
- do not try to commit live memory files as part of the skill
- document memory policy instead of committing memory content

## Draft files prepared

I prepared draft content for:

- `drafts/openclaw/SKILL.md`
- `drafts/openclaw/HANDOFF_PROTOCOL.md`
- `drafts/openclaw/references/first-session-checklist.md`
- `drafts/openclaw/references/testing-layers.md`
- `drafts/openclaw/references/live-hvac-guardrails.md`
- `drafts/openclaw/references/session-status-summary.md`
- `drafts/openclaw/references/memory-policy.md`
- `drafts/docs/operations/openclaw_agent_bootstrap.md`

These are written for future OpenClaw instances working both on the bench and later on live HVAC systems.
