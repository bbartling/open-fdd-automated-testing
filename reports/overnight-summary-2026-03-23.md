# Overnight Summary — 2026-03-23

- **Snapshot time:** 2026-03-23 04:00 CDT
- **Window:** Open-FDD dev-testing window (18:00–06:00 CDT)
- **Branch context:** `master` for published docs review; active PR under watch: `develop/v2.0.6` → `master` (PR #81)
- **Reviewer:** OpenClaw

## 1. Executive summary

Nothing fundamentally new broke during this 04:00 CDT pass, but several previously observed issues remain real and worth carrying forward:

1. **PR #81 is still the only active PR** and is still broadly healthy, but it still carries at least one meaningful CodeRabbit correctness suggestion around bootstrap env-default handling.
2. **Published docs on `master` still have a bad LLM-workflow route reference pattern**: the trailing-slash URL 404s, while the no-trailing-slash URL works.
3. **The older GitHub README/docs reference to `pdf/canonical_llm_prompt.txt` was indeed broken on `master`**, and the active dev branch appears to be correcting that by pointing readers to the docs-site anchor instead.
4. **Live backend SPARQL parity from this bench remains blocked by missing auth/config drift** (`401 Missing or invalid Authorization header`), which prevents unattended graph verification even though the frontend path still shows real data.
5. **Live Docker/container log review could not be performed from this host** because Docker Desktop’s Linux engine pipe is unavailable right now.
6. **Overnight BACnet log evidence still shows mixed discovery behavior**: one earlier pass had device `3456790` fail `point_discovery_to_graph` with HTTP 422, while a later pass in the same log shows both devices added successfully.

## 2. Active PR review

### PR #81 — `develop/v2.0.6` → `master`
- URL: <https://github.com/bbartling/open-fdd/pull/81>
- Status at review time: open, not draft
- Last update: 2026-03-22 14:21Z
- Scope includes:
  - README/docs cleanup
  - LLM workflow docs updates
  - analytics API/frontend work
  - Docker/bootstrap/Grafana provisioning changes

### Review assessment
- **Overall state:** still looks close to mergeable
- **Known standing review item:** CodeRabbit left a substantive bootstrap comment requesting deduplication/centralization of MQTT bridge env-default insertion logic.
- **No new commits or review-state shifts** were observed during this 04:00 pass.

### Classification
- **product polish / correctness follow-up**, not a freshly observed regression

## 3. Docs and README link verification

### Checked against published `master` docs

| Link | Result | Notes |
|---|---|---|
| <https://bbartling.github.io/open-fdd/> | 200 | docs home loads |
| <https://bbartling.github.io/open-fdd/modeling/llm_workflow/> | 404 | still broken with trailing slash |
| <https://bbartling.github.io/open-fdd/modeling/llm_workflow> | 200 | route works without trailing slash |
| <https://github.com/bbartling/open-fdd/blob/master/pdf/canonical_llm_prompt.txt> | 200 | currently resolves now |
| <https://github.com/bbartling/open-fdd/blob/master/pdf/open-fdd-docs.pdf> | 200 | PDF link resolves |

### Interpretation
- The **published docs route remains fragile/inconsistent** for `llm_workflow`: users following a trailing-slash variant still hit 404.
- Compared with the 2026-03-22 evening note, the GitHub `canonical_llm_prompt.txt` link is **no longer returning 404** in this pass. That suggests either GitHub propagation/caching or a repo-side change since the earlier check.
- The active dev-branch README already appears to be steering readers away from the brittle GitHub file-link dependency and toward the docs-site anchor instead, which is a good direction.

### Additional docs/process gap
- `master` README/contributing text still says contributors should target **`develop`**, and that PRs to **`master`** will be rejected.
- The only active live PR (#81) currently targets **`master`**.
- That is a **documentation/process mismatch** that will confuse both humans and AI agents reviewing contribution guidance.

### Classification
- **documentation gap**
- **process/documentation mismatch**

## 4. Container-log / runtime evidence

### Docker access from this host
Attempted:
- `docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"`

Observed:
- Docker Desktop Linux engine pipe unavailable:
  - `open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified`

### Interpretation
- This prevented live review of expected containers:
  - `api`
  - `frontend`
  - `bacnet-scraper`
  - `fdd-loop`
  - `host-stats`
  - `bacnet-server`
- Because Docker was unreachable from this host, this pass had to rely on existing overnight artifacts rather than current container logs.

### Classification
- **testbench limitation**

## 5. Frontend vs backend/container evidence

### Frontend-side evidence from `overnight_bacnet.log`
- E2E frontend Selenium sections passed overall.
- Data Model Testing page still produced visible results in the browser.
- Points page device tree looked healthy enough to show:
  - expected columns
  - selected site `TestBenchSite`
  - site/Unassigned UI structure
- Plots page still showed a selectable fault in the legend.

### Backend/API-side evidence from the same artifact
Repeated failures in the SPARQL/API parity stage:
- `POST /data-model/sparql/upload` → **401** `Missing or invalid Authorization header`
- `GET /sites` (from parity script path) → **401** `Missing or invalid Authorization header`
- `POST /data-model/sparql` for many queries → **401** `Missing or invalid Authorization header`

### Interpretation
This is the same split seen earlier:
- **frontend/browser path appears able to render/use data**, likely via the deployed frontend’s configured auth/proxy path
- **direct backend test-bench path to :8000 remains unauthorized**

That makes this look much more like **bench auth/config drift** than a confirmed Open-FDD product regression.

### Classification
- **auth/config drift**

## 6. BACnet / graph / fault-verification status

### What the overnight artifact still shows
From `overnight_bacnet.log`:
- Earlier pass:
  - device `3456789` added to graph successfully
  - device `3456790` hit `POST /bacnet/point_discovery_to_graph` → **422 Unprocessable Entity**
- Later pass in the same log:
  - device `3456789` added successfully
  - device `3456790` also added successfully

### What we can say confidently
- BACnet discovery is not dead; it worked at least partially, and later fully, in the browser-driven flow.
- The earlier 422 for `3456790` appears **intermittent or state-dependent**, not a permanent hard failure.
- Because direct authenticated SPARQL access is blocked from this bench, this pass could **not** independently re-run the full BACnet graph verification chain.

### Rule / rolling-window context retained for morning follow-up
Relevant repo rules still include:
- `sensor_bounds.yaml`
  - out-of-range sensor checks by Brick class
- `sensor_flatline.yaml`
  - `window: 12`
  - `rolling_window: 6`

This means any fault-verification claim for flatline behavior still needs evidence across enough consecutive samples to satisfy the configured rolling-window expectation, not just a single anomalous point.

### RPC / BACnet-side independent verification
- This pass did **not** perform fresh DIY BACnet server RPC reads.
- Prior context still says the gateway OpenAPI exists, but without fresh RPC calls this snapshot is **not** a full BACnet-to-fault proof chain.

### Verdict for this pass
- **BACnet/FDD verification status:** **INCONCLUSIVE**

### Why inconclusive
Because the full evidence chain remains incomplete:
1. live direct SPARQL/API verification from this bench is blocked by auth drift
2. live container logs were unavailable due to Docker unavailability on this host
3. no fresh RPC observations were captured in this 04:00 pass

### Classification
- **auth/config drift**
- **testbench limitation**

## 7. What changed vs the prior evening report

Meaningful deltas from the earlier 2026-03-22 overnight summary:

1. **The GitHub `canonical_llm_prompt.txt` link now resolves (200) in this pass**, so that specific link should no longer be treated as currently broken without rechecking again.
2. **The docs-route problem remains**, but it is now more precisely characterized as:
   - trailing-slash URL = 404
   - no-trailing-slash URL = 200
3. **The overnight BACnet log contains both a failure and a later success for device `3456790` discovery**, which is a useful nuance missing from any one-line “device 3456790 failed” summary.

## 8. Follow-up recommendations

1. **Bench auth drift first:** load/provide the correct backend auth secret for unattended `POST /data-model/sparql` from this automated-testing bench.
2. **Docker/runtime access:** restore Docker Desktop engine access on this host so container evidence can be gathered directly instead of inferred.
3. **Docs cleanup on `master`:** normalize LLM-workflow links so published docs do not depend on brittle trailing-slash behavior.
4. **Contribution guidance cleanup:** reconcile “PR into develop” docs with the currently active reality of PR #81 targeting `master`.
5. **BACnet verification hardening:** add a report section or script step that explicitly records when a device discovery attempt first 422s and later succeeds, so intermittent discovery behavior is not flattened into a misleading single verdict.

## 9. Issue classification roll-up

- **Auth/config drift**
  - direct backend SPARQL/API access from the test bench still returns 401
- **Documentation gaps**
  - published `llm_workflow` route still breaks with trailing slash
  - contribution guidance does not match the active PR target reality
- **Testbench limitations**
  - Docker unavailable from this host, so no live container log review
  - no fresh RPC evidence captured in this snapshot
- **Possible product bug / product rough edge**
  - intermittent `3456790` discovery 422 seen earlier in the same overnight log, though later success makes this non-conclusive

## 10. Morning handoff

If the morning pass only has time for three checks, do these in order:
1. restore/directly provide backend auth so SPARQL queries can run non-interactively
2. restore Docker access and inspect live logs for `api`, `frontend`, `bacnet-scraper`, `fdd-loop`, `host-stats`, `bacnet-server`
3. re-run BACnet graph verification plus one independent DIY BACnet RPC read to close the evidence loop
