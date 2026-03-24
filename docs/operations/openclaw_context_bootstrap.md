---
title: OpenClaw context bootstrap for Open-FDD work
parent: Operations
nav_order: 4
---

# OpenClaw context bootstrap for Open-FDD work

This note exists so future clones, fresh agent sessions, and alternate OpenClaw deployments can hit the ground running on Open-FDD work without depending on one machine's private local state.

## What should be backed up to GitHub

Back up **durable operating context**, not raw secrets.

Good candidates:
- sweep philosophy and operator logic
- overnight workflow expectations
- how to classify failures
- current repo paths and test-bench conventions
- dashboard expectations
- data-model/SPARQL patterns that derive meaningful BACnet checks
- climate-aware live-HVAC reasoning strategy
- lessons learned from auth drift and launch-context drift

Do **not** push:
- API keys
- bearer tokens
- raw auth stores
- local SQLite databases with sensitive conversation history
- device pairing secrets
- copied `.env` secrets

## Important local context currently living under `C:\Users\ben\.openclaw`

Useful local context exists in places like:
- `workspace/memory/*.md`
- `workspace/TOOLS.md`
- `workspace/AGENTS.md`
- `cron/jobs.json`
- `cron/runs/*.jsonl`
- `memory/main.sqlite`

Those local stores are helpful for reconstruction and continuity, but they are **not** all appropriate for direct GitHub backup.

The safe pattern is:
1. read the local context
2. distill durable, reusable knowledge
3. publish the distilled version into this repo's docs
4. keep secrets and raw chat history local

## Current durable context worth preserving

### 1) Integrity sweep cadence and stance
- daytime recurring sweep cadence is now **20 minutes**, not 10
- the sweep should behave like an intelligent building operator, not a dumb ping monitor
- use the Open-FDD semantic model as the primary window into the system

### 2) Source-of-truth order
Prefer this order when deciding what to trust:
1. live backend model via `/data-model/check` and `/data-model/sparql`
2. running stack semantic model / launch context
3. repo docs and local notes

### 3) Environment resolution before trust
Do not assume one static IP forever.
Resolve from the **current repo/env/launcher context**:
- frontend URL
- backend URL
- DIY BACnet server URL
- auth source / shell context

### 4) What a good sweep must do
A meaningful sweep should:
1. confirm authenticated backend access
2. query the current semantic model
3. discover current sites/equipment/devices/points via SPARQL
4. choose representative BACnet reads from the model
5. compare model expectation vs live BACnet behavior
6. classify drift clearly

### 5) Failure classes to preserve
Use these buckets consistently:
- auth/config drift
- graph/model drift
- BACnet/device-state drift
- testbench limitation
- likely Open-FDD product behavior

### 6) Operator-style live HVAC reasoning target
When the same workflow later runs on a real building, the sweep should reason like a strong human operator:
- use model location and local time
- use outdoor-air sensors from the model
- use recent outdoor trend context from Open-FDD when available
- use Open-Meteo current/historical weather as a support signal
- decide whether the building should broadly be making heat or cool
- bias checks toward seasonally important plant/air/zone devices
- compare commands vs feedback when possible
- stay humble: use weather as a sanity input, not as proof by itself

Examples:
- if it is cold outside, representative heating equipment should broadly look capable of making heat
- if it is hot outside, representative cooling equipment should broadly look capable of making cooling
- if the building is unoccupied, focus more on protection/sanity and less on comfort optimization

### 7) Overnight coordination rule
During the dedicated **6 PM to 6 AM** overnight testing/review workflow:
- suppress duplicate low-signal sweep chatter
- let the richer overnight review do the deeper PR/log/docs/BACnet/FDD work
- only surface genuinely new, high-signal alerts
- if meaningful durable context changed, commit it and push it so future clones inherit it

### 8) Dashboard expectations
The dashboard should reflect:
- `TEST BENCH` vs `LIVE HVAC`
- why that mode was chosen
- operator alert level
- seasonal/time basis
- weather basis
- HVAC sanity summary
- representative live sensor reads
- action plan and findings

### 9) Fake-device fault schedule context must be explicit
On the current test bench, the fake BACnet devices intentionally inject deterministic faults.

Important durable facts:
- the shared schedule lives in `fake_bacnet_devices/fault_schedule.py`
- schedule basis is **UTC minute-of-hour**, not process start time
- UTC minutes `10-49` are the flatline window
- UTC minutes `50-54` are the out-of-bounds window
- the out-of-bounds marker is intentionally `180.0` on scheduled points

That means a 180°F spike on points like `SA-T` or `ZoneTemp` is not automatically a product bug.
The right next step is to compare:
- current UTC minute
- expected schedule mode from `fault_schedule.py`
- live BACnet RPC reads
- Open-FDD fault outputs and rolling-window expectations

Future clones should use `scripts/monitor_fake_fault_schedule.py` instead of treating a raw spike as mysterious.
The recurring integrity sweep and local dashboard summary should carry the schedule-aware interpretation forward so another machine can see whether a spike was expected without re-deriving the whole bench model from scratch.

## Recommended backup discipline

When local OpenClaw memory yields something future-you will need again:
- convert it into docs, not raw transcript backup
- prefer one clean durable write over many noisy scratch notes
- commit the repo change the same day if it changes how the system should be operated

## Minimal future-clone checklist

A new clone/agent should be able to learn this repo by reading:
- `docs/operations/openfdd_integrity_sweep.md`
- `docs/operations/openclaw_context_bootstrap.md`
- `docs/appendix/ai_pr_review_playbook.md`
- dashboard local/progress structure

That should be enough to start behaving intelligently even before local personal memory is restored.
