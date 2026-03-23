---
title: Open-FDD integrity sweep
parent: Operations
nav_order: 3
---

# Open-FDD Integrity Sweep

This note defines the lightweight every-10-minute integrity sweep for Open-FDD test benches and future OT-LAN deployments.

## Goal

Verify that Open-FDD is still reachable, authenticated, semantically queryable, and loosely aligned with BACnet-side reality.

This is not the same as a full overnight review. It is a short recurring integrity pulse.

## Hard rule: do not hard-code one bench forever

Today’s known test bench uses routes like:
- frontend: `http://192.168.204.16`
- Open-FDD backend: `http://192.168.204.16:8000`
- DIY BACnet server / gateway API: `http://192.168.204.16:8080`

But the sweep must stay flexible.

The active endpoints may differ by:
- job
- OT LAN
- host
- cloned repo
- launcher context
- VPN/tailscale/local subnet

So the sweep should first resolve the active endpoints from the current repo/env/launcher context rather than blindly trusting old static IPs.

## Minimum integrity checks

Before live point reads, derive the representative checks from the data model itself. For example:
- use SPARQL to identify current sites
- use SPARQL to identify BACnet devices currently represented in the graph
- use SPARQL to identify a small representative set of modeled/polling points
- choose BACnet-side reads based on those modeled points rather than on arbitrary hard-coded point names

This should feel like:
- a strong human building operator using the Open-FDD knowledge graph as the window into the HVAC system
- expert-level building commissioning / mechanical engineering judgment for what should broadly make sense
- expert-level web application testing / bug-hunting skepticism for the Open-FDD product and its UI/API behavior


### 1) Backend auth is available in the launch context
- verify the shell/Python context actually has the backend auth needed for direct Open-FDD API calls
- if direct authenticated backend checks cannot run, classify that as auth/config drift immediately

### 2) Open-FDD backend basic API check
Useful checks include:
- `POST /bacnet/server_hello` with `{}`
- `GET /data-model/check`

Example expected structure from `/data-model/check` can include:
- overall `status: ok`
- graph serialization state
- last FDD run metadata

### 3) SPARQL/data-model integrity check
Use one of:
- `POST /data-model/sparql`
- `POST /data-model/sparql/upload`

Good baseline query:
```sparql
PREFIX brick: <https://brickschema.org/schema/Brick#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?site ?site_label WHERE {
  ?site a brick:Site .
  ?site rdfs:label ?site_label
}
```

This confirms the backend can still query the current semantic model.

### 4) DIY BACnet-side point reality check
Use the BACnet-side API to perform one lightweight live point read for a modeled point when available.

Examples of acceptable operations:
- a property read
- a point read
- equivalent BACnet gateway sensor read against a known modeled point/device

The point is not to prove the entire building every 10 minutes. The point is to prove the BACnet-side world is still reachable and not obviously diverged from the model.

### 5) Model vs live comparison
Check that at least one expected device/point relationship still broadly makes sense:
- modeled device exists
- modeled point addressing exists
- live BACnet-side read exists for the same rough entity

If this breaks, classify it clearly:
- auth/config drift
- graph/model drift
- BACnet/device-state drift
- testbench limitation
- possible Open-FDD product behavior

## Current test-bench mode vs future real HVAC mode

The dashboard and sweep summary should explicitly surface mode awareness, not leave it implicit.

Recommended fields for every sweep/dashboard summary:
- environment mode: `TEST BENCH` or `LIVE HVAC`
- mode basis: why that mode was chosen
- operator alert level: info / warning / urgent
- seasonal/time basis: what local time/season/weather context was used
- HVAC sanity summary: what broadly makes sense for this mode

## Interaction with the overnight workflow

The every-10-minute integrity sweep should not blindly compete with the richer overnight workflow.

Rule:
- if the dedicated 6 PM to 6 AM overnight Open-FDD testing/review workflow is active, the normal 10-minute integrity sweep should stand down or stay quiet unless it detects a genuinely new high-signal alert
- the overnight workflow is already doing broader PR/log/docs/BACnet/FDD review, so duplicate low-signal chatter is not useful
- outside the overnight workflow, the integrity sweep is the lightweight daytime safety/integrity pulse

### Current mode
Today this is primarily a fake-data / test-bench environment.

So the sweep should focus on:
- auth
- backend reachability
- graph/data-model integrity
- BACnet point readability
- expected device presence

### Future live HVAC mode
If later used on a real HVAC system, add lightweight common-sense HVAC sanity checks.

Examples:
- in winter, representative heating-related points should not look absurd relative to outdoor conditions
- in summer, representative cooling-related points should not look absurd relative to outdoor conditions
- use weather/season as a weak sanity input, not as proof of a control bug
- think like a comfort/safety-conscious human building operator, but grounded in the data model and actual point evidence

Do not over-claim from sparse points.

The sweep should alternate across modeled devices to verify liveness broadly, but it should not waste cycles equally on low-value points.

Instead, in live HVAC mode it should bias toward operator-meaningful and seasonally critical components derived from the knowledge graph, for example:
- winter: boilers, hot-water systems, pumps, heating enable, hot-water temperature, representative heating distribution points
- summer: chillers, condenser/chilled-water systems, pumps, cooling enable, chilled-water temperature, representative cooling distribution points
- air systems: fan status, airflow/pressure relationships, supply-air temperature, key commands vs feedback
- occupied/unoccupied logic: if the building is unoccupied, focus more on zone temperature protection, freeze/overheat risk, and whether equipment that should be off is still running

The point is to verify that important devices are online and that the building broadly makes sense at an operator level, not to burn reads on worthless internal/controller-only points when more meaningful plant/air/zone points exist.

The dashboard should eventually tell the human not only that integrity is broken, but whether the building appears:
- broadly comfortable
- mechanically suspicious
- energy-wasteful
- safety- or occupant-risking

## Why this exists

The overnight run is richer and slower. The integrity sweep is short and frequent.

It exists to answer:
- can we still authenticate?
- can we still reach the backend?
- can we still query the graph?
- can we still read a BACnet-side point?
- are we obviously drifting before the overnight run even starts?

That makes the overnight run more trustworthy and less likely to waste a whole night on a broken launch context.


That makes the overnight run more trustworthy and less likely to waste a whole night on a broken launch context.
un more trustworthy and less likely to waste a whole night on a broken launch context.
