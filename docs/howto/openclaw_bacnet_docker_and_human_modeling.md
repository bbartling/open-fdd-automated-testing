---
title: OpenClaw, Docker BACnet, and human data modeling
parent: How-to Guides
nav_order: 18
---

# OpenClaw, Docker BACnet, and human data modeling

This page is written for **OpenClaw** (and similar agents) that run **inside Docker** on the same Compose project as Open-FDD, and for **operators** doing **AI-assisted Brick tagging** in the browser. It is indexed into the optional **MCP RAG** corpus when you bootstrap with `--with-mcp-rag` (see [MCP RAG service](../operations/mcp_rag_service)).

---

## 1) Critical: `bacnet-server` uses host networking (not a bridge peer)

In **`stack/docker-compose.yml`**, **`bacnet-server`** (`container_name: openfdd_bacnet_server`) sets **`network_mode: host`**. That means:

- JSON-RPC **HTTP :8080** and BACnet **UDP** are bound on the **Docker host’s** network stack (same as `curl http://127.0.0.1:8080` from the **host**).
- The service is **not** attached to the Compose **user-defined bridge** (`stack_default`, etc.). You should **not** assume the hostname **`openfdd_bacnet_server`** resolves from other containers to that HTTP listener—often it **does not**, or it resolves but still does not reach host-port-8080 the way you expect.

**What actually works from bridge containers** (`openfdd_api`, `openfdd_bacnet_scraper`, an OpenClaw container after `docker network connect …`):

- **`http://host.docker.internal:8080`** — only if that container has **`extra_hosts: host.docker.internal:host-gateway`** (the stack’s **`api`** and **`bacnet-scraper`** images do). Match **`OFDD_BACNET_SERVER_URL`** in `stack/.env` when hairpin is broken (LAN IP is common on Linux).
- **`http://<HOST_LAN_IP>:8080`** — same port the host uses; must be routable from the container (firewall / rp_filter).

**What does *not* work from inside a normal container:**

- **`http://127.0.0.1:8080` / `localhost:8080`** — that is the **container’s** loopback, not the host’s → **connection refused** unless something inside *that* container listens on 8080.
- **`http://openfdd_api:8080`** — wrong idea: **`openfdd_api`** serves the **REST API on port 8000**, not the BACnet gateway on 8080 → **connection refused**.

**Preferred path for OpenClaw (and most agents):** do **not** talk to diy-bacnet-server :8080 directly unless you deliberately mirror the stack’s `extra_hosts` + URL. Instead call the **Open-FDD API** on **port 8000** and use **`POST /bacnet/server_hello`**, **`POST /bacnet/whois_range`**, etc. The API container already has the right route to the host gateway via **`OFDD_BACNET_SERVER_URL`**.

**Quick check from the API container** (host gateway via compose default):

```bash
docker exec openfdd_api python3 -c "
import os, httpx
u = (os.environ.get('OFDD_BACNET_SERVER_URL') or 'http://host.docker.internal:8080').rstrip('/')
r = httpx.post(
    f'{u}/server_hello',
    json={'jsonrpc':'2.0','id':'0','method':'server_hello','params':{}},
    timeout=8.0,
    headers={'Authorization': 'Bearer ' + (os.environ.get('OFDD_BACNET_SERVER_API_KEY') or '')},
)
print('URL', u, '->', r.status_code, r.text[:400])
"
```

---

## 2) Two-layer test plan (gateway vs Open-FDD proxy)

Use this order so you can tell **where** a failure is.

### Layer A — Host gateway :8080 (from a container that has `host.docker.internal`)

From **`openfdd_api`** (or any container with the same **`extra_hosts`** line), hit **`$OFDD_BACNET_SERVER_URL`** (default `http://host.docker.internal:8080`) for **`/server_hello`**, **`/docs`**, **`/openapi.json`** with the **BACNET** Bearer token when required.

If this fails with **timeout**, the problem is **host routing / hairpin / firewall** between the bridge and host :8080—not OpenClaw “using the wrong hostname format” for `openfdd_bacnet_server`.

### Layer B — Open-FDD proxy (recommended for OpenClaw)

From a container attached to the stack network:

- Base: **`http://openfdd_api:8000`** (or `http://api:8000` from the same Compose project)
- **`POST /bacnet/server_hello`**, **`POST /bacnet/whois_range`**, **`POST /bacnet/point_discovery_to_graph`**, … with **`Authorization: Bearer <OFDD_API_KEY>`** (and the same allowlisting rules as the UI).

Use **`GET http://openfdd_api:8000/bacnet/gateways`** to see the configured default gateway URL. See [BACnet gateway RPC contract](../bacnet/gateway_rpc_contract) and [OpenClaw integration](../openclaw_integration).

If **Layer B** times out but the **host** can reach the gateway with **POST** (JSON-RPC), e.g. `curl -sS -X POST http://127.0.0.1:8080/server_hello -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":"0","method":"server_hello","params":{}}'`, the break is almost always **API → host:8080** (`OFDD_BACNET_SERVER_URL`, iptables/ufw, hairpin)—not “OpenClaw vs OpenClaw”. A bare **GET** to `/server_hello` returns **405 Method Not Allowed**; that only proves something is listening on :8080, not that JSON-RPC works.

---

## 2b) OpenClaw-specific checklist (avoids the common traps)

1. **Attach OpenClaw to the stack’s default network** (name is often **`stack_default`**; run `docker network ls` and `docker inspect openfdd_api --format '{{json .NetworkSettings.Networks}}'` to copy the exact network ID/name). Without this, **`openfdd_api`** does not resolve.

   One-shot (replace the OpenClaw container name if yours differs):

   ```bash
   docker network connect stack_default openclaw-openclaw-gateway-1
   ```

   If Docker prints **“endpoint … already exists in network stack_default”**, you are **already attached** — nothing more to do. Confirm:

   ```bash
   docker inspect openclaw-openclaw-gateway-1 --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
   ```

   You want **`stack_default`** in that list (alongside **`openclaw_default`** or similar).

   After connect, from inside OpenClaw you can use **container DNS** (no host port mapping required):

   | Service | Typical base URL from OpenClaw |
   |---------|--------------------------------|
   | Open-FDD API | `http://openfdd_api:8000` (alias `http://api:8000`) — use `Authorization: Bearer <OFDD_API_KEY>` from `stack/.env` |
   | MCP RAG (if `--with-mcp-rag`) | `http://openfdd_mcp_rag:8090` — see [MCP RAG service](../operations/mcp_rag_service) |
   | Caddy (UI + `/api` proxy) | `http://openfdd_caddy:80` |
   | Postgres | `db:5432` (only if you intentionally give tools DB access; prefer the API) |

2. **Use port 8000 for the API**, not 8080: `http://openfdd_api:8000/health`, then `/bacnet/server_hello`.
3. If you **must** curl :8080 from OpenClaw’s container, add **`--add-host=host.docker.internal:host-gateway`** (or compose equivalent) so **`host.docker.internal`** behaves like **`api`** / **`bacnet-scraper`**. Plain `docker run` OpenClaw images often omit that.
4. **Do not expect `openfdd_bacnet_server:8080`** from bridge containers when **`network_mode: host`** is in use—that model is for **operators on the host** and for docs that describe the **container name** for logs (`docker logs openfdd_bacnet_server`), not for embedded DNS reachability from arbitrary peers.

### 2c) Interpreting “what I have access to” reports (avoid a false blocker)

Agents often produce a split like **have: API + MCP + graph** / **lack: `host.docker.internal` + `/bacnet/*` timeouts**. Treat that as **two different checks**:

| Check | If it “fails” from OpenClaw | Meaning |
|--------|---------------------------|--------|
| `getent hosts host.docker.internal` or raw `http://host.docker.internal:8080` | Expected on many OpenClaw images | **Not required** for the supported path. OpenClaw should call **`http://openfdd_api:8000/bacnet/...`**, not :8080 on the host. |
| `POST http://openfdd_api:8000/bacnet/server_hello` (with `Authorization: Bearer <OFDD_API_KEY>`) | Timeout | **`openfdd_api` cannot reach `OFDD_BACNET_SERVER_URL`** (usually `http://host.docker.internal:8080` on Linux). Fix on the **Open-FDD host**: hairpin / firewall / routing, or run **`./scripts/bootstrap.sh --verify --autofix-bacnet`** so `stack/.env` uses a **LAN IP :8080** URL and recreates **api** + **bacnet-scraper**. |

So: **missing `host.docker.internal` inside OpenClaw is normal** and does **not** prove the gateway is down. **Timeouts on `/bacnet/*` via the API** do prove the **API → gateway** hop is broken until the operator fixes the host URL or network.

**Host-side proof** (operator runs on the server, not inside OpenClaw):

```bash
docker exec openfdd_api python3 -c "
import os, httpx
u = (os.environ.get('OFDD_BACNET_SERVER_URL') or 'http://host.docker.internal:8080').rstrip('/')
key = os.environ.get('OFDD_BACNET_SERVER_API_KEY') or ''
h = {'Authorization': 'Bearer ' + key} if key else {}
r = httpx.post(f'{u}/server_hello', json={'jsonrpc':'2.0','id':'0','method':'server_hello','params':{}}, timeout=8.0, headers=h)
print(u, '->', r.status_code, r.text[:200])
"
```

If that **times out** but **`curl -X POST http://127.0.0.1:8080/server_hello ...`** on the host works, focus on **Docker bridge → host :8080** (same **Layer A vs Layer B** split in section 2 above).

**Automated smoke (host, same logic as verify):** from the repo root on the Docker host:

```bash
./scripts/smoke_bacnet_api_to_gateway.sh
```

Exit code **0** means at least one **`bacnet_rpc_base_candidates`** URL answered **`server_hello`** from inside **`openfdd_api`**.

### 2d) “First five” checks for a containerized agent (on `stack_default`)

Replace **`$API_KEY`** with **`OFDD_API_KEY`** from `stack/.env`. Base **`http://openfdd_api:8000`**.

1. **`GET /health`** — `curl -sS -o /dev/null -w "%{http_code}" http://openfdd_api:8000/health` → expect **200**.
2. **`GET /bacnet/gateways`** — `curl -sS -H "Authorization: Bearer $API_KEY" http://openfdd_api:8000/bacnet/gateways` → expect **JSON** with default gateway.
3. **`POST /bacnet/server_hello`** (proxy) — JSON body `{"jsonrpc":"2.0","id":"0","method":"server_hello","params":{}}` with same **Bearer** → expect **200** and JSON **result** (not a hang).
4. If step **3** **times out**, the fault is **not** “OpenClaw cannot resolve `host.docker.internal`”. Have the **operator** on the host run **`./scripts/smoke_bacnet_api_to_gateway.sh`** and **`./scripts/bootstrap.sh --verify --autofix-bacnet`** (or set **`OFDD_BACNET_SERVER_URL`** to **`http://<host-LAN-IP>:8080`** and recreate **api** + **bacnet-scraper**).
5. (Optional) **`POST /bacnet/whois_range`** with a small body after **3** succeeds — confirms RPC path beyond **`server_hello`**.

**Known bad assumptions (quick list):**

- **`http://openfdd_bacnet_server:8080`** — wrong default mental model when **`bacnet-server` uses `network_mode: host`**; use the API proxy or **`OFDD_BACNET_SERVER_URL`** from **`openfdd_api`** / **`bacnet-scraper`**.
- **`http://localhost:8080`** or **`http://127.0.0.1:8080`** from **inside OpenClaw** — that is the **OpenClaw** container’s loopback, not the host gateway.
- **`http://openfdd_api:8080`** — wrong port; the API listens on **8000**.

---

## 3) Human operator path (React) — discovery, export JSON, tags, re-import

OpenClaw should know operators often work in the **UI** first; agents can mirror the same APIs.

| Goal | Where in the UI | API equivalent |
|------|------------------|----------------|
| Sites | **BACnet tools** → Step 1 — Sites | `POST /sites`, … |
| Who-Is / discovery / add BACnet to graph | **BACnet tools** → Step 2 | `POST /bacnet/*`, then add-to-model actions |
| Export / import Brick tags | **Data model** — export JSON, edit or LLM, import | `GET /data-model/export`, `PUT /data-model/import` |
| SPARQL checks | **Data model** — SPARQL panel | `POST /data-model/sparql` |
| Preset equipment counts | **Data model testing** (after `equipment_type` / tags) | Same graph; see testing docs |

Canonical rules for **export → tag → import** (Brick types, `rule_input`, **polling**, `equipment` array, **no extra top-level keys**) live in:

- [AI-assisted data modeling](../modeling/ai_assisted_tagging)
- [LLM workflow (prompt + validate)](../modeling/llm_workflow)
- [Using the React dashboard](../frontend) — navigation table and **Data model** / **BACnet tools** rows

For **HTTP automation** (no browser), use the same flow as [OpenClaw integration](../openclaw_integration): `GET /data-model/export`, `GET /model-context/docs`, `PUT /data-model/import`, plus **`GET /mcp/manifest`** on the core API for tool discovery.

---

## 4) MCP RAG and published docs

When **`--with-mcp-rag`** is enabled, the sidecar index includes this repo’s **`docs/`** plus sparse upstream **`docs/`** trees (engine, DIY gateway, easy-aso) as described in [MCP RAG service](../operations/mcp_rag_service). Keeping **this page** and the **modeling** links accurate improves retrieval for OpenClaw.

**Published hub (human + web-capable agents):** [Data modeling](https://bbartling.github.io/open-fdd-afdd-stack/modeling/) and [OpenClaw integration](https://bbartling.github.io/open-fdd-afdd-stack/openclaw_integration) on GitHub Pages.

---

## See also

- [OpenClaw integration](../openclaw_integration) — `model-context`, `mcp/manifest`, bearer auth, split LAN setup
- [OpenClaw context bootstrap](../operations/openclaw_context_bootstrap) — ordered read list for fresh clones
- [BACnet overview](../bacnet/overview) — stack vs gateway roles
