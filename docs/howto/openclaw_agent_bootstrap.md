---
title: OpenClaw agent bootstrap
parent: Operations
nav_order: 4
---

# OpenClaw agent bootstrap

This page is the first-stop runbook for future OpenClaw or similar coding-agent sessions working on Open-FDD.

## Purpose

Help a fresh agent quickly determine:

- what environment it is in
- what docs to read first
- whether it is working on a test bench or a live HVAC system
- what safety boundaries apply
- where to write durable findings

## First 30 minutes

### 1. Capture environment facts

Record:

- repo branch and commit SHA
- Open-FDD base URL
- auth mode used
- whether Docker/bootstrap commands can run from the current shell
- whether the target is fake bench or live HVAC
- whether writes are permitted

### 2. Read in this order

1. `docs/openclaw_integration.md`
2. `docs/operations/openclaw_context_bootstrap.md`
3. `docs/operations/testing_plan.md`
4. `docs/modeling/llm_workflow.md` and `docs/modeling/ai_assisted_tagging.md` when modeling is in scope
5. `docs/bacnet/fault_verification.md` and `docs/howto/bacnet_discovery_via_crud.md` when BACnet/FDD validation is in scope

If the repo includes an `openclaw/` directory, also read that bootstrap pack first.

### 3. Choose the validation lane

#### Bench lane

Use for:

- fake BACnet devices
- discovery-to-graph validation
- export/import modeling loops
- provenance validation
- reset semantics
- YAML rule behavior

#### Live HVAC lane

Use for:

- validating real controller discovery
- validating point semantics and model quality
- checking timeseries freshness and FDD quality
- fault tuning and health review

Default to observation-only unless writes are explicitly approved.

### 4. Leave durable outputs

Use:

- `reports/` for timestamped validation artifacts
- docs pages for reusable lessons
- `repo_reviews/` for branch/PR snapshots

Do not rely on chat history as the only record.

## Important deployment nuance

OpenClaw may have API visibility without direct shell control of the Docker-capable host. In that case:

- ask the human to run bootstrap/reset/orchestration commands in the correct environment
- verify the effects via API afterward
- clearly mark whether proof is direct command-log proof or API-side postcondition proof

## Future live-HVAC direction

The same workflow used on the bench should evolve into a live HVAC validation playbook focused on:

- AI-assisted data modeling robustness
- discovery-to-graph correctness
- timeseries and FDD confidence
- fault tuning quality
- operational safety and human review
