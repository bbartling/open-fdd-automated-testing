---
title: Open-FDD integrity sweep
parent: Operations
nav_order: 3
---

# Open-FDD Integrity Sweep

This note defines the lightweight every-20-minute integrity sweep for Open-FDD test benches and future OT-LAN deployments.

## Goal

Verify that Open-FDD is still reachable, authenticated, semantically queryable, and loosely aligned with BACnet-side reality.

This is not the same as a full overnight review. It is a short recurring integrity pulse.

The sweep should not behave like a dumb uptime ping. It should behave like a strong human building operator using the semantic model as the main window into the HVAC system.

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
- `GET /data-model/check`
- authenticated `POST /data-model/sparql`
- other authenticated backend routes that are expected to work in the current environment

Do not assume a historically-used route is unauthenticated forever; classify real behavior from the current launch context.

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
Use the BACnet-side API to perform one or more lightweight live point reads for modeled points when available.

Examples of acceptable operations:
- a property read
- a point read
- equivalent BACnet gateway sensor read against a known modeled point/device

The point is not to prove the entire building every 20 minutes. The point is to prove the BACnet-side world is still reachable and not obviously diverged from the model.

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
- live sensor reads: representative model-derived values that support the judgment

## Real human operator logic for future live HVAC mode

When the same sweep runs against real HVAC instead of the current fake-data bench, it should mimic a competent human building operator.

That means using all of the following when available:
- the site location as defined in the Open-FDD data model
- current outdoor-air sensor readings discovered from the model
- recent outdoor trend context available through Open-FDD history/trending paths
- current and historical weather support data from Open-Meteo
- local time, season, and occupancy context
- model-derived plant/air/zone equipment relationships

Examples of intelligent reasoning:
- if it is cold outside, representative heating systems should broadly look ready to make heat
- if it is hot outside, representative cooling systems should broadly look ready to make cooling
- if outdoor temperature is mild, avoid over-claiming; many systems may reasonably idle or economize
- compare command vs feedback when possible instead of trusting one point in isolation
- use weather as a sanity input, not as proof of a control bug by itself

Bias reads toward operator-meaningful and seasonally critical components derived from the knowledge graph, for example:
- winter: boilers, hot-water systems, pumps, heating enable, hot-water temperature, representative heating-distribution points
- summer: chillers, condenser/chilled-water systems, pumps, cooling enable, chilled-water temperature, representative cooling-distribution points
- air systems: fan status, airflow/pressure relationships, supply-air temperature, key commands vs feedback
- occupied/unoccupied logic: if the building is unoccupied, focus more on temperature protection, freeze/overheat risk, and whether equipment that should be off is still running

The point is to verify that important devices are online and that the building broadly makes sense at an operator level, not to burn reads on worthless controller internals when more meaningful plant/air/zone points exist.

The dashboard should eventually tell the human not only that integrity is broken, but whether the building appears:
- broadly comfortable
- mechanically suspicious
- energy-wasteful
- safety- or occupant-risking

## Interaction with the overnight workflow

The every-20-minute integrity sweep should not blindly compete with the richer overnight workflow.

Rule:
- if the dedicated 6 PM to 6 AM overnight Open-FDD testing/review workflow is active, the normal 20-minute integrity sweep should stand down or stay quiet unless it detects a genuinely new high-signal alert
- the overnight workflow is already doing broader PR/log/docs/BACnet/FDD review, so duplicate low-signal chatter is not useful
- outside the overnight workflow, the integrity sweep is the lightweight daytime safety/integrity pulse
- when the sweep logic or operator heuristics improve in a durable way, record that in repo docs and push it so future clones inherit the improvement
- when model/API budget pressure is high, throttle the sweep to auth + graph + a minimal model-derived BACnet sanity check instead of spending budget on repeated narrative or broad browser-driven checks

### Current mode
Today this is primarily a fake-data / test-bench environment.

So the sweep should focus on:
- auth
- backend reachability
- graph/data-model integrity
- BACnet point readability
- expected device presence
- whether the bench is trustworthy enough for the next overnight window

One subtle but important rule on this bench:
- a raw 180°F spike on a scheduled fake-device point is not automatically abnormal
- first compare it to the shared UTC schedule in `fake_bacnet_devices/fault_schedule.py`
- use `scripts/monitor_fake_fault_schedule.py` when possible so the sweep can distinguish expected fault injection from unscheduled drift
- expose that interpretation in the dashboard / temporary local summary, not only in chat text
- if 180°F appears **outside** the scheduled bounds window, classify that as a meaningful anomaly

### Future live HVAC mode
If later used on a real HVAC system, add lightweight common-sense HVAC sanity checks.

Examples:
- in winter, representative heating-related points should not look absurd relative to outdoor conditions
- in summer, representative cooling-related points should not look absurd relative to outdoor conditions
- use current outdoor-air readings plus recent history before flagging control weirdness
- use weather/season as a weak sanity input, not as proof of a control bug
- think like a comfort/safety-conscious human building operator, but stay grounded in the data model and actual point evidence

Do not over-claim from sparse points.

## Why this exists

The overnight run is richer and slower. The integrity sweep is short and frequent.

It exists to answer:
- can we still authenticate?
- can we still reach the backend?
- can we still query the graph?
- can we still read a BACnet-side point?
- does the building or bench broadly make sense right now?
- are we obviously drifting before the overnight run even starts?

That makes the overnight run more trustworthy and less likely to waste a whole night on a broken launch context.
