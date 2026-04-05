# Open-FDD AFDD stack

[![Discord](https://img.shields.io/badge/Discord-Join%20Server-5865F2.svg?logo=discord&logoColor=white)](https://discord.gg/Ta48yQF8fC)
[![CI](https://github.com/bbartling/open-fdd-afdd-stack/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/bbartling/open-fdd-afdd-stack/actions/workflows/ci.yml)
![MIT License](https://img.shields.io/badge/license-MIT-green.svg)
![Development Status](https://img.shields.io/badge/status-Beta-blue)
![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python&logoColor=white)
[![Engine (PyPI)](https://img.shields.io/pypi/v/open-fdd?label=engine%20(PyPI))](https://pypi.org/project/open-fdd/)

<div align="center">

![open-fdd logo](https://raw.githubusercontent.com/bbartling/open-fdd-afdd-stack/main/image.png)

</div>

Open-FDD is an open-source knowledge graph fault-detection platform for HVAC systems that helps facilities optimize their energy usage and cost-savings. Because it runs on-prem, facilities never have to worry about a vendor hiking prices, going dark, or walking away with their data. The platform is an AFDD stack designed to run inside the building, behind the firewall, under the owner’s control. It transforms operational data into actionable, cost-saving insights and provides a secure integration layer that any cloud platform can use without vendor lock-in. U.S. Department of Energy research reports median energy savings of roughly 8–9% from FDD programs—meaningful annual savings depending on facility size and energy spend.

This repository is the **full on-prem AFDD platform**, which bootstraps entirely with Docker and runs the **rules engine** installed from **[`open-fdd` on PyPI](https://pypi.org/project/open-fdd/)**.


---

## Documentation

- 📖 [**Stack documentation**](https://bbartling.github.io/open-fdd-afdd-stack/) — Bootstrap, Docker Compose, API, drivers, React UI (this repo’s `docs/` on push).
- 📘 [**Engine documentation**](https://bbartling.github.io/open-fdd/) — `RuleRunner`, rule YAML, pandas; source [bbartling/open-fdd](https://github.com/bbartling/open-fdd), package [`open-fdd` on PyPI](https://pypi.org/project/open-fdd/).
- 📕 [**Documentation PDF**](https://github.com/bbartling/open-fdd/blob/master/pdf/open-fdd-docs.pdf) — Offline / Kindle-friendly. Regenerate from this repo with `python3 scripts/build_docs_pdf.py` → `pdf/open-fdd-docs.pdf`.
- ✨ [**LLM prompt (copy/paste template)**](https://bbartling.github.io/open-fdd-afdd-stack/modeling/llm_workflow#copy-paste-prompt-template-recommended) — Export the data model (knowledge graph) as JSON, run an **external** LLM-assisted tagging workflow, then re-import; the API parses JSON on import.
- 🤖 [**Open‑Claw / external agents**](https://bbartling.github.io/open-fdd-afdd-stack/openclaw_integration) — `GET /model-context/docs`, `GET /mcp/manifest`, data-model export/import for your own OpenAI-compatible stack.

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
cd open-fdd

printf '%s' 'YourSecurePassword' | ./scripts/bootstrap.sh \
  --bacnet-address 192.168.204.16/24:47808 \
  --bacnet-instance 12345 \
  --user ben \
  --password-stdin
```

> **NOTE:** Both the DIY BACnet server and Open-FDD API in the **Standard HTTP bootstrap (no TLS)** configuration still require bearer tokens for authorization. These are defined in `open-fdd/stack/.env` and are set during the bootstrapping process.


### Standard hardened stack — self-signed TLS (Caddy) and app login

Open-FDD runs over TLS with self-signed certificates, and there is no access to the Open-FDD API or the DIY BACnet server Docker container APIs.


```bash
cd open-fdd

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