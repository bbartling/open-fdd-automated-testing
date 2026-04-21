# Fault Applicability Contract

## Applicability source

Applicability must come from:
- graph-modeled points
- Brick class matches
- semantic input mappings
- rule YAML requirements

## Active state source

Active state must come from runtime projections:
- `fault_state`
- `fault_results` derived views

## UI contract

UI should show:
- configured/applicable faults from graph-backed applicability
- active overlays from runtime state

UI should not:
- infer configured faults from active rows alone
- assume no configured faults when active rows are empty

## Proven lesson

Treat this as the encoded fix for dropdown/applicability drift: graph-driven applicability first, runtime activity second.
