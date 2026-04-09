# Future: OpenClaw clones on live HVAC / Open-FDD sites

## What varies per deployment

- **Brick / RDF graph** — site, equipment, points, namespaces.
- **HVAC archetype** — chillers vs RTUs vs district systems; rules and SPARQL differ.
- **BACnet** device inventory and credentials.
- **Operator workflows** — alarms, schedules, ticketing integrations (future).

## Unknown / to be defined

- **Gold standard** “day-one” skill pack for a new clone (minimal vs full operator).
- How much lives in **repo `openclaw/`** vs **per-site git** vs **OpenClaw workspace `memory/`**.
- **Secrets** handling (never in `issues_log` or committed env files).

## What to do now

1. Keep **`open-fdd-afdd-stack/openclaw/`** as the versioned starter pack for stack-side OpenClaw clones.
2. Keep the repo split explicit:
   - engine-owned guidance belongs in `open-fdd`
   - stack-side testing, gateway, frontend, fake-device, and import/export guidance belongs here
3. Append **site-specific** lessons to `issues_log.md` during pilots; promote stable patterns into this file or nearby references.
4. When a pattern repeats across two sites, open a **GitHub issue** to codify it as:
   - a checklist under `openclaw/references/`
   - a reusable helper under `openclaw/scripts/`
   - or a bench fixture under `openclaw/bench/`
5. Reuse `bench/scripts/fake_modbus_device.py` and `bench/modbus_fake_device_sample.json` as the default Modbus bring-up kit for new OpenClaw clones instead of rebuilding a fake device each time.

This file is intentionally incomplete — update as real deployments teach us.
