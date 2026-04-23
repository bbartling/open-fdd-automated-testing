# First session checklist

Use this on the first session in a fresh clone or on a new machine.

## 1. Establish deployment context

Capture:

- repo branch and SHA
- Open-FDD base URL
- auth mode available
- bench or live HVAC
- whether BACnet writes are allowed
- whether bootstrap/reset commands can run from this shell or must run elsewhere

## 2. Read the right docs

Minimum set:

- `docs/openclaw_integration.md`
- `docs/operations/openclaw_context_bootstrap.md`
- `docs/operations/testing_plan.md`

Add modeling or BACnet docs depending on the task.

## 3. Verify basic health

Typical checks:

- `GET /health`
- `GET /sites`
- `GET /run-fdd/status`
- `GET /analytics/fault-summary`
- `GET /data-model/export`

## 4. Pick the right lane

### Bench lane

Use when validating fake devices, discovery-to-graph, scrape/FDD cadence, reset semantics, provenance, or YAML rule behavior.

### Live HVAC lane

Use when validating real BAS integration, live model quality, fault tuning, or operational monitoring. Default to read-only unless writes are explicitly approved.

## 5. Leave durable notes

Before ending the session, write reusable findings into repo artifacts, not only memory.
