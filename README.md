# Open-FDD AFDD stack

[![Discord](https://img.shields.io/badge/Discord-Join%20Server-5865F2.svg?logo=discord&logoColor=white)](https://discord.gg/Ta48yQF8fC)
[![CI](https://github.com/bbartling/open-fdd-afdd-stack/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/bbartling/open-fdd-afdd-stack/actions/workflows/ci.yml)
![MIT License](https://img.shields.io/badge/license-MIT-green.svg)
![Development Status](https://img.shields.io/badge/status-Beta-blue)
![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python&logoColor=white)
[![Engine (PyPI)](https://img.shields.io/pypi/v/open-fdd?label=engine%20(PyPI))](https://pypi.org/project/open-fdd/)
[![Stack version](https://img.shields.io/badge/stack%20(pyproject.toml)-2.0.16-3776AB?labelColor=444)](https://github.com/bbartling/open-fdd-afdd-stack/blob/main/pyproject.toml)

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


### Validate Hardware

Before running the full Open-FDD stack, check the available disk, RAM, swap, and CPU resources on the machine.

```bash
printf '%s\n' "Current machine resources:" "Disk: $(df -h / | awk 'NR==2 {print $2 " total, " $3 " used, " $4 " free, " $5 " full"}')" "RAM: $(free -h | awk '/^Mem:/ {print $2 " total, " $7 " available"}')" "Swap: $(free -h | awk '/^Swap:/ {print $2 " total, " $3 " used"}')" "CPU: $(nproc) cores"
````

Example output:

```text
Current machine resources:
Disk: 58G total, 21G used, 35G free, 38% full
RAM: 7.9Gi total, 6.0Gi available
Swap: 2.0Gi total, 0B used
CPU: 4 cores
```

Minimum practical hardware:

```text
Disk: 60–80 GB free
RAM: 8–16 GB
CPU: 4 logical cores
```

Recommended hardware for running Open-FDD + OpenClaw + MCP/RAG together:

```text
Disk: 500 GB+ free recommended
RAM: 32 GB recommended
CPU: 8 logical cores recommended
```

The stack may run on smaller machines, but use caution. Docker builds, frontend builds, MCP/RAG services, database containers, and OpenClaw agents can consume disk and memory quickly.

For lightweight testing, a Raspberry Pi 5 with 8 GB RAM and enough disk space may work well. For heavier workflows that include OpenClaw, MCP/RAG, full Docker rebuilds, frontend builds, and test runs, a larger workstation-class machine is strongly recommended.


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

This retains existing auth and BACnet NIC settings when those were previously bootstrapped (unless override flags are passed).

Recommended recurring patch command:

```bash
cd open-fdd-afdd-stack
./scripts/bootstrap.sh --maintenance --update --verify --force-rebuild --with-mcp-rag
```

This updates/rebuilds to latest code.

### What this enables

* Query MCP for model context and retrieval
* Speed up Brick tagging and import workflows
* Generate/refine FDD rules and diagnostics
* Analyze faults and telemetry trends
* Automate repeatable AFDD bench workflows

---

### OpenClaw and AI worker docs

OpenClaw runtime details, sibling-container networking, API auth patterns, worker prompts, and model-context/MCP workflows are maintained in docs:

- [OpenClaw integration](docs/openclaw_integration.md)
- [OpenClaw agent bootstrap](docs/howto/openclaw_agent_bootstrap.md)
- [Operations testing plan](docs/operations/testing_plan.md)


---

## Online Documentation

This application is part of a broader ecosystem that together forms the **Open FDD AFDD Stack**, enabling a fully orchestrated, edge-deployable analytics and optimization platform for building automation systems.

* 🔗 **DIY BACnet Server**
  Lightweight BACnet server with JSON-RPC and MQTT support for IoT integrations.
  [Documentation](https://bbartling.github.io/diy-bacnet-server/) · [GitHub](https://github.com/bbartling/diy-bacnet-server)

* 📖 **Open FDD AFDD Stack**
  Full AFDD framework with Docker bootstrap, API services, drivers, and React web UI.
  [Documentation](https://bbartling.github.io/open-fdd-afdd-stack/) · [LLM Prompt Template](https://bbartling.github.io/open-fdd-afdd-stack/modeling/llm_workflow#copy-paste-prompt-template-recommended) · [GitHub](https://github.com/bbartling/open-fdd-afdd-stack)

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