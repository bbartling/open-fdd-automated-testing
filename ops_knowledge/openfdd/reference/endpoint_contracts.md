# Endpoint Contracts (Graph-First)

This reference captures contract intent for AI/MCP workflows.

## Primary Open-FDD endpoints

- `/faults/bacnet-devices`: enumerates BACnet devices from modeled points/equipment.
- `/faults/bacnet-device-faults`: graph-derived applicability + runtime active overlay per device.
- `/faults/active`: active runtime faults.
- `/faults/state`: active + cleared runtime fault state.
- `/download/faults`: export view for downstream analysis (may include historical pre-fix rows).
- `/analytics/fault-results-raw`: low-level evidence checks.

## Cross-repo MCP document sources

MCP augmentation should include docs from:
- this repo (`open-fdd-afdd-stack`)
- `diy-bacnet-server` (gateway and BACnet edge behavior)
- `open-fdd` engine repo (rule runner, schemas, rule semantics)
- future `easy-aso` repo (automation/orchestration patterns)

## Contract principles

- Device/equipment alignment must tolerate UUID/name alias differences where legacy runtime rows exist.
- `active_fault_ids` in device applicability must align with `/faults/active` for same site/device context.
- Contract examples may show bench IDs, but logic must remain device-ID agnostic.
