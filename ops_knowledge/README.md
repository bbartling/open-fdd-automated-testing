# Ops Knowledge

Reusable operations knowledge for AI-assisted Open-FDD deployments.

## Scope

This knowledge base is shared, graph-first guidance intended to work across many buildings and topologies.

Primary source set for MCP-assisted workflows:
- `open-fdd-afdd-stack` docs and API contracts
- `diy-bacnet-server` docs and gateway contracts
- `open-fdd` engine docs (rule semantics and runner behavior)
- future `easy-aso` docs and deployment patterns

## Rules

- Keep reusable knowledge in `ops_knowledge/` as building-agnostic patterns.
- Keep per-site notes in `site_memory/` and treat them as temporary overlays.
- Never encode fixed BACnet device IDs, fixed point names, or bench-only assumptions as reusable logic.

## OpenClaw Fill-In Convention

OpenClaw should populate:
- live evidence snippets
- timestamps and environment metadata
- PASS/FAIL tables from runtime verification

Cursor agents should maintain:
- architecture principles
- endpoint contracts
- validation playbooks
- troubleshooting ladders
