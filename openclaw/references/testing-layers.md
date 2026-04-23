# Testing layers

Open-FDD validation should be described in layers so agents do not confuse one kind of evidence for another.

## Layer 1. Static/code review

Examples:

- reading backend/frontend code paths
- reviewing docs and YAML rules
- comparing branch status and PRs

Good for:

- likely cause analysis
- smallest fix identification
- documentation updates

## Layer 2. API/runtime verification

Examples:

- `GET /sites`
- `GET /analytics/fault-summary`
- `GET /download/faults`
- `POST /data-model/reset`
- `POST /data-model/reset?clear_fault_history=true`

Good for:

- proving real behavior in deployment
- catching config drift
- validating auth, timeseries, and fault outputs

## Layer 3. Bench verification

Examples:

- BACnet discovery on fake devices
- data-model export/import loops
- BACnet reads and writes on the DIY test bench
- proving rule behavior against the known fake fault schedule

Good for:

- end-to-end chain validation
- provenance checks
- scrape and FDD cadence checks

## Layer 4. Host/bootstrap orchestration

Examples:

- `./scripts/bootstrap.sh --reset-data`
- compose restarts
- Docker network assumptions

Important nuance:

An agent may have API visibility without having shell access to the Docker-capable host context. Record that boundary explicitly.

## Layer 5. Live HVAC operational validation

Examples:

- verifying discovery against real controllers
- checking model quality and point semantics
- tuning fault thresholds and reviewing false positives/negatives
- building operator-facing confidence summaries

Default to observation-first and change-control discipline.
