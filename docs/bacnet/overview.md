---
title: BACnet Overview
parent: BACnet
nav_order: 1
---

# BACnet Integration

Open-FDD embeds the [rusty-bacnet](https://github.com/jscott3201/rusty-bacnet) driver — a PyO3 binding to a full ASHRAE 135-2020 BACnet stack written in Rust. Both the API container (for ad-hoc discovery calls) and the scraper container (for periodic reads) instantiate a BACnet/IP client directly; there is no separate gateway container.

Discovered devices and objects live as typed nodes in **SeleneDB** (`:bacnet_network`, `:bacnet_device`, `:bacnet_object`). Points are authored via the Sites / Equipment / Points CRUD API and linked to BACnet objects via `protocolBinding` edges. The scraper walks those bindings every interval and writes `present-value` samples via SeleneDB `ts_write`.

---

## Components

| Component | Purpose |
|-----------|---------|
| **rusty-bacnet Python package** | PyO3 wrapper over the Rust protocol stack. Provides an async `BACnetClient` (WhoIs, ReadProperty, ReadPropertyMultiple, WriteProperty, Who-Has). Installed via the `[bacnet]` optional-dependencies extra. |
| **`openfdd_stack.platform.bacnet.BipTransport`** | Thin adapter around `BACnetClient` for the BACnet/IP transport. `ScTransport` (BACnet/SC) is on the roadmap; the `Transport` ABC is the seam. |
| **`BacnetDriver`** | Orchestrator: runs WhoIs + object-list enumeration, converts rusty-bacnet types to frozen dataclasses, and persists discovery results into SeleneDB via `upsert_bacnet_device` / `upsert_bacnet_object`. |
| **`BacnetScraper`** | Periodic loop: `load_scrape_plan(selene)` walks the `:bacnet_device → :bacnet_object → :point` graph, issues one `ReadPropertyMultiple` per device in parallel, writes samples with `entity_id = point.id`. |
| **Data model** | `:site`, `:equipment`, `:point` + `:bacnet_device`, `:bacnet_object`, `:protocolBinding`. Configured via the React frontend or the CRUD API. Single source of truth for what to scrape. |

---

## Ports

| Port | Protocol | Use |
|------|----------|-----|
| 47808 | UDP | BACnet/IP (driver binds this inside the scraper / API containers) |

Only **one** process on the host can use port 47808. The scraper container runs with `network_mode: host` so it binds directly to the host NIC that reaches the BAS.

---

## Discovery → points workflow

Phase 2.5 retired the "push a TTL into the graph" path in favour of typed graph nodes + explicit protocol bindings. The current shape:

1. **WhoIs broadcast** — `POST /bacnet/whois_range` returns the responding devices. Each becomes a `:bacnet_device` node with its BACnet instance, IP+port address, and (optionally) vendor/model/firmware from a follow-up `ReadPropertyMultiple`.
2. **Object enumeration** — `POST /bacnet/point_discovery_to_graph` walks one device's `object-list` property, optionally enriches each entry with `object-name` / `description` / `units`, and writes one `:bacnet_object` node per entry. The `concept_curie` field aligns the object to a Mnemosyne BACnet concept (`mnemo:BacnetAnalogInput` etc.) so downstream graph queries can traverse into Brick / 223P via `equivalentTo` edges.
3. **Point authoring** — Add `:site`, `:equipment`, and `:point` nodes via the existing CRUD API. Each point's application-layer metadata (Brick class, rule input, unit) stays independent of the BACnet protocol detail.
4. **Protocol binding** — Link a `:bacnet_object` to a `:point` via `bind_object_to_point(object_id, point_id, bacnet_property='present_value')`. The scraper reads this edge to know what to fetch for which point.
5. **Scraping** — Every `OFDD_BACNET_SCRAPE_INTERVAL_MIN` minutes, the scraper loads the full plan from Selene, groups by device, issues one RPM per device, and writes samples. A per-device failure is isolated — one flaky device doesn't stall the loop.

---

## Configuration

See [Configuration](../configuration) for the full list. BACnet-specific knobs:

| Env var | Default | Purpose |
|---------|---------|---------|
| `OFDD_BACNET_INTERFACE` | `0.0.0.0` | Bind interface for the BACnet/IP UDP socket. |
| `OFDD_BACNET_PORT` | `47808` | UDP port (ASHRAE 135 standard). |
| `OFDD_BACNET_BROADCAST_ADDRESS` | `255.255.255.255` | Who-Is broadcast target. Set to the subnet broadcast when needed. |
| `OFDD_BACNET_APDU_TIMEOUT_MS` | `6000` | APDU timeout for every request the driver issues. |
| `OFDD_BACNET_DEVICE_INSTANCE` | unset | When set, the driver registers itself as a Device object on the network (required for COV subscriptions and some vendor gateways). |
| `OFDD_BACNET_SCRAPE_ENABLED` | `true` | Short-circuit flag. Set `false` to idle the scraper without tearing down the container. |
| `OFDD_BACNET_SCRAPE_INTERVAL_MIN` | `5` | Cadence. Fractional minutes allowed for testing. |
