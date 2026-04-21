# Memory Boundaries

## Shared memory (`ops_knowledge/`)

Contains reusable patterns:
- validation workflows
- query intent and expected fields
- endpoint contracts
- troubleshooting ladders

Must NOT contain:
- hardcoded building IDs
- fixed BACnet device assumptions
- one-site network assumptions presented as universal behavior

## Site-local memory (`site_memory/`)

Contains temporary local context:
- operator handoff notes
- network quirks
- known model gaps pending graph updates

Use local notes as a patch pad, not a graph replacement.

## Anti-hardcoding rules

- Never encode one building's BACnet IDs as reusable logic.
- Never treat device names as globally meaningful identifiers.
- Never assume OT routing patterns transfer between sites.
- Always ask graph/model first.
- Fall back to local notes only when graph facts are absent or known stale.
