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

Older material also ships as **`afdd_stack/`** in **[bbartling/open-fdd](https://github.com/bbartling/open-fdd)**. **This repository** is the canonical Docker + React stack, bootstrap, and stack docs (see links below). The **rules engine** library remains **[`open-fdd` on PyPI](https://pypi.org/project/open-fdd/)**.


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

The `--bacnet-address` value is the static **BACnet/IP (UDP)** bind for **bacpypes3** in diy-bacnet-server (**`OFDD_BACNET_ADDRESS`**, e.g. `192.168.204.18/24:47808`), which is the usual setup on operations technology (OT) LANs. It is **not** the same thing as **`OFDD_BACNET_SERVER_URL`**: the DIY gateway’s HTTP **:8080** listens on the **Docker host**, so the API and scraper default to **`http://host.docker.internal:8080`** (see Compose / `stack/.env`). Bootstrap supports **dual-NIC** hosts: use `--bacnet-address` on the OT interface; your other interface can use DHCP for outbound internet access.

```bash
cd open-fdd-afdd-stack

printf '%s' 'YourSecurePassword' | ./scripts/bootstrap.sh \
  --bacnet-address 192.168.204.16/24:47808 \
  --bacnet-instance 12345 \
  --user ben \
  --password-stdin
```


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
./scripts/bootstrap.sh --verify
./scripts/bootstrap.sh --smoke-bacnet-api-gateway   # same hop as scripts/smoke_bacnet_api_to_gateway.sh; alias: --smoke-bacnet-api
./scripts/bootstrap.sh --verify --smoke-bacnet-api-gateway   # health checks then explicit API→gateway smoke
```

If BACnet shows **API→gateway** timeout, on the host run **`./scripts/bootstrap.sh --smoke-bacnet-api-gateway`** or **`./scripts/smoke_bacnet_api_to_gateway.sh`** (same hop as **`./scripts/bootstrap.sh --verify`** BACnet line). If **`curl -X POST http://127.0.0.1:8080/server_hello`** with a JSON-RPC body works on the host but the smoke script fails, try **`./scripts/bootstrap.sh --verify --autofix-bacnet`** (opt-in hairpin repair) or set **`OFDD_BACNET_SERVER_URL`** in `stack/.env` per [BACnet overview](docs/bacnet/overview.md) and [OpenClaw + Docker BACnet](docs/howto/openclaw_bacnet_docker_and_human_modeling.md). A bare **GET** to `/server_hello` returns **405**; use **POST** with `{"jsonrpc":"2.0","id":"0","method":"server_hello","params":{}}`.

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


## Optional: OpenClaw + MCP (AI-Assisted Data Modeling & FDD)

This section enables AI-assisted data modeling, tagging, and fault detection (FDD) using OpenClaw and the MCP (Model Context Protocol) service.

---

### 1. Bootstrap AFDD stack with MCP enabled

```bash
cd open-fdd-afdd-stack

printf '%s' 'YourSecurePassword' | ./scripts/bootstrap.sh \
  --bacnet-address 192.168.204.16/24:47808 \
  --bacnet-instance 12345 \
  --user ben \
  --password-stdin \
  --enable-mcp
```

The `--enable-mcp` flag starts the internal MCP/RAG service on port `8090`.

---

### 2. Setup OpenClaw in a separate Docker container

```bash
git clone https://github.com/openclaw/openclaw.git
cd openclaw
chmod +x docker-setup.sh
./docker-setup.sh
```

To access the OpenClaw terminal UI:

```bash
docker exec -it openclaw-openclaw-gateway-1 bash
openclaw tui
```

---

### 3. Configure `.env` for Open-FDD access

Edit:

```bash
open-fdd-afdd-stack/stack/.env
```

After bootstrapping, this file contains the API keys and access tokens required for the Open-FDD platform. These can be used by OpenClaw to interact with the system.

---

### 4. Connect OpenClaw to the AFDD Docker network

```bash
docker network connect stack_default openclaw-openclaw-gateway-1
```

Verify the connection:

```bash
docker inspect openclaw-openclaw-gateway-1 \
  --format '{{json .NetworkSettings.Networks}}'
```

---

### 5. Test MCP connectivity from OpenClaw

Once connected, OpenClaw can access the MCP service at:

```text
http://openfdd_mcp_rag:8090
```

Alternatively, you can use the container IP address (e.g., `http://172.x.x.x:8090`).

---

### What this enables

* Query MCP for building data models
* Assist with Brick data model tagging
* Generate and refine FDD rules
* Analyze faults and telemetry data
* Automate workflows against the AFDD stack

---

### Architecture (simplified)

```text
OpenClaw (AI Agent)
        |
        | HTTP (Docker internal network)
        v
MCP / RAG Service (openfdd_mcp_rag:8090)
        |
        v
Open-FDD AFDD Stack (API + DB + BACnet)
```

### Open Claw Model Routing Prompt

Just drop this prompt right into Open Claw—it’s helped me avoid hitting API limits. I think it encourages the framework to use simple, low-cost models for easier tasks, while reserving more advanced (and expensive) models only for the tasks that truly require deeper reasoning.


```text
## Model Routing Policy
When analyzing test results, classify each task before processing:
SIMPLE (use primary model):
- Pass/fail test results
- HTTP status code errors (404, 500, timeout)
- Missing UI elements or broken selectors
- Test environment setup failures
- Syntax errors or import failures
COMPLEX (use thinking model)
- Unexpected behavior that passed but shouldn't have
- Race conditions or timing-dependent failures
- Security vulnerabilities
- Performance degradation patterns
- Failures that span multiple components or files
Default to SIMPLE unless the test result shows ambiguous or multi-layered behavior.
Always classify first, then process. Never use the thinking model for a task that fits the SIMPLE list.

```


---


## Local development


Python layout (co-developing engine + stack) and push to a new or existing development branch:

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