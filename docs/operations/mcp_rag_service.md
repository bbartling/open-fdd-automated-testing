---
title: MCP RAG service
parent: Operations
nav_order: 5
---

# MCP RAG service

Open-FDD can run an optional MCP-style retrieval service derived from canonical docs.

## Canonical vs derived context

- Canonical human docs: `docs/` and generated `pdf/open-fdd-docs.txt`.
- Derived AI index: `stack/mcp-rag/index/rag_index.json`.
- **Upstream markdown (bootstrap `--with-mcp-rag` only):** shallow sparse `git` clones under `stack/mcp-rag/.vendor-docs/<repo>/docs` from [open-fdd/docs](https://github.com/bbartling/open-fdd/tree/master/docs), [diy-bacnet-server/docs](https://github.com/bbartling/diy-bacnet-server/tree/master/docs), and [easy-aso/docs](https://github.com/bbartling/easy-aso/tree/master/docs). Those trees are indexed with tags like `upstream:open-fdd` and stable `source` paths such as `open-fdd/docs/rules/overview.md` (not the full repositories).

Never edit index artifacts as source-of-truth documentation.

## Bootstrap

Run:

```bash
./scripts/bootstrap.sh --with-mcp-rag
```

This flow clones upstream `docs/` folders when `git` is available, builds docs text when needed, builds the retrieval index (stack + upstream markdown), and starts the MCP RAG service profile. Offline or clone failures still produce an index from this repository’s `docs/` only.

For module-focused operations, combine with bootstrap mode:

```bash
./scripts/bootstrap.sh --mode model --with-mcp-rag
```

## Service endpoints

- `GET /health`
- `GET /manifest`
- `POST /tools/search_docs`
- `POST /tools/get_doc_section`
- `POST /tools/search_api_capabilities`
- `POST /tools/get_operator_playbook`

Optional guarded action tools are present but disabled by default via `OFDD_MCP_ENABLE_ACTION_TOOLS=false`.

