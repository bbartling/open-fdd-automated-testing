# Graph As Source of Truth

## Graph-first rules

- Use the Open-FDD graph/model as the primary representation of site structure.
- Infer device, equipment, and point relationships from the graph, not from UI labels or ad hoc aliases.
- Infer fault applicability from modeled points, Brick classes, semantic mappings (`rule_input`, `fdd_input`), and rule YAML inputs.
- Treat BACnet discovery as input to graph construction, not as the final source of operational truth.
- Treat frontend dropdowns and views as projections over graph-backed applicability.
- Use site-local notes only when graph facts are missing or stale.

## Building variability (explicit)

Real buildings vary widely across:
- equipment inventory and hierarchy
- point naming conventions
- BACnet instance allocations
- OT routing and gateway topology

Reusable workflows must stay graph-driven and building-agnostic.

## MCP design implication

MCP tools should query graph-backed facts first, then reconcile runtime state, then render diagnostics.
