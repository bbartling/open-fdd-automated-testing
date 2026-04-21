# Graph-Driven Rebuild Postcheck

Use this order after rebuilds and patches.

## 1) Graph integrity

- Enumerate sites/equipment/points from model-backed APIs.
- Confirm points resolve to Brick classes.
- Confirm BACnet references exist where expected.
- Confirm rule input mappings exist where required.

## 2) Applicability from graph

- For each selected device/equipment, derive applicable faults from graph + YAML rules.
- Do not start from active runtime rows.

## 3) Runtime execution

- Trigger FDD run.
- Verify `run_ts` advances and run is healthy.

## 4) Fault-state projection

- Verify active/state rows map back to graph-derived device/equipment identity.
- Check name-vs-UUID alias scenarios when present.

## 5) Frontend consistency

- Verify dropdowns and views reflect graph-derived applicability.
- Verify active overlays match runtime state.

## OpenClaw fill-in template

- Environment: API URL, branch, SHA, auth mode
- Timestamped endpoint snippets
- PASS/FAIL table by step (1-5)
- Remaining gaps + smallest next fix
