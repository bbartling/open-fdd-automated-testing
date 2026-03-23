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

Do not over-claim from sparse points.

## Why this exists

The overnight run is richer and slower. The integrity sweep is short and frequent.

It exists to answer:
- can we still authenticate?
- can we still reach the backend?
- can we still query the graph?
- can we still read a BACnet-side point?
- are we obviously drifting before the overnight run even starts?

That makes the overnight run more trustworthy and less likely to waste a whole night on a broken launch context.
