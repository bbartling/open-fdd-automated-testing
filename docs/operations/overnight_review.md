---
title: Overnight review
parent: Operations
nav_order: 1
---

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
7. Are the key docs pages and README links still valid?
8. What documentation gaps or unclear areas should be improved for both humans and AI agents?
9. Which failures are likely real product bugs?
10. Which failures are more likely auth, environment, timing, or operator setup drift?

## Outcome categories

Use three categories:

- **PASS** - evidence is present and the behavior matched expectation
- **FAIL** - evidence is present and the behavior clearly did not match expectation
- **INCONCLUSIVE** - the test did not gather enough reliable evidence to decide

For BACnet-to-fault verification, the overnight review should produce a durable report in `reports/` using the BACnet verification template when possible.

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

For docs and link review, make sure the branch context is explicit:
- prefer `master` as the default branch under review
- optionally check one intended development branch when that branch is the real destination for an unreleased fix
- do not mix findings across many branches; the working assumption is two branches only: `master` and one active dev branch

Examples:
- a repeatable BACnet discovery 422 for one device may be issue-worthy
- a blanket 401 from protected endpoints may simply indicate auth drift
- a missing suite log is an automation reliability issue, even if the product is fine
- a broken docs link on `master` matters immediately; a fix that only exists on the active dev branch should be called out as branch-specific
