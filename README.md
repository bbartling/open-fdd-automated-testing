# Open-FDD Automated Testing

> Getting started note: [OpenClaw setup with ChatGPT subscription / Codex OAuth (not API key)](docs/howto/openclaw_subscription_setup.md)

![Open-FDD automated testing dashboard](docs/images/dashboard_snip.png)

## Purpose

This repo is the reusable testing, verification, and model-context pack for Open-FDD development and future HVAC deployments.

It is meant to help both humans and AI agents:
- run frontend/API/BACnet/FDD checks
- review overnight evidence
- preserve durable engineering context
- carry lessons forward across future jobs and future buildings

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
- BACnet graph/addressing validation through SPARQL and API checks
- YAML rule hot-reload checks
- proof that faults are computed and surfaced by Open-FDD as expected
- future-facing context for optimization and supervisory logic based on equipment semantics

## Main scripts
- `1_e2e_frontend_selenium.py`
- `2_sparql_crud_and_frontend_test.py`
- `3_long_term_bacnet_scrape_test.py`
- `4_hot_reload_test.py`
- `automated_suite.py`

## Documentation

The docs are now organized in a structure closer to the main Open-FDD docs so they can be built into a cleaner PDF context pack.

### Docs home
- [`docs/index.md`](docs/index.md)

### Sections
- [Concepts](docs/concepts/index.md)
- [BACnet verification](docs/bacnet/index.md)
- [Operations](docs/operations/index.md)
- [How-to guides](docs/howto/index.md)
- [Appendix](docs/appendix/index.md)

### Key pages
- [`docs/concepts/operational_states.md`](docs/concepts/operational_states.md)
- [`docs/concepts/context_and_recordkeeping.md`](docs/concepts/context_and_recordkeeping.md)
- [`docs/bacnet/graph_context.md`](docs/bacnet/graph_context.md)
- [`docs/bacnet/fault_verification.md`](docs/bacnet/fault_verification.md)
- [`docs/operations/overnight_review.md`](docs/operations/overnight_review.md)
- [`docs/operations/testing_plan.md`](docs/operations/testing_plan.md)
- [`docs/operations/openfdd_integrity_sweep.md`](docs/operations/openfdd_integrity_sweep.md)
- [`docs/appendix/ai_pr_review_playbook.md`](docs/appendix/ai_pr_review_playbook.md)

## PDF build

This repo now has its own docs PDF builder:

- `scripts/build_docs_pdf.py`

Expected output:
- `pdf/open-fdd-automated-testing-docs.pdf`
- `pdf/open-fdd-automated-testing-docs.txt`

Example:

```bash
python scripts/build_docs_pdf.py
```

Requirements:
- `pandoc`
- `PyYAML`
- for PDF output, a supported Pandoc engine such as `weasyprint`, `pdflatex`, or `xelatex`

## Engineering principle

This repo should stay:
- portable across labs and OT LANs
- professional enough for human engineers to trust
- structured enough for agents to reuse without depending on chat memory
- explicit about the difference between product bugs, auth/config drift, testbench limitations, and BACnet/model drift

## License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE).
