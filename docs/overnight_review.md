# Overnight Review

The overnight review is the daily discipline that turns unattended testing into useful engineering evidence.

## Morning questions

Every morning review should answer these questions explicitly:

1. Did frontend Selenium pass?
2. Did SPARQL/API parity pass?
3. Did BACnet discovery succeed for all expected fake devices?
4. Did scraped telemetry arrive in Open-FDD for the expected points?
5. Did expected fake-device fault windows produce corresponding Open-FDD fault results?
6. Did YAML rule hot reload still work?
7. Which failures are likely real product bugs?
8. Which failures are more likely auth, environment, timing, or operator setup drift?

## Outcome categories

Use three categories:

- **PASS** - evidence is present and the behavior matched expectation
- **FAIL** - evidence is present and the behavior clearly did not match expectation
- **INCONCLUSIVE** - the test did not gather enough reliable evidence to decide

## Evidence sources

Expected evidence sources include:

- script exit codes
- per-step logs
- Open-FDD API responses
- frontend-visible state
- BACnet fake-device schedules
- fault APIs such as `/faults/state`, `/faults/active`, and downloadable fault results
- later: Docker container logs for scraper / API / FDD correlation

## Review standard

Do not call something a product bug unless the evidence chain is specific enough to reproduce.

Examples:
- a repeatable BACnet discovery 422 for one device may be issue-worthy
- a blanket 401 from protected endpoints may simply indicate auth drift
- a missing suite log is an automation reliability issue, even if the product is fine
