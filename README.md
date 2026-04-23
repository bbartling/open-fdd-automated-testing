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


---


## The Open-FDD AFDD Platform 

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
git clone https://github.com/bbartling/open-fdd-afdd-stack.git
```

### Standard HTTP bootstrap (no TLS) and app login



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

```

---

### Standard Maintenance

Standard update procedures pull the latest versions of all applications, including the DIY BACnet Server, safely remove unused Docker container images, validate that the API and unit tests pass, and deploy the system with the MCP server running on the latest content.

Note that the username and password must be reconfigured, along with BACnet OT NIC settings and the BACnet instance ID for the Open FDD deployment at the specific site.


```bash
cd open-fdd-afdd-stack

printf '%s' 'YourSecurePassword' | ./scripts/bootstrap.sh \
  --maintenance \
  --update \
  --verify \
  --force-rebuild \
  --test \
  --diy-bacnet-tests \
  --user ben \
  --password-stdin \
  --frontend \
  --bacnet-address 192.168.204.18/24:47808 \
  --bacnet-instance 123456 \
  --with-mcp-rag
```


The `--enable-mcp` flag starts the internal MCP/RAG service on port `8090`.



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

### OpenClaw execution boundaries (important)

In many deployments, OpenClaw runs outside the Docker host shell and can only call exposed HTTP APIs.

- OpenClaw **can** run API workflows (`/config`, `/sites`, `/data-model/*`, `/run-fdd`, analytics/download routes) when given the correct base URL and Bearer key.
- OpenClaw **cannot** run host-local shell tasks like `./scripts/bootstrap.sh` unless it is granted host shell access.
- If you need reset verification from OpenClaw-only mode, prefer API evidence and clearly separate:
  - **API reset**: `POST /data-model/reset` (graph reset + stale active fault-state deactivation)
  - **Full fault-history cleanup**: `POST /data-model/reset?clear_fault_history=true`
  - **Host bootstrap reset path**: `./scripts/bootstrap.sh --reset-data` (calls the full cleanup endpoint above)

For API-only agents, provide `OFDD_API_URL`/base URL and `OFDD_API_KEY` (Bearer) from `stack/.env`.

### Open Claw Model Routing Prompt

Just drop this prompt right into Open Claw—it’s helped me avoid hitting API limits. I think it encourages the framework to use simple, low-cost models for easier tasks, while reserving more advanced (and expensive) models only for the tasks that truly require deeper reasoning. Open Claw is currently being tested with the Open AI Codex subscription. 


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

## Online Documentation

This application is part of a broader ecosystem that together forms the **Open FDD AFDD Stack**, enabling a fully orchestrated, edge-deployable analytics and optimization platform for building automation systems.

* 🔗 **DIY BACnet Server**
  Lightweight BACnet server with JSON-RPC and MQTT support for IoT integrations.
  [Documentation](https://bbartling.github.io/diy-bacnet-server/) · [GitHub](https://github.com/bbartling/diy-bacnet-server)

* 📖 **Open FDD AFDD Stack**
  Full AFDD framework with Docker bootstrap, API services, drivers, and React web UI.
  [Documentation](https://bbartling.github.io/open-fdd-afdd-stack/) · [GitHub](https://github.com/bbartling/open-fdd-afdd-stack)

* 📘 **Open FDD Fault Detection Engine**
  Core rules engine with `RuleRunner`, YAML-based fault logic, and pandas workflows.
  [Documentation](https://bbartling.github.io/open-fdd/) · [GitHub](https://github.com/bbartling/open-fdd) · [PyPI](https://pypi.org/project/open-fdd/)

* ⚙️ **easy-aso Framework**
  Lightweight framework for Automated Supervisory Optimization (ASO) algorithms at the IoT edge.
  [Documentation](https://bbartling.github.io/easy-aso/) · [GitHub](https://github.com/bbartling/easy-aso) · [PyPI](https://pypi.org/project/easy-aso/0.1.7/)


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

## Dependencies

* Python 3.12+
* `open-fdd>=2.3.1`
* `rdflib>=7.5.0,<8`
* `pyparsing>=2.1.0,<3.2`
* `pydantic>=2.4,<3`
* `pydantic-settings>=2.2,<3`
* `psycopg2-binary>=2.9.9`
* `fastapi>=0.115,<1`
* `python-multipart>=0.0.9`
* `uvicorn[standard]>=0.30`
* `httpx>=0.27`
* `requests>=2.31`
* `PyJWT>=2.8,<3`
* `argon2-cffi>=23.1`
* `docker>=7.0,<8`
* `pip` + virtual environment tooling (`python3 -m venv`)
* Docker (for container runs)


---

## License

MIT