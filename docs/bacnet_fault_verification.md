# BACnet-to-Fault Verification

This document defines the verification practice we need to master for both development testing and future live HVAC deployments.

## Goal

Use **independent BACnet-side evidence** plus **Open-FDD-side evidence** to prove that fault detection is behaving correctly.

This is stronger than merely checking whether a page loads or whether a fault appears somewhere in the UI.

## Required evidence chain

The target verification chain is:

1. **Fake BACnet device schedule is known**
   - use the deterministic schedules in `fake_bacnet_devices/`
   - know which devices and points should be healthy vs faulted during the review window

2. **DIY BACnet server RPC confirms source values**
   - use RPC methods such as:
     - `client_read_property`
     - `client_read_multiple`
     - `client_point_discovery`
     - `client_supervisory_logic_checks`
   - confirm the real present values seen by the BACnet gateway

3. **Open-FDD graph confirms BACnet addressing is modeled correctly**
   - query the data model for:
     - BACnet devices
     - point addressing
     - object identifiers
     - equipment relationships
     - polling points
   - use the SPARQL assets in `sparql/`

4. **Open-FDD rules context is understood**
   - identify the relevant YAML rule(s) in `rules/`
   - note the rule inputs and rolling-window assumptions
   - make sure the point/equipment mapping actually supports the rule logic

5. **Open-FDD fault outputs match the expected behavior**
   - compare expected fault windows against:
     - `/download/faults`
     - `/faults/state`
     - `/faults/active`
     - frontend fault views when useful

6. **Result is classified clearly**
   - PASS
   - FAIL
   - INCONCLUSIVE

## Overnight expectation

The overnight process should increasingly automate the following:

- pull BACnet device and point-address evidence from the Open-FDD graph
- validate that expected BACnet devices are present
- validate that expected point object identifiers are present
- compare the modeled BACnet points to the fake-device schedules
- identify which YAML rules are most relevant to the current fake faults
- compare Open-FDD fault outputs to expected rule behavior
- write a durable report for the morning review

## Minimum overnight report contents

Every overnight BACnet verification report should include:

- date/time window
- target branch context (`master` and optional dev branch if relevant)
- expected BACnet devices
- observed BACnet devices from SPARQL
- expected point/object identifiers
- observed point/object identifiers from SPARQL
- RPC observations from DIY BACnet server
- relevant YAML rule files
- rolling-window notes
- observed Open-FDD fault outputs
- PASS / FAIL / INCONCLUSIVE summary
- follow-up actions

## Current practical limitation

Today, full unattended graph verification can still be blocked by missing backend auth (`OFDD_API_KEY`) for `POST /data-model/sparql` from the test bench.

That does not change the target practice. It just means the environment must be corrected so the verification chain can run unattended.
