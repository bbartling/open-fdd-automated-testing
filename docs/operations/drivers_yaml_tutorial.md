# Driver Profile Tutorial (`config/drivers.yaml`)

Use `config/drivers.yaml` to declare which runtime services bootstrap should start.

`scripts/bootstrap.sh` reads this file and only starts the matching driver services for each mode.

## Default baseline (manual CSV-first)

Current defaults prioritize UI/API workflows first, with collectors opt-in:

```yaml
drivers:
  bacnet: false
  fdd: true
  weather: false
  onboard: false
  csv: false
  host_stats: true
```

This means:
- CSV upload via frontend/API works (manual, one-shot ingest).
- `csv-scraper` is not started unless `csv: true`.
- BACnet/Onboard/Weather collectors are disabled unless explicitly enabled.

## 1) Local BACnet Setup

Use when you want local BACnet gateway + scrape + standard FDD/weather loop.

```yaml
drivers:
  bacnet: true
  fdd: true
  weather: true
  onboard: false
  csv: false
  host_stats: true
```

Recommended `.env` values:

```env
OFDD_BACNET_ADDRESS=192.168.204.18/24:47808
OFDD_BACNET_DEVICE_INSTANCE=123456
OFDD_BACNET_SERVER_URL=http://caddy:8081
```

Start and verify:

```bash
./scripts/bootstrap.sh --mode full --verify
curl -s -X POST http://localhost:8080/server_hello \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"server_hello","params":{}}' | jq .
```

For a clean profile reconciliation, run stack bootstrap first, then tests:

```bash
./scripts/bootstrap.sh --mode full --force-rebuild --verify
./scripts/bootstrap.sh --test
```

## 2) CSV Ingest Setup

Use when you want file-based ingest + FDD backfill windows.

```yaml
drivers:
  bacnet: false
  fdd: true
  weather: false
  onboard: false
  csv: true
  host_stats: true
```

Recommended `.env` values:

```env
OFDD_CSV_ENABLED=true
OFDD_CSV_SOURCES=[{"path":"examples/csv/AHU7.csv","site_id":"csv-ahu7"}]
OFDD_CSV_SCRAPE_INTERVAL_MIN=180
OFDD_CSV_BACKFILL_START=2026-04-01T00:00:00Z
OFDD_CSV_CREATE_POINTS=true

OFDD_FDD_BACKFILL_ENABLED=true
OFDD_FDD_BACKFILL_START=2026-04-01T00:00:00Z
OFDD_FDD_BACKFILL_END=
OFDD_FDD_BACKFILL_STEP_HOURS=3
```

Start and test upload API (dry run):

```bash
./scripts/bootstrap.sh --mode full --verify
curl -s -X POST http://127.0.0.1:8000/csv/upload \
  -F "file=@examples/csv/AHU7.csv" \
  -F "site_id=csv-ahu7" \
  -F "create_points=true" \
  -F "dry_run=true" | jq .
```

## 3) Onboard Ingest Setup

Use when you want Onboard API ingest + AFDD.

```yaml
drivers:
  bacnet: false
  fdd: true
  weather: false
  onboard: true
  csv: false
  host_stats: true
```

Recommended `.env` values:

```env
OFDD_ONBOARD_ENABLED=true
OFDD_ONBOARD_API_BASE_URL=https://api.onboarddata.io
OFDD_ONBOARD_API_KEY=your_onboard_key
OFDD_ONBOARD_BUILDING_IDS=Office Building
OFDD_ONBOARD_SCRAPE_INTERVAL_MIN=180
OFDD_ONBOARD_BACKFILL_START=2026-04-01T00:00:00Z
OFDD_ONBOARD_SITE_ID_STRATEGY=onboard-building-id
OFDD_ONBOARD_CREATE_POINTS=true
```

Start and test metadata fetch:

```bash
./scripts/bootstrap.sh --mode full --verify
python scripts/onboard_list_metadata.py --building "Office Building"
```

## Useful checks

Driver profile status endpoint:

```bash
curl -s http://127.0.0.1:8000/config/driver-profile | jq .
```

This route is also consumed by the frontend to show whether drivers are bootstrapped.
