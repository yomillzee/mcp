"""Run scheduled pulls from ad APIs and land rows in BigQuery."""

from __future__ import annotations

from datetime import date
import os
from typing import Any

import google_ads_service
import linkedin_service
import meta_service
from bq_warehouse import ensure_warehouse_schema, upsert_account_daily
from clients_config import SyncClientTarget, load_sync_clients
from dates_util import resolve_date_range


def _sync_google_ads(target: SyncClientTarget, *, start: date, end: date) -> dict[str, Any]:
    cid = target.google_ads_customer_id
    if not cid:
        return {"skipped": True, "reason": "no google_ads_customer_id"}
    rows = google_ads_service.fetch_daily_metrics(cid, start=start, end=end)
    written = upsert_account_daily(
        platform="google",
        account_id=cid,
        rows=rows,
        project_id=target.bq_project_id,
        dataset_id=target.bq_dataset_google,
    )
    return {"account_id": cid, "days_synced": written, "dataset": target.bq_dataset_google}


def _sync_meta(target: SyncClientTarget, *, start: date, end: date) -> dict[str, Any]:
    aid = target.meta_account_id
    if not aid:
        return {"skipped": True, "reason": "no meta_account_id"}
    rows = meta_service.fetch_daily_metrics(aid, start=start, end=end)
    written = upsert_account_daily(
        platform="meta",
        account_id=aid,
        rows=rows,
        project_id=target.bq_project_id,
        dataset_id=target.bq_dataset_meta,
    )
    return {"account_id": aid, "days_synced": written, "dataset": target.bq_dataset_meta}


def _sync_linkedin(target: SyncClientTarget, *, start: date, end: date) -> dict[str, Any]:
    aid = target.linkedin_account_id
    if not aid:
        return {"skipped": True, "reason": "no linkedin_account_id"}
    rows = linkedin_service.fetch_daily_metrics(aid, start=start, end=end)
    written = upsert_account_daily(
        platform="linkedin",
        account_id=aid,
        rows=rows,
        project_id=target.bq_project_id,
        dataset_id=target.bq_dataset_linkedin,
    )
    return {"account_id": aid, "days_synced": written, "dataset": target.bq_dataset_linkedin}


def sync_client(
    target: SyncClientTarget,
    *,
    date_range: str = "LAST_7_DAYS",
) -> dict[str, Any]:
    start, end, preset = resolve_date_range(date_range)
    ensure_warehouse_schema(
        project_id=target.bq_project_id,
        datasets={
            "google": target.bq_dataset_google,
            "meta": target.bq_dataset_meta,
            "linkedin": target.bq_dataset_linkedin,
        },
    )
    results: dict[str, Any] = {
        "client_key": target.client_key,
        "label": target.label,
        "bq_project_id": target.bq_project_id,
        "date_range": {"start": start.isoformat(), "end": end.isoformat(), "preset": preset},
        "platforms": {},
    }
    for name, fn in (
        ("google_ads", _sync_google_ads),
        ("meta", _sync_meta),
        ("linkedin", _sync_linkedin),
    ):
        try:
            results["platforms"][name] = fn(target, start=start, end=end)
        except Exception as exc:
            results["platforms"][name] = {"error": str(exc)[:500]}
    return results


def sync_all(*, date_range: str | None = None, client_key: str | None = None) -> dict[str, Any]:
    preset = (date_range or os.getenv("SYNC_DATE_RANGE") or "LAST_7_DAYS").strip()
    clients = load_sync_clients()
    if not clients:
        raise RuntimeError("SYNC_CLIENTS is empty — configure at least one client in Railway Variables.")

    key = (client_key or "").strip().lower()
    if key:
        if key not in clients:
            known = ", ".join(sorted(clients))
            raise RuntimeError(f"Unknown client_key '{client_key}'. Configured: {known}")
        selected = {key: clients[key]}
    else:
        selected = clients

    client_results = [sync_client(target, date_range=preset) for target in selected.values()]
    return {
        "date_range": preset,
        "client_count": len(client_results),
        "clients": client_results,
    }
