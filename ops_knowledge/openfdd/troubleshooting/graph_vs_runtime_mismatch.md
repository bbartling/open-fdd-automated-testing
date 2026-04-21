# Graph vs Runtime Mismatch Ladder

Use this ladder to classify and triage contradictions.

## 1) Graph says applicable, runtime says inactive

Often valid (fault currently inactive). Check recent run and thresholds.

## 2) Graph says applicable, UI says no configured faults

Likely frontend applicability/view bug. Validate `/faults/bacnet-device-faults` payload first.

## 3) Runtime says active, applicability misses active flags

Likely backend join/projection bug between fault-state and device mapping.

## 4) Runtime says active, provenance lacks point identity

Provenance enrichment gap. Validate evidence payload and export mapping path.

## 5) Discovery sees devices, graph lacks points

Discovery-to-graph ingestion/modeling bug; discovery alone is not enough.

## Triage rule

Resolve graph-model correctness first, then runtime mapping, then UI presentation.
