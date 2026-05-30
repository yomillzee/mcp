# EOS Marketing Data MCP (BigQuery warehouse)

Fork of `railway/app` (sagefrog) for **scheduled sync → BigQuery**. The original ChatGPT/live-API service is unchanged in the sagefrog repo.

## What this service does

1. **Cron** (Railway) calls `POST /internal/sync-all` daily.
2. Pulls account-level daily metrics from **Google Ads**, **Meta**, and **LinkedIn**.
3. **MERGE** rows into BigQuery warehouse datasets.
4. **GA4** stays in the native export (`analytics_313855909`) — query it with `POST /ga4/query` as before.

Legacy platform API routes are still included for debugging; production dashboards should query BigQuery only.

## Railway settings

| Setting | Value |
|--------|--------|
| **Root directory** | *(repo root — this folder is the service)* |
| **Start command** | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| **Health check** | `/health` |

Connect GitHub repo: [yomillzee/mcp](https://github.com/yomillzee/mcp)

## Environment variables

Copy from `.env.example`. Minimum for BigQuery sync:

| Variable | Purpose |
|----------|---------|
| `GCP_SERVICE_ACCOUNT_JSON` | Service account with **BigQuery Data Editor** on warehouse datasets |
| `BQ_WAREHOUSE_PROJECT` | GCP project (e.g. `penn-community-b-1699391543298`) |
| `BQ_DATASET_GOOGLE` | `warehouse_google_ads` |
| `BQ_DATASET_META` | `warehouse_meta` |
| `BQ_DATASET_LINKEDIN` | `warehouse_linkedin` |
| `CRON_SECRET` | Random secret; Railway cron sends `X-Cron-Secret` header |
| `SYNC_CLIENTS` | JSON registry of clients + account IDs (see below) |
| `SYNC_DATE_RANGE` | Default `LAST_7_DAYS` for cron overlap |

Also copy **platform tokens** from sagefrog (Google Ads, LinkedIn, Meta) — sync still calls those APIs.

`DATABASE_URL` is **optional** on this service (Postgres cache/legacy warehouse). BigQuery is the primary store.

### SYNC_CLIENTS example (Penn)

One-line JSON in Railway:

```json
{"penn":{"label":"Penn Community Bank","bq_project_id":"penn-community-b-1699391543298","bq_dataset_google":"warehouse_google_ads","bq_dataset_meta":"warehouse_meta","bq_dataset_linkedin":"warehouse_linkedin","google_ads_customer_id":"YOUR_GOOGLE_CUSTOMER_ID","linkedin_account_id":"507720820","meta_account_id":"506176584"}}
```

Replace account IDs with Penn's values from the sagefrog GPT / platform UIs.

## BigQuery setup

1. Open [BigQuery Console](https://console.cloud.google.com/bigquery) for project `penn-community-b-1699391543298`.
2. Run `scripts/create_bq_warehouse.sql` **or** call `POST /internal/bq/ensure-schema` once after deploy (creates datasets/tables automatically).
3. IAM → grant your Railway service account:
   - **BigQuery Data Editor** on `warehouse_google_ads`, `warehouse_meta`, `warehouse_linkedin`
   - **BigQuery Data Viewer** on `analytics_313855909` (GA4 read-only)
4. Leave `analytics_313855909` as the GA4 native export — do not write paid media into it.

### Query examples (Penn)

```sql
-- Google Ads account daily
SELECT * FROM `penn-community-b-1699391543298.warehouse_google_ads.metrics_account_daily`
WHERE metric_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
ORDER BY metric_date;

-- Meta account daily
SELECT * FROM `penn-community-b-1699391543298.warehouse_meta.metrics_account_daily`
WHERE account_id = '506176584'
ORDER BY metric_date DESC;

-- GA4 (native export)
SELECT event_date, COUNTIF(event_name = 'session_start') AS sessions
FROM `penn-community-b-1699391543298.analytics_313855909.events_*`
WHERE _TABLE_SUFFIX BETWEEN FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY))
  AND FORMAT_DATE('%Y%m%d', CURRENT_DATE())
GROUP BY 1 ORDER BY 1;
```

## Railway cron

1. Deploy the service and set `CRON_SECRET`.
2. **Settings → Cron** (or use [Railway cron](https://docs.railway.app/guides/cron-jobs)):
   - Schedule: `0 11 * * *` (6am ET ≈ 11:00 UTC, adjust as needed)
   - Command / HTTP: trigger a deploy hook or use Railway's HTTP cron if available.

**Manual test after deploy:**

```bash
curl -X POST "https://YOUR-MCP-SERVICE.up.railway.app/internal/sync-all" \
  -H "X-Cron-Secret: YOUR_CRON_SECRET"
```

Optional query params: `?date_range=LAST_7_DAYS&client_key=penn`

## API routes (v2)

| Route | Auth | Purpose |
|-------|------|---------|
| `GET /health` | none | Load balancer |
| `POST /internal/sync-all` | `X-Cron-Secret` | Daily sync job |
| `POST /internal/bq/ensure-schema` | `X-Cron-Secret` | Create BQ datasets/tables |
| `GET /warehouse/bq/status` | API_KEY | Row counts / date coverage |
| `GET /sync/clients` | API_KEY | List SYNC_CLIENTS registry |
| `POST /ga4/query` | API_KEY | SQL on GA4 export + warehouse |

## Next phases (not built yet)

- Campaign / ad set / creative daily tables in BigQuery
- Video thumbnail snapshot tables
- BQ-only Custom GPT schema (no live platform actions)

## Local dev

```bash
cd mcp
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```
