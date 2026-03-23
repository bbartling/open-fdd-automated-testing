---
title: Testing plan
parent: Operations
nav_order: 2
---

# Testing Plan

This is the evolving engineering plan for Open-FDD automated testing.

## Near-term priorities

### 0. Continuous PR and CI review

The OpenClaw workflow should continuously watch active PRs in the same spirit as CodeRabbit:

- detect new commits quickly
- re-check CI and review state
- inspect changed files directly
- run targeted local checks where possible
- write down risks, limitations, and next tests instead of relying on chat memory

See `docs/appendix/ai_pr_review_playbook.md`.


### 1. Restore authenticated backend graph checks

Problem:
- `POST /data-model/sparql` currently returns `401 Missing or invalid Authorization header` from this test bench.

Action:
- ensure `OFDD_API_KEY` is available to the automated testing environment
- verify the SPARQL suite and parity suite can run unattended

Why it matters:
- without authenticated SPARQL/API access, BACnet graph validation is incomplete

### 2. Promote BACnet addressing to a first-class validation target

We need to explicitly validate:
- BACnet devices in the graph
- device instance and address visibility
- object identifiers for polling points
- semantic equipment type for those points

This is no longer optional background metadata. It is core operational context.

### 3. Prove fault calculation from end to end

The target standard is:
- fake BACnet device fault schedule is known
- DIY BACnet server RPC confirms source values
- Open-FDD data-model SPARQL queries confirm BACnet devices and point addressing
- Open-FDD scrape path receives those values
- YAML rules + rolling windows predict an expected fault
- Open-FDD fault outputs show that exact fault
- the overnight process writes a durable report

See `docs/bacnet_fault_verification.md` and `reports/overnight-bacnet-verification-template.md`.

### 4. Preserve reusable context for future clones

The repo should keep visible documentation for:
- the operational states
- overnight review discipline
- BACnet graph context
- portability assumptions
- future optimization intent
- documentation guidance that works for both humans and AI agents

### 5. Add nightly docs and link review

The overnight workflow should also:
- validate important README and docs links
- make sure link checking is done against the correct target branches
- treat `master` as the primary target branch
- optionally check one active development branch when it is the intended docs destination for unreleased fixes
- avoid mixing findings from unrelated feature branches
- identify missing docs pages or thin areas
- suggest documentation improvements that make the system easier for both humans and AI agents to understand
- record those suggestions in durable repo docs or review notes

## Future role in live HVAC systems

In a live HVAC deployment, the same testing and validation assets should support:

- confidence in FDD outputs
- confidence in model/rule applicability
- future optimization and supervisory logic
- operator- or facility-manager-facing monitoring summaries

The repo is not only a test harness. It is becoming a reproducible engineering context pack.
