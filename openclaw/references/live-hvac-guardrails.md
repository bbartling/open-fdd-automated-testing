# Live HVAC guardrails

Use this file when the target is a real building, not the fake bench.

## Default mode

Default to read-only and observation-first.

Do not assume BACnet writes are acceptable in live HVAC.

## Ask before

- commanding writable points
- changing schedules or setpoints
- forcing values for fault provocation
- resetting live data/model state
- changing rule thresholds in production

## Safe default work

- verify discovery visibility
- verify model completeness and semantics
- verify timeseries freshness
- verify FDD cadence and outputs
- compare observed faults to expected HVAC behavior
- identify likely false positives and false negatives
- draft tuning recommendations without applying them

## Preferred progression

1. observe
2. validate model
3. validate fault quality
4. propose tuning
5. apply changes only with approval
6. re-verify after changes

## Reporting focus

In live HVAC, reports should emphasize:

- confidence level
- operational risk
- what was observed vs changed
- candidate tuning changes
- any need for human operator review
