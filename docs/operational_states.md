# Operational States

Open-FDD development and field verification naturally fall into three operational states.

## 1. Application validation state

In this state, the Open-FDD product itself is under test.

Examples:
- frontend regressions
- API regressions
- SPARQL parity failures
- BACnet discovery path failures
- rules hot-reload regressions

Primary concern: **does the product still behave correctly?**

## 2. AI-assisted data-modeling state

In this state, the building model is being created, repaired, or improved.

Examples:
- exporting discovered points
- mapping Brick classes
- assigning `rule_input`
- validating import payloads
- checking SPARQL and UI consistency after import

Primary concern: **is the semantic model good enough to support FDD and operator workflows?**

## 3. Live HVAC monitoring state

In this state, the platform is acting like a real monitoring and diagnostics system.

Examples:
- BACnet scraping into Open-FDD
- rules running on incoming timeseries
- active faults being exposed through APIs and UI
- operator-facing summaries and maintenance follow-up

Primary concern: **is the system producing trustworthy operational insight?**

## Why this matters

The same script or endpoint can behave differently depending on which state you are in.

A UI regression in application validation state is a product problem.
A bad Brick mapping in AI-assisted data-modeling state may not be a product bug at all.
A missing fault in live HVAC monitoring state could be caused by telemetry, rule selection, rolling-window tuning, or platform execution timing.

Using these states helps keep debugging disciplined.
