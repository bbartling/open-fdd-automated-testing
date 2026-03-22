# Cloning and Porting

This repo should be portable to another lab, another workstation, or another Open-FDD deployment with minimal conceptual changes.

## What should transfer cleanly

- the test phases
- the BACnet fake-device approach
- the overnight review discipline
- the SPARQL validation set
- the idea of proving telemetry-to-fault correctness rather than only checking page loads

## What usually changes per environment

- frontend URL
- API URL
- API auth setup
- site IDs / names
- BACnet gateway hostnames or IPs
- active Open-FDD rules directory
- Docker/container naming

## Portability goal

A clone of this repo should make it easy for another engineer to answer:

- Is Open-FDD healthy here?
- Is BACnet scraping working here?
- Is the building model usable here?
- Are faults being computed here?
- Are regressions visible here before they affect a real deployment?

## Engineering principle

Keep environment-specific values configurable and keep the verification logic reusable.
