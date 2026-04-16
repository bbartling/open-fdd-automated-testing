# Open-FDD AFDD stack

[![Discord](https://img.shields.io/badge/Discord-Join%20Server-5865F2.svg?logo=discord&logoColor=white)](https://discord.gg/Ta48yQF8fC)
[![CI](https://github.com/bbartling/open-fdd-afdd-stack/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/bbartling/open-fdd-afdd-stack/actions/workflows/ci.yml)
![MIT License](https://img.shields.io/badge/license-MIT-green.svg)
![Development Status](https://img.shields.io/badge/status-Beta-blue)
![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python&logoColor=white)
[![Engine (PyPI)](https://img.shields.io/pypi/v/open-fdd?label=engine%20(PyPI))](https://pypi.org/project/open-fdd/)
[![Stack version](https://img.shields.io/badge/stack%20(pyproject.toml)-2.0.14-3776AB?labelColor=444)](https://github.com/bbartling/open-fdd-afdd-stack/blob/main/pyproject.toml)

<div align="center">

![open-fdd logo](https://raw.githubusercontent.com/bbartling/open-fdd-afdd-stack/main/image.png)

</div>

Open-FDD is an open-source knowledge graph fault-detection platform for HVAC systems that helps facilities optimize their energy usage and cost-savings. Because it runs on-prem, facilities never have to worry about a vendor hiking prices, going dark, or walking away with their data. The platform is an AFDD stack designed to run inside the building, behind the firewall, under the owner’s control. It transforms operational data into actionable, cost-saving insights and provides a secure integration layer that any cloud platform can use without vendor lock-in. U.S. Department of Energy research reports median energy savings of roughly 8–9% from FDD programs—meaningful annual savings depending on facility size and energy spend.

The content that used to live here is now **`afdd_stack/`** in **[bbartling/open-fdd](https://github.com/bbartling/open-fdd)**. The README below is **legacy**; prefer the monorepo. The **rules engine** is still **[`open-fdd` on PyPI](https://pypi.org/project/open-fdd/)**.


---

## Documentation


* 📖 **[Stack Docs](https://bbartling.github.io/open-fdd-afdd-stack/)** — bootstrap, Docker, API, drivers, React UI
* 📘 **[Engine Docs](https://bbartling.github.io/open-fdd/)** — RuleRunner, YAML rules, pandas ([repo](https://github.com/bbartling/open-fdd), [`open-fdd` PyPI](https://pypi.org/project/open-fdd/))
* 📕 **[PDF Docs](https://github.com/bbartling/open-fdd/blob/master/pdf/open-fdd-docs.pdf)** — offline build: `python3 scripts/build_docs_pdf.py`
* ✨ **[LLM Workflow](https://bbartling.github.io/open-fdd-afdd-stack/modeling/llm_workflow#copy-paste-prompt-template-recommended)** — export → tag → import
* 🤖 **[Open-Claw](https://bbartling.github.io/open-fdd-afdd-stack/openclaw_integration)** — model context, MCP, API workflows

---

## Quick Starts

### Open-FDD Engine-only (rules engine, no Docker) PyPi

If you only want the Python rules engine (without the full platform stack), you can use it in standard Python environments.

```bash
pip install open-fdd
```


### Open-FDD AFDD Platform Manually by the Human

Open-FDD uses Docker and Docker Compose to orchestrate and manage all platform services within a unified containerized environment. The bootstrap script (`./scripts/bootstrap.sh`) is **Linux-only** and intended for IoT edge applications using Docker exclusively.

### Debian / Ubuntu setup

- **Git:** Install Git if needed, e.g. `sudo apt update && sudo apt install git`.
- **Docker:** Follow the official guide to install Docker Engine (and Compose): [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/).

### Prerequisites (Ubuntu / Debian-style)

After Docker is installed, add your Linux user to the **`docker`** group so you can run `docker` without `sudo` (log out and back in, or use `newgrp`, for the group change to apply):

```bash
sudo usermod -aG docker "$USER"
newgrp docker
docker ps
```

Create a Python virtual environment and install **`argon2-cffi`** (used to hash passwords for bootstrap):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install argon2-cffi
```

Clone the repository:

```bash
git clone https://github.com/bbartling/open-fdd.git
```

### Standard HTTP bootstrap (no TLS) and app login

The `--bacnet-address` value is the static bind address for BACnet, which is the usual setup for BACnet/IP on operations technology (OT) LANs. Bootstrap supports **dual-NIC** hosts: use this address on the OT interface; your other interface can use DHCP for outbound internet access.

```bash
cd open-fdd-afdd-stack

printf '%s' 'YourSecurePassword' | ./scripts/bootstrap.sh \
  --bacnet-address 192.168.204.16/24:47808 \
  --bacnet-instance 12345 \
  --user ben \
  --password-stdin
```

**Dashboard “BACnet” status:** The strip is green when the **API container** can reach the DIY gateway (`OFDD_BACNET_SERVER_URL`, usually `http://host.docker.internal:8080` from compose). The knowledge graph (`config/data_model.ttl`, `ofdd:bacnetServerUrl`) may still say `http://localhost:8080` for local dev; **`OFDD_BACNET_SERVER_URL` in `stack/.env` always wins** over that value in containers so drivers and config stay aligned with Docker. **GET `/config`** merges the same env URL into the JSON for the UI so the Config screen matches runtime. Contract tests: `openfdd_stack/tests/platform/test_platform_config_contract.py`. The DIY BACnet service is usually **`network_mode: host`**, so it is **not** on the same Docker bridge as `api` / `frontend` — traffic is **host ↔ bridge** routing (and often firewall/hairpin rules), not ordinary “sibling container” DNS on the default network. On many Linux hosts **hairpin routing fails**: both `host.docker.internal` and the Docker bridge gateway (for example `172.19.0.1`) time out even though `curl http://localhost:8080/server_hello` on the host works. Fix it by passing **`OFDD_BACNET_ADDRESS`** into the API and scraper (compose does this from `stack/.env`) so the stack retries **`http://<that-LAN-IPv4>:8080`**, or set **`OFDD_BACNET_SERVER_URL`** explicitly in `stack/.env` to that URL. Bootstrap **`--bacnet-address`** writes both. **`./scripts/bootstrap.sh --verify`** and a **full** default bootstrap (when the host gateway responds on :8080) can **auto-write** `OFDD_BACNET_SERVER_URL` to the host’s default-route IPv4 (or the IPv4 from `OFDD_BACNET_ADDRESS` when set) and recreate **api** and **bacnet-scraper** so the API→gateway check passes without manual edits.

**If every URL still times out** (including `http://<LAN-IP>:8080` after auto-fix): this is almost always **host firewall or routing** blocking **Docker bridge → host TCP :8080**, not a stale UI build. **Rebuilding the frontend container does not fix BACnet online** — the browser calls the API, and the API must open TCP to the gateway. Inspect **`sudo ufw status`**, **`nft`/`iptables` FORWARD** rules, and **`rp_filter`** / hairpin settings for the Docker bridge. Host-only curl can succeed while the UI is red if the frontend was talking to the wrong API host; use the app through **Caddy on port 80 or 8880** (recommended), not raw `:5173`, unless you know what you are doing. Raw **:5173** uses `vite preview` with `VITE_API_BASE=/api`: requests go to `/api/bacnet/…` and the preview proxy must **strip `/api`** before forwarding to Uvicorn (fixed in `frontend/vite.config.ts`); without that, the Stack strip shows API/BACnet offline even when the API is healthy.

**Rebuild API + frontend after a git pull (normal operators):**

```bash
cd open-fdd-afdd-stack/stack
docker compose build api frontend && docker compose up -d api frontend
```

Or one maintenance pass (pull, rebuild stack, optional tests): `./scripts/bootstrap.sh --maintenance --update --verify --force-rebuild` (add `--test` if you want pytest too).

**LAN / firewall / ports:** See [Standard HTTP lab: remote LAN access](https://bbartling.github.io/open-fdd-afdd-stack/getting_started#standard-http-lab-remote-lan-access) in the Stack Docs (bearer keys in `stack/.env`, `http://` vs `https://`, ports **80** / **8880** / **8000**, and automatic **ufw**).

### Standard hardened stack — self-signed TLS (Caddy) and app login

Open-FDD runs over TLS with self-signed certificates, and there is no access to the Open-FDD API or the DIY BACnet server Docker container APIs.


```bash
cd open-fdd-afdd-stack

printf '%s' 'YourSecurePassword' | ./scripts/bootstrap.sh \
  --bacnet-address 192.168.204.16/24:47808 \
  --bacnet-instance 12345 \
  --user ben \
  --password-stdin \
  --caddy-self-signed
```

### Bootstrap Troubleshooting

```bash
./scripts/bootstrap.sh --doctor
```

Also available is the **partial stack** mode: `./scripts/bootstrap.sh --mode collector`, `--mode model`, or `--mode engine`. See the `Docs` below for more information.

### Run tests (`--test`)

Use the same bootstrap script for local verification (no separate CI recipe required on the machine):

```bash
cd open-fdd-afdd-stack
./scripts/bootstrap.sh --test
```

This runs frontend lint, TypeScript `tsc`, Vitest, backend `pytest`, and Caddyfile validation when Docker is available. If Docker is missing or the daemon is not usable, Caddy validation is skipped; frontend and backend tests still run when Node/npm and Python (with dev deps) are available.

Optional one-shot creation of `.venv` and `pip install -e ".[dev]"` when `pytest` is not installed:

```bash
OFDD_BOOTSTRAP_INSTALL_DEV=1 ./scripts/bootstrap.sh --test
```

Combine with health checks: `./scripts/bootstrap.sh --verify --test`.

---

## Python layout


Local development (co-developing engine + stack) and push to a new or existing development branch:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e "/path/to/open-fdd[dev]"
pip install -e ".[dev]"
pytest openfdd_stack/tests -v
```

---

## License

MIT