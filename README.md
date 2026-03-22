# Open-FDD Automated Testing

Professional validation harnesses for **Open-FDD**, **BACnet-backed fault verification**, **AI-assisted data modeling workflows**, and **live HVAC monitoring support**.

Repo: <https://github.com/bbartling/open-fdd-automated-testing>

## Why this repo exists

This repository is the practical test and operations layer around Open-FDD. It is meant to be cloned onto another workstation or test bench and used as a repeatable engineering toolkit for:

- **Advanced web application testing** for the Open-FDD frontend and API
- **Advanced data-model verification** for Brick / BACnet / SPARQL workflows
- **Advanced HVAC monitoring validation** using deterministic fake BACnet devices and expected fault windows
- **Autonomous OpenClaw-assisted operation**, where the agent can execute tests, summarize failures, investigate regressions, and draft GitHub issues when evidence is strong enough

The goal is not just to run scripts. The goal is to create **defensible evidence** that:

1. BACnet discovery is working
2. scraped telemetry is arriving in Open-FDD
3. the active YAML rule set is the rule set we think is running
4. rolling-window logic is behaving as expected
5. expected faults are actually visible through Open-FDD APIs and UI surfaces

---

## Repository layout

```text
.
├─ README.md
├─ LICENSE
├─ docs/
│  ├─ cloning_and_porting.md
│  ├─ operational_states.md
│  └─ overnight_review.md
├─ fake_bacnet_devices/
│  ├─ fault_schedule.py
│  ├─ fake_ahu_faults.py
│  ├─ fake_vav_faults.py
│  └─ README.md
├─ rules/
├─ sparql/
├─ 1_e2e_frontend_selenium.py
├─ 2_sparql_crud_and_frontend_test.py
├─ 3_long_term_bacnet_scrape_test.py
├─ 4_hot_reload_test.py
├─ automated_suite.py
├─ run_midnight_suite.cmd
├─ run_overnight_bacnet.cmd
└─ requirements-e2e.txt
```

---

## Core validation layers

### 1. Frontend and API regression testing

- Selenium-based UI smoke and regression coverage
- frontend-to-API parity checks
- SPARQL CRUD and data-model validation
- verification that visible app state matches backend truth

### 2. AI-assisted data modeling verification

- export/import Open-FDD data model flows
- Brick tagging and `rule_input` mapping validation
- SPARQL checks that confirm imported data is usable by Open-FDD
- evidence that AI-assisted tagging outputs still land in the app correctly

### 3. Live BACnet and FDD verification

- fake BACnet devices with deterministic fault schedules
- BACnet scraping validation against known bad-good windows
- YAML rule hot-reload checks
- proof that faults are computed and surfaced by Open-FDD as expected

---

## Three operational states

This repo is organized around three real operational states that Open-FDD development and deployment move through.

### 1) Application validation state

Use this state when Open-FDD itself is the thing under test.

**Purpose**
- validate frontend behavior
- validate API behavior
- catch regressions in Selenium, SPARQL, auth, hot reload, and BACnet integration

**Primary scripts**
- `1_e2e_frontend_selenium.py`
- `2_sparql_crud_and_frontend_test.py`
- `4_hot_reload_test.py`
- `automated_suite.py`

### 2) AI-assisted data-modeling state

Use this state when a site is being modeled or remapped.

**Purpose**
- verify export/import flows
- verify Brick tagging quality
- verify `rule_input` mappings
- confirm that data modeling decisions still support FDD and UI workflows

**Primary assets**
- `sparql/`
- demo import payloads
- Open-FDD docs and model-context endpoints

### 3) Live HVAC monitoring state

Use this state when the deployment is acting like a real operations platform.

**Purpose**
- verify telemetry is being scraped
- verify rules are executing over real timeseries
- verify expected faults are visible to developers and operators
- support operator-style summaries, maintenance triage, and platform health review

**Primary assets**
- `3_long_term_bacnet_scrape_test.py`
- `fake_bacnet_devices/`
- `rules/`
- overnight automation scripts

These are not just marketing buckets. They reflect three different reasoning contexts with different evidence requirements and different failure modes.

---

## Core scripts

| Script | Purpose |
|---|---|
| `1_e2e_frontend_selenium.py` | End-to-end frontend smoke and UI regression coverage |
| `2_sparql_crud_and_frontend_test.py` | SPARQL/API/frontend parity and CRUD validation |
| `3_long_term_bacnet_scrape_test.py` | BACnet scrape cadence, telemetry arrival, and expected fault verification |
| `4_hot_reload_test.py` | Rule upload/sync, hot reload, and FDD verification |
| `automated_suite.py` | Orchestrates the major test phases into one run |

### Full suite example

```bash
python automated_suite.py \
  --api-url http://192.168.204.16:8000 \
  --frontend-url http://192.168.204.16 \
  --bacnet-devices 3456789 3456790 \
  --long-run-check-faults
```

---

## Overnight development workflow

Recommended unattended cadence:

- **Evening / overnight:** BACnet soak and fault-window validation
- **Midnight:** full regression suite
- **Morning:** human or OpenClaw review of logs, summaries, and candidate bugs

The standard morning review should answer:

- Did BACnet discovery succeed for all expected devices?
- Did scraped telemetry land for the modeled points?
- Did the expected fault windows from the fake devices show up in Open-FDD?
- Did Selenium/UI pass?
- Did SPARQL parity pass?
- Did rule hot reload still work?
- Is any failure clearly a product bug vs environment drift or auth/setup drift?

See `docs/overnight_review.md`.

---

## Cloning this to another environment

This repo is designed to be portable.

At a minimum, another engineer or lab should be able to clone this repo and reconnect the same testing ideas to a different Open-FDD environment by providing:

- Open-FDD frontend URL
- Open-FDD API URL
- API auth if required
- BACnet gateway URL / fake-device host(s)
- site identifiers used by the deployment
- active rule directory inside Open-FDD

See `docs/cloning_and_porting.md` for the intended portability model.

---

## OpenClaw role in this repo

OpenClaw is expected to operate here as a highly capable engineering assistant that can:

- run and compare test phases
- investigate mismatches between frontend, API, BACnet, and FDD outcomes
- summarize overnight results
- verify whether a failure is likely real or merely environmental
- draft GitHub issues only when evidence is specific and reproducible

This repo is intentionally being shaped so an autonomous agent can work effectively **without turning the repository into agent-only glue code**. Human engineers should still be able to inspect the structure, understand the reasoning, and reuse the testing assets directly.

---

## Documentation roadmap

The documentation in this repo should explain not only how to run the scripts, but **why this style of testing matters** for Open-FDD development.

Current emphasis:

- how the repo maps to the three operational states
- how overnight testing should be reviewed
- how to clone or port the setup elsewhere
- how deterministic fake BACnet faults support high-confidence FDD verification

### Important next documentation targets

- exact BACnet-to-fault verification chain
- active YAML rule inventory and rolling-window expectations
- evidence formats for pass / fail / inconclusive outcomes
- docker-log correlation once container-log access is integrated

---

## License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE).
