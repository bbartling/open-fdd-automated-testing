---
title: BACnet
nav_order: 6
has_children: true
---

# BACnet

BACnet is the **default data driver** for Open-FDD. Discovery and scraping are handled by an embedded [rusty-bacnet](https://github.com/jscott3201/rusty-bacnet) driver (PyO3 bindings to an ASHRAE 135-2020 stack written in Rust). There is no separate gateway container — the API and scraper both talk to the BACnet/IP network directly over UDP 47808.

---

## Setup (do this before the platform scrapes data) {#setup}

1. **Start the platform** — e.g. `./scripts/bootstrap.sh`. The `bacnet-scraper` container runs under the `selene` compose profile with `network_mode: host` so rusty-bacnet can bind UDP 47808 on the host NIC that reaches your BAS.
2. **Discover devices** — `POST /bacnet/whois_range` broadcasts Who-Is and returns the I-Am responders. Each device is upserted into SeleneDB as a `:bacnet_device` node.
3. **Enumerate objects** — `POST /bacnet/point_discovery_to_graph` reads a single device's `object-list`, enriches each object (name, description, units), and persists them as `:bacnet_object` nodes linked to the device via `exposesObject` edges. Each object carries a `concept_curie` pointing at a [Mnemosyne](https://github.com/jscott3201/selenepack-smartbuildings) BACnet concept.
4. **Create application points** — add `:point` nodes via the Sites/Equipment/Points CRUD API, then bind objects to points with a `protocolBinding` edge (property defaults to `present_value`).
5. **Scraper runs automatically** — on the configured interval the scraper walks `:bacnet_object`→`:protocolBinding`→`:point` bindings and writes samples via SeleneDB `ts_write`. Per-device failures are isolated; one flaky device doesn't stall the loop.

---

## Configuration

Driver bind and timeout knobs live in [Configuration](../configuration):

- `OFDD_BACNET_INTERFACE` (default `0.0.0.0`)
- `OFDD_BACNET_PORT` (default `47808`)
- `OFDD_BACNET_BROADCAST_ADDRESS` (default `255.255.255.255`)
- `OFDD_BACNET_APDU_TIMEOUT_MS` (default `6000`)
- `OFDD_BACNET_DEVICE_INSTANCE` (optional — register this node as a Device on the network; required for COV subscriptions)
- `OFDD_BACNET_SCRAPE_ENABLED` (toggle — set `false` to idle the scraper without tearing down the container)
- `OFDD_BACNET_SCRAPE_INTERVAL_MIN` (default `5`)

---

## Verification and lab (OpenClaw bench)

| Page | Description |
|------|-------------|
| [BACnet graph context](graph_context) | What the graph must expose for BACnet-backed verification and rules. |
| [BACnet-to-fault verification](fault_verification) | Evidence chain from fake devices through reads, SPARQL, rules, to faults. |

Example SPARQL files for modeling checks live under `openclaw/bench/sparql/` in the repository (not on this docs site).

---

## BACnet/SC (future)

The driver's `Transport` abstraction has a `BipTransport` implementation today and will grow an `ScTransport` for [BACnet/SC (Secure Connect)](https://www.ashrae.org/technical-resources/bookstore/bacnet) via rusty-bacnet's WebSocket client. See the queued 2.5e slice in the graph milestone for status.
