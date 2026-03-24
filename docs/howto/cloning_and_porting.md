---
title: Cloning and porting
parent: How-to guides
nav_order: 1
---

# Cloning and Porting

This repo should be portable to another lab, another workstation, or another Open-FDD deployment with minimal conceptual changes.

## Core portability idea

Same tools, any building — only the knowledge graph changes.

That means the repo carries the reusable process, while the live Open-FDD model carries the site-specific truth.

## What should transfer cleanly

- the test phases
- the BACnet fake-device approach
- the overnight review discipline
- the SPARQL validation set
- the operator framework
- the continuous context-backup loop
- the idea of proving telemetry-to-fault correctness rather than only checking page loads

## What usually changes per environment

- frontend URL
- API URL
- API auth setup
- site IDs / names
- BACnet gateway hostnames or IPs
- active Open-FDD rules directory
- Docker/container naming
- LAN / OT network topology
- the actual HVAC system, naming conventions, and semantic model shape
- SPARQL queries or filters needed for that environment

## What to do when deploying to another site

1. Resolve the target frontend/backend/BACnet endpoints from the real launch context.
2. Confirm auth works from the shell or runtime that will actually run the checks.
3. Query the Open-FDD model first:
   - sites
   - equipment
   - BACnet devices
   - representative outdoor / plant / air / zone points
4. Let the model decide what should be checked at that site.
5. Keep repo docs generic; put site-specific truth into the Open-FDD model instead of hard-coding it into markdown.

## Recommended first-pass deployment flow for a new building

Use this order on a fresh site:
- verify backend auth and reachability
- run SPARQL/model sanity checks
- discover representative operator-relevant points from the model
- run the daytime smoke suite first
- fix auth/model/BACnet issues found there before trusting the overnight 12-hour run
- only then move into recurring integrity sweeps and overnight review

## Same-bench OpenClaw clone checklist

If OpenClaw is cloned onto another machine for the **same current test bench**, the new clone should read these first:

1. `README.md`
2. `docs/operations/openclaw_context_bootstrap.md`
3. `docs/operations/openfdd_integrity_sweep.md`
4. `docs/bacnet/fault_verification.md`
5. `fake_bacnet_devices/README.md`
6. `docs/howto/fake_fault_schedule_monitoring.md`

And it should know these durable facts immediately:
- the fake devices intentionally inject faults on a **UTC** schedule
- the 180°F spike is expected only during the shared out-of-bounds window
- the correct way to judge that spike is to compare live BACnet RPC reads against `fake_bacnet_devices/fault_schedule.py`
- the integrity sweep should classify graph drift, auth drift, BACnet drift, and product behavior separately
- durable reasoning belongs in this repo, not only in local OpenClaw chat memory

## Portability goal

A clone of this repo should make it easy for another engineer to answer:

- Is Open-FDD healthy here?
- Is BACnet scraping working here?
- Is the building model usable here?
- Are faults being computed here?
- Are regressions visible here before they affect a real deployment?

## Engineering principle

Keep environment-specific values configurable and keep the verification logic reusable.

In practice, deployment to another site usually looks like this:
- Open-FDD runs on some other server (often a Linux box on the OT LAN)
- the testing/tooling repo is cloned onto another machine
- the tooling is pointed at the target Open-FDD URL, auth, BACnet gateway, and rule/model context for that environment

The tooling should therefore be robust to:
- different LAN IP schemes
- different Open-FDD hosts
- different HVAC systems and point naming
- different site/equipment modeling shapes
- different SPARQL needs per deployment

The goal is portability with context, not a one-off lab setup.
