# OpenClaw lab (external bench first)

OpenClaw’s default Open-FDD posture is **external system testing and AI-assisted data modeling**, not clone-first repo work.

Use OpenClaw as a commissioning-minded tester and model-quality reviewer for a running Open-FDD deployment, bench, or new-building onboarding effort:
- web app regression testing
- frontend/API parity checks
- BRICK/RDF model validation
- BACnet add-to-model and live read verification
- Modbus add-to-model and live read verification
- AI-assisted data-model payload review and refinement
- bootstrap-mode verification (HTTP vs self-signed TLS)
- overnight scrape/FDD/hot-reload review
- defect confirmation and issue filing

Repo-local source edits are optional and only when explicitly requested by the human.

**Agent entry:** [`SKILL.md`](SKILL.md) · [`HANDOFF_PROTOCOL.md`](HANDOFF_PROTOCOL.md).

## System under test

Open-FDD is usually treated as an externally running bench or deployment.

OpenClaw may or may not have:
- SSH to the Open-FDD host
- access to `stack/.env`
- access to active API/BACnet bearer tokens
- colocated access on the same machine as the stack

So the default workflow must support both:
1. **host-aware** testing with SSH / `.env` / local logs
2. **edge-only** testing from a reachable LAN or VPN client

When host access is missing, fall back to generic LAN probing, frontend observation, API edge checks, exported payload review, and explicit asks for missing credentials.

## Current Open-FDD/OpenClaw role

Near-term default:
- OpenClaw = tester, reproducer, evidence collector, AI-assisted model reviewer
- product code changes = human / Cursor / engineer unless explicitly delegated

Current repo boundary:
- `open-fdd` = engine-only repo / expression-rule ownership
- `open-fdd-afdd-stack` = frontend / API / gateway / data-model / OpenClaw bench assets

High-value OpenClaw work now includes:
- validating AI-generated site/equipment/point payloads
- checking BRICK classing/tagging/topology
- checking BACnet references for plausibility and live-read proof when possible
- checking Modbus fake-device, gateway, and point-model workflows
- confirming whether imports, exports, and UI views match model intent

## Current bench reality (keep this straight)

- Bench/frontend/backend/BACnet reachability can be healthy while auth context is still wrong.
- Missing or invalid `OFDD_API_KEY` should be treated as **launcher/env/runtime-context drift** unless proven otherwise.
- If Open-FDD is running on another machine, load the active `.env` into the shell or point `OPENCLAW_STACK_ENV` at it before calling auth-sensitive APIs.
- Do not frame auth-context drift itself as a confirmed product bug without clean repro under known-good auth.
- For fresh bootstrap testing, **wait for the final bootstrap-complete summary before running LAN checks**. The frontend health gate can take a while, especially in TLS mode.

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

## Testing layers

1. Frontend / web app
   - Selenium workflow validation
   - UI state, error handling, console failures
   - Data Model Testing UI parity
2. Backend / API
   - auth preflight
   - config and data-model endpoints
   - SPARQL query correctness
   - graph integrity checks
3. AI-assisted data modeling
   - payload shape validation
   - site/equipment/point topology review
   - import/export parity
   - Standard 223 / BRICK / naming sanity
4. BACnet integration
   - add-to-model flows
   - address/reference integrity
   - live property reads via gateway
5. Overnight stability
   - long-run scrape review
   - FDD pass/fail review
   - hot-reload verification
   - issue triage
6. Future field mode
   - live HVAC sanity checks
   - operator-style monitoring

## Failure classification

- Auth / launcher / env drift
- Bench limitation
- Frontend/API parity bug
- Graph hygiene / model drift bug
- BACnet integration bug
- Likely real Open-FDD product defect

File GitHub issues for confirmed product defects by default. Track harness/env failures in `openclaw/issues_log.md` unless Ben explicitly asks to file harness issues too.

## Security phases

Track security work as deliberate hardening:
- auth and token handling
- Caddy/reverse-proxy boundaries
- secrets handling
- attack-surface reduction
- phased hardening roadmap items

Do not mix security hardening work casually into unrelated defect triage.

## Generic testing procedures

Use generic procedures first so the workflow works on any LAN and any building, not just the current bench.

Start with:
- [`references/generic_lan_testing.md`](references/generic_lan_testing.md)
- [`scripts/probe_openfdd_lan.sh`](scripts/probe_openfdd_lan.sh)
- [`scripts/probe_openfdd_lan.ps1`](scripts/probe_openfdd_lan.ps1)

Those tools are intentionally host-parameterized instead of hardcoded to a single OT subnet.

## Layout (bench-focused)

| Path | Purpose |
|------|---------|
| [`bench/e2e/`](bench/e2e/) | Frontend regression, Selenium, long-run suites. |
| [`bench/sparql/`](bench/sparql/) | SPARQL parity and graph checks. |
| [`bench/fake_bacnet_devices/`](bench/fake_bacnet_devices/) | BACnet fixture devices and validation runs. |
| [`bench/scripts/fake_modbus_device.py`](bench/scripts/fake_modbus_device.py) | Standard-library fake Modbus TCP device for point-model and gateway testing. |
| [`bench/modbus_fake_device_sample.json`](bench/modbus_fake_device_sample.json) | Sample fake Modbus site/equipment/point import payload. |
| [`bench/README_modbus_fake_device.md`](bench/README_modbus_fake_device.md) | How to use the fake Modbus harness safely. |
| [`bench/rules_reference/`](bench/rules_reference/) | Reference rules for testing/cookbooks (not auto-live). |
| [`references/`](references/) | Stable protocol/checklist references for agents. |
| [`scripts/`](scripts/) | Reusable host-side helper scripts and generic LAN probes. |
| [`reports/`](reports/) | Templates and summarized outputs (avoid duplicated policy docs). |
| [`issues_log.md`](issues_log.md) | Ongoing classification trail and evidence index. |

## Standing constraints

- Do not assume clone-first or repo-first workflow.
- Do not assume OpenClaw always has SSH to the Open-FDD host.
- Start from runtime evidence: UI behavior, API responses, SPARQL, BACnet reads, logs.
- Use repo docs/reference only as support unless local edits are explicitly requested.
- Prefer generic LAN-safe procedures over current-bench-only hardcoding.

## Quick commands (when running from this repo)

```bash
./scripts/bootstrap.sh --verify
./scripts/bootstrap.sh --test
./scripts/bootstrap.sh --mode collector
./scripts/bootstrap.sh --mode model
./scripts/bootstrap.sh --mode engine
./openclaw/scripts/probe_openfdd_lan.sh --host 192.168.1.50 --mode auto
python openclaw/bench/scripts/fake_modbus_device.py --print-map
python openclaw/bench/scripts/fake_modbus_device.py --host 127.0.0.1 --port 1502 --unit-id 1
```

## Clone-friendly defaults for new OpenClaw instances

When spawning a new OpenClaw instance for Open-FDD work, default it to this posture:
- treat the stack as **externally running** until proven local
- read `SKILL.md`, `HANDOFF_PROTOCOL.md`, `README.md`, and the latest `issues_log.md` section first
- use generic LAN probes before one-off curls
- use the fake Modbus harness before inventing a new Modbus fixture
- keep site-specific secrets and bench-only notes out of committed repo files
- promote reusable lessons into `openclaw/` so the next clone starts smarter
