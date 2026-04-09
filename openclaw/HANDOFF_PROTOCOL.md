# Cursor ↔ OpenClaw handoff protocol (Open-FDD lab)

OpenClaw and Cursor do not talk to each other directly. The shared ground truth is this git tree, especially:

- `openclaw/issues_log.md` — append-only diagnosis + status (use dated sections)
- `openclaw/logs/bootstrap-test-*.txt` — full command transcripts
- `openclaw/README.md` — OpenClaw-side operating notes
- `openclaw/references/generic_lan_testing.md` — host-agnostic test procedures
- `openclaw/bench/README_modbus_fake_device.md` — fake Modbus bench procedure when Modbus is in scope

## Default mission posture

OpenClaw is testing-first for Open-FDD:
- external web app and API verification
- BRICK/SPARQL/data-model parity checks
- BACnet add-to-model and live-read validation
- Modbus fake-device, gateway, and add-to-model validation
- AI-assisted data-model payload review and refinement
- overnight scrape/FDD/hot-reload review
- issue filing for confirmed product defects

Repo-local source editing is optional and only when explicitly requested.

Do not treat clone-first local development as the baseline OpenClaw workflow.

## Repo boundary (important)

Keep the repo split explicit in handoffs:
- `open-fdd` = engine-only repo / expression-rule ownership
- `open-fdd-afdd-stack` = frontend / API / gateway / data-model / OpenClaw bench assets

Do not leave stack-side notes that imply the expression-rule cookbook or other engine-only references belong here long term.

## Access assumptions (important)

Some OpenClaw instances may have SSH access to the Open-FDD host; others may only have LAN/VPN access to the app edge.

Do not assume the agent has:
- SSH to the host
- access to `stack/.env`
- bearer tokens
- plaintext UI credentials

Always record which access level the current run had:
- **host-aware** (SSH / logs / local loopback checks available)
- **edge-only** (frontend and reachable LAN endpoints only)

## Current bench truth (do not lose this context)

- Bench services can all be reachable while auth context is still wrong.
- Current direct authenticated backend failure (`FORBIDDEN: Invalid API key`) should be treated as launcher/env/runtime-context drift unless proven otherwise.
- Do not declare auth drift a confirmed product bug by default.
- For bootstrap testing, wait for the final script completion summary before doing client-side interpretation. A slow frontend health gate can create misleading early results.

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

## File-only loop

No Cursor↔OpenClaw HTTP is required. Both sides communicate through repo files.

Typical loop:
1. OpenClaw reads `issues_log.md`, `README.md`, and any referenced notes.
2. OpenClaw runs tests or model-review steps.
3. OpenClaw writes logs and appends concise findings.
4. Cursor reads the same files, makes code/doc changes, and appends next steps.
5. OpenClaw retests from the updated instructions.

## Roles (intentional)

| Who | Role |
|-----|------|
| human | run gateway, provide access, decide scope, merge PRs |
| Cursor / engineer | product-code edits, architecture, deeper refactors |
| OpenClaw | tester, reproducer, AI-assisted data-model reviewer, evidence collector |

## Failure classification required in handoffs

Classify each fail/block as:
- auth/launcher/env drift
- bench limitation
- frontend/API parity bug
- graph hygiene/model drift bug
- BACnet integration bug
- likely real Open-FDD product defect

Only product defects should become GitHub issues by default. Keep harness/runtime drift in `issues_log.md` unless explicitly told otherwise.

## Issues log format

Append under today’s `## YYYY-MM-DD` header, one block per run:

```markdown
- **runner:** openclaw | cursor | human
- **access:** host-aware | edge-only
- **branch:** …
- **command / prompt:** …
- **log:** `openclaw/logs/<file>.txt`
- **result:** pass | fail | blocked
- **classification:** …
- **summary:** one line
- **next for senior:** optional
```

## Generic LAN-first procedure when SSH is unavailable

Use `openclaw/references/generic_lan_testing.md` and the probe scripts under `openclaw/scripts/`.

That procedure is the default for:
- new buildings
- remote deployments
- unknown LANs
- cases where the OpenClaw instance is not running on the Open-FDD host

## Modbus procedure when Modbus is in scope

Use `openclaw/bench/README_modbus_fake_device.md` plus:
- `openclaw/bench/scripts/fake_modbus_device.py`
- `openclaw/bench/modbus_fake_device_sample.json`

Preferred order:
1. prove raw local reads against the fake device
2. prove gateway `/modbus/read_registers`
3. prove backend proxy read path
4. prove frontend Modbus tab behavior
5. only then import fake points into a clearly fake site and verify polling / TTL / SPARQL parity

## Host-aware procedure when SSH is available

When SSH exists, gather:
1. active `.env` keys relevant to edge/API mode
2. `docker ps` for caddy/api/frontend
3. caddy logs
4. local loopback API checks
5. then client-side curl checks

When testing bootstrap behavior, keep HTTP and TLS runs as separate phases.

## AI-assisted data-modeling handoff expectations

When the task is model-oriented rather than stack-oriented, record:
- payload source and goal
- whether the payload is draft, malformed, partial, or intended for import
- site/equipment/point topology concerns
- BACnet reference concerns
- BRICK / Standard 223 concerns
- what was validated by UI/API/export/import vs what remains assumption

## Skills / context

Versioned skill: `openclaw/SKILL.md` plus `references/`, `scripts/`, and bench artifacts.

Recommended read order for an OpenClaw session:
1. `openclaw/SKILL.md`
2. `openclaw/README.md`
3. latest relevant section in `openclaw/issues_log.md`
4. `openclaw/references/testing_layers.md`
5. `openclaw/references/generic_lan_testing.md`
