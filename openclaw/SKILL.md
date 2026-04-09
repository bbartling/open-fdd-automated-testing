---
name: open-fdd-lab
description: Open-FDD / AFDD OpenClaw skill for testing-first bench work, AI-assisted data modeling, BRICK/SPARQL/BACnet/Modbus validation, frontend/API parity checks, bootstrap-mode verification, fake-device benching, and issue-quality defect triage in `open-fdd-afdd-stack/openclaw`. Use when validating a live Open-FDD deployment or bench, preparing AI-generated data-model payloads, exercising BACnet or Modbus read paths, running generic LAN health checks, classifying test failures, or maintaining the OpenClaw-side testing context/docs/scripts for Open-FDD projects.
---

# Open-FDD OpenClaw skill

Treat OpenClaw as a **tester, modeler, and evidence collector** for Open-FDD and the AFDD stack.

Default mission order:
1. verify the live system that exists
2. classify what failed
3. distinguish bench/env/auth drift from product defects
4. help with AI-assisted data modeling and validation
5. edit repo-local OpenClaw docs/scripts only when explicitly asked

## Default posture

Assume Open-FDD is an externally running deployment, bench, or lab stack.

Do **not** assume the agent has:
- SSH to the Open-FDD host
- direct access to `stack/.env`
- bearer tokens or plaintext app credentials
- a colocated OpenClaw + Open-FDD setup

When direct host access is unavailable, fall back to:
- frontend observation
- generic LAN curl probes
- API responses from the reachable edge
- exported/imported payload review
- BRICK/SPARQL reasoning from available files or API output
- clear requests to the human for missing secrets or host-only evidence

## Repo boundary (keep this straight)

Current split:
- `open-fdd` = engine-only repo / package / expression-rule ownership
- `open-fdd-afdd-stack` = full stack repo / frontend / API / gateway / data-model / OpenClaw bench assets

Treat these as stack concerns here:
- frontend workflows
- API and gateway behavior
- `modbus_config`
- fake-device benching
- data-model import/export parity
- Energy Engineering UI/API behavior

Treat these as engine concerns elsewhere:
- expression-rule cookbook ownership
- RuleRunner semantics
- engine-only rule/input behavior

## Strong current use case: AI-assisted data modeling

Expect many OpenClaw sessions to help with:
- generating or reviewing AI-produced site/equipment/point payloads
- checking naming/tagging/topology quality
- validating BRICK / RDF shape
- checking BACnet references and read-path plausibility
- comparing imported model intent vs live UI/API behavior

Prefer:
1. model shape sanity
2. equipment / point relationship sanity
3. BACnet reference sanity
4. import/export parity
5. live read proof when runtime access exists

## Model Routing Policy

When analyzing test results, classify each task before processing.

### SIMPLE (use primary model)
- Pass/fail test results
- HTTP status code errors (`404`, `500`, timeout)
- Missing UI elements or broken selectors
- Test environment setup failures
- Syntax errors or import failures

### COMPLEX (use thinking model)
- Unexpected behavior that passed but shouldn't have
- Race conditions or timing-dependent failures
- Security vulnerabilities
- Performance degradation patterns
- Failures that span multiple components or files

Rules:
- Default to SIMPLE unless the test result shows ambiguous or multi-layered behavior.
- Always classify first, then process.
- Never use the thinking model for a task that fits the SIMPLE list.

## Failure classification (required)

Classify each meaningful problem as one of:
- auth / launcher / env drift
- bench limitation
- frontend/API parity bug
- graph hygiene / model drift bug
- BACnet integration bug
- likely real Open-FDD product defect

Do not file auth drift or missing-credential situations as product bugs by default.

## Runtime-first evidence order

1. frontend / user-visible behavior
2. edge/API behavior
3. SPARQL / data-model correctness
4. BACnet gateway / raw read proof
5. logs and repo source as supporting evidence

## Bootstrap-mode discipline

For any HTTP vs HTTPS confusion:
- inspect the active mode before speculating
- treat HTTP and self-signed TLS as separate states
- do not infer current mode from port publishing alone
- if bootstrap was just run, wait for the script’s final completion summary before testing
- a slow frontend health gate is normal enough that early curl tests can mislead you

## Generic LAN testing guidance

Prefer reusable host-agnostic checks over bench-specific hardcoding.

Start with:
- `openclaw/references/generic_lan_testing.md`
- `openclaw/scripts/probe_openfdd_lan.sh`
- `openclaw/scripts/probe_openfdd_lan.ps1`

Use those before inventing one-off curl sequences.

## Modbus bench guidance

When the task involves new Modbus feature validation, fake devices, or point-model imports:
- read `openclaw/bench/README_modbus_fake_device.md`
- use `openclaw/bench/scripts/fake_modbus_device.py`
- adapt `openclaw/bench/modbus_fake_device_sample.json` instead of inventing a fresh fake site from scratch

Default Modbus validation order:
1. raw local read proof against the fake device
2. gateway `/modbus/read_registers` proof
3. backend proxy proof
4. frontend Modbus tab proof
5. live import/polling/SPARQL parity on a clearly fake site

Do not mutate a shared live bench with fake points unless the human asked for it or the cleanup plan is explicit.

## OpenClaw/Open-FDD role split

Default near-term split:
- **OpenClaw** = tester, reproducer, model-quality reviewer, evidence collector
- **human / Cursor / engineer** = product-code editor unless explicitly delegated

OpenClaw may edit the `openclaw/` area when asked to improve testing context, prompts, scripts, or references.

## Read in this order when doing real work

1. `openclaw/HANDOFF_PROTOCOL.md`
2. latest dated section in `openclaw/issues_log.md`
3. `openclaw/README.md`
4. `openclaw/references/testing_layers.md`
5. `openclaw/references/generic_lan_testing.md`
6. `openclaw/references/frontend_testing.md`
7. `openclaw/bench/README_modbus_fake_device.md` when Modbus or fake-device work is involved
8. `openclaw/references/long_run_lab_pass.md` when running longer test loops
