---
title: AI PR review playbook
parent: Appendix
nav_order: 1
---

# AI PR Review Playbook

This document describes how the automated testing and OpenClaw workflow should mimic the useful parts of CodeRabbit-style review without depending on a paid service.

## Goal

Act like a persistent PR reviewer for Open-FDD and related repos:

- notice new commits quickly
- inspect changed files, not just status badges
- check CI state
- check tests locally when possible
- summarize likely risks, regressions, and follow-up tests
- stay quiet when nothing meaningful changed

## Desired review behavior

For each meaningful PR update, produce a short review in this shape:

1. **What changed**
   - files touched
   - feature area
   - user-visible behavior

2. **What looks good**
   - clear improvements
   - tests added
   - docs/config updated with the feature

3. **What could be wrong**
   - coupling between frontend and backend behavior
   - auth assumptions
   - environment-specific fragility
   - missing tests or local setup gaps

4. **What to test next**
   - exact endpoints
   - exact UI flows
   - exact container/log paths
   - BACnet/FDD implications if relevant

5. **Merge-readiness**
   - pass / caution / blocked

## Current Open-FDD PR focus

The current feature direction includes Docker container log viewing in Open-FDD.

That means the AI reviewer should specifically verify:

- the frontend dropdown lists the correct Docker container names
- the selected dropdown item maps to the correct backend log stream endpoint
- the backend endpoint rejects bad container references safely
- the API container actually has access to `/var/run/docker.sock`
- the feature degrades cleanly when Docker is unavailable
- host-stats container names match what users expect from `docker ps`
- frontend-visible logs actually correspond to the selected container

## Nightly monitoring extension (6 PM to 6 AM)

During the overnight dev-testing window, the reviewer should also behave like a lightweight operations analyst.

### Nightly checks to add

- monitor PR activity and CI changes
- monitor container logs for:
  - `openfdd_api`
  - `openfdd_frontend`
  - `openfdd_bacnet_scraper`
  - `openfdd_fdd_loop`
  - `openfdd_host_stats`
  - `openfdd_bacnet_server`
- compare frontend-observed behavior with backend/container log evidence
- verify that the container selected in the UI produces the matching log output
- note whether failures are:
  - product bugs
  - setup drift
  - missing auth/config
  - testbench limitations

## How to knock off CodeRabbit on a budget

The useful pieces of CodeRabbit can be reproduced with local tools and discipline:

### Inputs
- `gh pr view`
- `gh pr checks`
- `gh pr diff`
- local git diff / file inspection
- targeted pytest or frontend tests
- log inspection
- overnight summaries written to disk

### Review style to mimic
- identify scope fast
- call out one or two concrete risks rather than vague anxiety
- mention tests that were added or should be added
- separate likely bug from likely environment/config issue
- prefer actionable follow-up over generic commentary

### What not to imitate
- filler comments
- noisy nits with no engineering value
- pretending certainty when local verification failed

## Known local limitation on 2026-03-22

A local attempt to run:

```bash
python -m pytest open_fdd/tests/platform_api/test_analytics.py -q
```

failed during collection because the environment on this machine is missing `pydantic-settings`.

That does **not** mean the PR is broken, but it does mean local backend verification on this workstation is not yet turnkey.

## Recommended next automation

- keep a recurring PR watcher enabled
- add an overnight reminder/checklist for 6 PM to 6 AM
- save review notes into repo docs or artifacts instead of chat only
- once Docker log access is available, correlate UI log selection against actual container output
