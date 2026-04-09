# Installing `open-fdd-lab` skill for OpenClaw

Canonical skill source: `openclaw/SKILL.md` in this repo.

Install this skill when you want an OpenClaw instance to help with:
- Open-FDD bench / deployment testing
- AI-assisted data modeling
- BRICK/SPARQL/BACnet/Modbus validation
- generic LAN health probing
- fake-device benching for new stack features
- OpenClaw-side context and testing-script maintenance for Open-FDD

## Paths OpenClaw resolves

OpenClaw resolves skills from:
- `workspace/skills/<skill-name>/SKILL.md`
- optional extra skill directories depending on OpenClaw version/config

## Option A — symlink into workspace skills

```bash
mkdir -p ~/.openclaw/workspace/skills
ln -sfn /path/to/open-fdd-afdd-stack/openclaw ~/.openclaw/workspace/skills/open-fdd-lab
```

## Option B — copy

Copy the whole `openclaw/` directory into `skills/open-fdd-lab/`.

If you want a thinner copy, keep at least:
- `SKILL.md`
- `README.md`
- `HANDOFF_PROTOCOL.md`
- `references/`
- `scripts/`

For Modbus-capable clones, also keep:
- `bench/README_modbus_fake_device.md`
- `bench/scripts/fake_modbus_device.py`
- `bench/modbus_fake_device_sample.json`

## Verify

```bash
openclaw doctor
# or
openclaw skills list
```

## Recommended read order once installed

1. `SKILL.md`
2. `README.md`
3. `HANDOFF_PROTOCOL.md`
4. `references/testing_layers.md`
5. `references/generic_lan_testing.md`

## Source of truth

Track the skill in `open-fdd-afdd-stack/openclaw/` and keep updates versioned in git so new OpenClaw instances on other buildings can inherit the same context without needing direct SSH to the original bench.
