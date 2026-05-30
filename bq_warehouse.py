"""BigQuery warehouse writes for scheduled ad-platform sync (v2)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from bigquery_service import build_client

METRICS_ACCOUNT_DAILY_SCHEMA = [
    bigquery.SchemaField("account_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("metric_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("spend", "FLOAT64"),
    bigquery.SchemaField("clicks", "INT64"),
    bigquery.SchemaField("impressions", "INT64"),
    bigquery.SchemaField("conversions", "FLOAT64"),
    bigquery.SchemaField("conversion_value", "FLOAT64"),
    bigquery.SchemaField("synced_at", "TIMESTAMP"),
]

METRICS_CAMPAIGN_DAILY_SCHEMA = [
    bigquery.SchemaField("account_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("campaign_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("campaign_name", "STRING"),
    bigquery.SchemaField("metric_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("spend", "FLOAT64"),
    bigquery.SchemaField("clicks", "INT64"),
    bigquery.SchemaField("impressions", "INT64"),
    bigquery.SchemaField("conversions", "FLOAT64"),
    bigquery.SchemaField("conversion_value", "FLOAT64"),
    bigquery.SchemaField("synced_at", "TIMESTAMP"),
]


def warehouse_project_id() -> str:
    pid = (os.getenv("BQ_WAREHOUSE_PROJECT") or os.getenv("BQ_PROJECT_ID") or "").strip()
    if not pid:
        raise RuntimeError("Set BQ_WAREHOUSE_PROJECT or BQ_PROJECT_ID for BigQuery warehouse writes.")
    return pid


def enabled() -> bool:
    return bool((os.getenv("GCP_SERVICE_ACCOUNT_JSON") or "").strip())


def ensure_dataset(client: bigquery.Client, project_id: str, dataset_id: str) -> None:
    ref = f"{project_id}.{dataset_id}"
    try:
        client.get_dataset(ref)
    except NotFound:
        ds = bigquery.Dataset(ref)
        ds.location = (os.getenv("BQ_WAREHOUSE_LOCATION") or "US").strip()
        client.create_dataset(ds, exists_ok=True)


def ensure_table(
    client: bigquery.Client,
    project_id: str,
    dataset_id: str,
    table_id: str,
    schema: list[bigquery.SchemaField],
    *,
    partition_field: str = "metric_date",
) -> bigquery.Table:
    table_ref = f"{project_id}.{dataset_id}.{table_id}"
    try:
        return client.get_table(table_ref)
    except NotFound:
        table = bigquery.Table(table_ref, schema=schema)
        table.time_partitioning = bigquery.TimePartitioning(field=partition_field)
        table.clustering_fields = ["account_id"]
        return client.create_table(table)


def ensure_warehouse_schema(
    *,
    project_id: str | None = None,
    datasets: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create datasets + core tables if missing."""
    pid = project_id or warehouse_project_id()
    ds_map = datasets or default_dataset_map()
    client = build_client(pid)
    created: list[str] = []
    for platform, dataset_id in ds_map.items():
        if not dataset_id:
            continue
        ensure_dataset(client, pid, dataset_id)
        ensure_table(client, pid, dataset_id, "metrics_account_daily", METRICS_ACCOUNT_DAILY_SCHEMA)
        ensure_table(client, pid, dataset_id, "metrics_campaign_daily", METRICS_CAMPAIGN_DAILY_SCHEMA)
        created.append(f"{pid}.{dataset_id}")
    return {"project_id": pid, "datasets": created}


def default_dataset_map() -> dict[str, str]:
    raw = (os.getenv("BQ_WAREHOUSE_DATASETS") or "").strip()
    if raw:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    return {
        "google": (os.getenv("BQ_DATASET_GOOGLE") or "warehouse_google_ads").strip(),
        "meta": (os.getenv("BQ_DATASET_META") or "warehouse_meta").strip(),
        "linkedin": (os.getenv("BQ_DATASET_LINKEDIN") or "warehouse_linkedin").strip(),
    }


def _normalize_rows(rows: list[dict[str, Any]], *, account_id: str) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    out: list[dict[str, Any]] = []
    acct = str(account_id).strip().split(":")[-1]
    for row in rows:
        metric_date = row.get("metric_date") or row.get("metricDate")
        if not metric_date:
            continue
        out.append(
            {
                "account_id": acct,
                "metric_date": str(metric_date)[:10],
                "spend": float(row.get("spend") or 0),
                "clicks": int(row.get("clicks") or 0),
                "impressions": int(row.get("impressions") or 0),
                "conversions": float(row.get("conversions") or 0),
                "conversion_value": float(row.get("conversion_value") or row.get("conversionValue") or 0),
                "synced_at": now,
            }
        )
    return out


def upsert_account_daily(
    *,
    platform: str,
    account_id: str,
    rows: list[dict[str, Any]],
    project_id: str | None = None,
    dataset_id: str | None = None,
) -> int:
    """Merge daily account metrics into BigQuery metrics_account_daily."""
    if not rows:
        return 0
    pid = project_id or warehouse_project_id()
    ds_map = default_dataset_map()
    ds = dataset_id or ds_map.get(platform) or ds_map.get(platform.lower())
    if not ds:
        raise ValueError(f"No BigQuery dataset configured for platform '{platform}'.")

    normalized = _normalize_rows(rows, account_id=account_id)
    if not normalized:
        return 0

    client = build_client(pid)
    ensure_table(client, pid, ds, "metrics_account_daily", METRICS_ACCOUNT_DAILY_SCHEMA)

    table_ref = f"`{pid}.{ds}.metrics_account_daily`"
    merge_sql = f"""
        MERGE {table_ref} AS T
        USING UNNEST(@rows) AS S
        ON T.account_id = S.account_id AND T.metric_date = S.metric_date
        WHEN MATCHED THEN UPDATE SET
          spend = S.spend,
          clicks = S.clicks,
          impressions = S.impressions,
          conversions = S.conversions,
          conversion_value = S.conversion_value,
          synced_at = S.synced_at
        WHEN NOT MATCHED THEN INSERT (
          account_id, metric_date, spend, clicks, impressions, conversions, conversion_value, synced_at
        ) VALUES (
          S.account_id, S.metric_date, S.spend, S.clicks, S.impressions, S.conversions, S.conversion_value, S.synced_at
        )
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter(
                "rows",
                "STRUCT<account_id STRING, metric_date DATE, spend FLOAT64, clicks INT64, "
                "impressions INT64, conversions FLOAT64, conversion_value FLOAT64, synced_at TIMESTAMP>",
                [
                    {
                        "account_id": r["account_id"],
                        "metric_date": r["metric_date"],
                        "spend": r["spend"],
                        "clicks": r["clicks"],
                        "impressions": r["impressions"],
                        "conversions": r["conversions"],
                        "conversion_value": r["conversion_value"],
                        "synced_at": r["synced_at"],
                    }
                    for r in normalized
                ],
            )
        ]
    )
    client.query(merge_sql, job_config=job_config).result()
    return len(normalized)


def warehouse_status() -> dict[str, Any]:
    if not enabled():
        return {
            "enabled": False,
            "project_id": None,
            "datasets": {},
            "error": "GCP_SERVICE_ACCOUNT_JSON is missing.",
        }
    try:
        pid = warehouse_project_id()
        client = build_client(pid)
        ds_map = default_dataset_map()
        counts: dict[str, Any] = {}
        for platform, ds in ds_map.items():
            if not ds:
                continue
            try:
                sql = f"""
                    SELECT COUNT(*) AS row_count,
                           MIN(metric_date) AS min_date,
                           MAX(metric_date) AS max_date
                    FROM `{pid}.{ds}.metrics_account_daily`
                """
                row = next(iter(client.query(sql).result()), None)
                counts[platform] = {
                    "dataset": ds,
                    "row_count": int(row.row_count) if row else 0,
                    "min_date": str(row.min_date) if row and row.min_date else None,
                    "max_date": str(row.max_date) if row and row.max_date else None,
                }
            except NotFound:
                counts[platform] = {"dataset": ds, "row_count": 0, "min_date": None, "max_date": None}
        return {"enabled": True, "project_id": pid, "datasets": counts, "error": None}
    except Exception as exc:
        return {"enabled": True, "project_id": None, "datasets": {}, "error": str(exc)[:500]}
