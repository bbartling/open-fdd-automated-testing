---
title: Data modeling
nav_order: 7
has_children: true
---

# Data modeling

The Open-FDD data model is built around **sites**, **equipment**, and **points**: the same entities you create, read, update, and delete via the API (**CRUD** = Create, Read, Update, Delete). The REST API (Swagger at `/docs`) and the data-model endpoints (`/data-model/export`, `/data-model/import`, `/data-model/ttl`) are the main way to manage this data. The database is the single source of truth; the Brick TTL file is regenerated on every change so FDD rules and Grafana stay in sync.

**Concepts (entities):**

- **[Sites](sites)** — Buildings or facilities. All equipment and points are scoped to a site.
- **[Equipment](equipment)** — Physical devices (AHUs, VAVs, heat pumps). Belong to a site; have points.
- **[Points](points)** — Time-series references (sensors, setpoints). Link to equipment and site; store `external_id`, optional `brick_type` and `rule_input` for FDD.
- **[External representations (Brick v1.4)](external_representations)** — `ref:hasExternalReference` mappings from points to BACnet and timeseries systems.
- **Engineering metadata + 223P topology** — equipment-level engineering metadata is stored as JSON and emitted to RDF using `ofdd:*` extension predicates plus `s223:*` topology patterns (`hasConnectionPoint`, connection conduits, mediums). Same graph as Brick and timeseries refs, so you can join **rated capacity** and **topology** to **FDD results** for optimization context or rough energy-penalty sketches ([Data model engineering](../howto/data_model_engineering)).
- **[SPARQL cookbook](sparql_cookbook)** — Run SPARQL via POST /data-model/sparql only: config, data model, BACnet, FDD rule mapping, time-series references. Copy-paste queries for validation and UIs.
- **[AI-assisted data modeling](ai_assisted_tagging)** — Export → LLM or human tagging → import (Brick types, rule_input, polling, equipment feeds). External agents (e.g. Open‑Claw) can use `GET /model-context/docs` as platform documentation context and `GET /mcp/manifest` for HTTP discovery; the canonical import schema is the same.
- **[LLM workflow (export + rules + validate → import)](llm_workflow)** — Canonical prompt (fault-first pre-flight for polling), export JSON, faults + rules (prefer YAML); validate with schema or Pydantic; then PUT /data-model/import and run FDD/tests. [Published hub](https://bbartling.github.io/open-fdd-afdd-stack/modeling/).
- **[AI-assisted energy calculations](ai_assisted_energy_calculations)** — After the Brick model exists: `GET /energy-calculations/export` → LLM fills predefined `calc_type` / `parameters` → `PUT /energy-calculations/import`. Export embeds full `calc_types` metadata for offline agents.
- **[Default FDD energy penalty catalog](energy_penalty_equations)** — 18 seeded engineering narratives (GL36-style airside, plant, zone), `POST /energy-calculations/seed-default-penalty-catalog`, TTL `ofdd:penaltyCatalogSeq`.

**Framework:** CRUD is provided by the FastAPI REST API. The data-model API adds bulk export/import and Brick TTL generation; see [Overview](overview) for the flow (DB → TTL → FDD column_map) and [Appendix: API Reference](../appendix/api_reference) for endpoints.
