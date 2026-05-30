"""Client + account registry for scheduled BigQuery sync."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SyncClientTarget:
    client_key: str
    label: str
    bq_project_id: str
    bq_dataset_google: str
    bq_dataset_meta: str
    bq_dataset_linkedin: str
    google_ads_customer_id: str | None = None
    linkedin_account_id: str | None = None
    meta_account_id: str | None = None


def _strip_env(val: str | None) -> str:
    if not val:
        return ""
    v = val.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
        return v[1:-1].strip()
    return v


def _default_project() -> str:
    return _strip_env(os.getenv("BQ_WAREHOUSE_PROJECT")) or _strip_env(os.getenv("BQ_PROJECT_ID"))


def load_sync_clients() -> dict[str, SyncClientTarget]:
    raw = _strip_env(os.getenv("SYNC_CLIENTS"))
    if not raw:
        return {}

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("SYNC_CLIENTS must be a JSON object keyed by client slug.")

    project_default = _default_project()
    ds_google = _strip_env(os.getenv("BQ_DATASET_GOOGLE")) or "warehouse_google_ads"
    ds_meta = _strip_env(os.getenv("BQ_DATASET_META")) or "warehouse_meta"
    ds_linkedin = _strip_env(os.getenv("BQ_DATASET_LINKEDIN")) or "warehouse_linkedin"

    out: dict[str, SyncClientTarget] = {}
    for key, entry in data.items():
        if not isinstance(entry, dict):
            continue
        slug = str(key).strip().lower()
        project = _strip_env(str(entry.get("bq_project_id") or entry.get("project") or "")) or project_default
        if not project:
            continue
        out[slug] = SyncClientTarget(
            client_key=slug,
            label=_strip_env(str(entry.get("label") or "")) or slug,
            bq_project_id=project,
            bq_dataset_google=_strip_env(str(entry.get("bq_dataset_google") or "")) or ds_google,
            bq_dataset_meta=_strip_env(str(entry.get("bq_dataset_meta") or "")) or ds_meta,
            bq_dataset_linkedin=_strip_env(str(entry.get("bq_dataset_linkedin") or "")) or ds_linkedin,
            google_ads_customer_id=_strip_env(str(entry.get("google_ads_customer_id") or "")) or None,
            linkedin_account_id=_strip_env(str(entry.get("linkedin_account_id") or "")) or None,
            meta_account_id=_strip_env(str(entry.get("meta_account_id") or "")) or None,
        )
    return out


def list_sync_clients_public() -> list[dict[str, Any]]:
    return [
        {
            "client_key": t.client_key,
            "label": t.label,
            "bq_project_id": t.bq_project_id,
            "bq_dataset_google": t.bq_dataset_google,
            "bq_dataset_meta": t.bq_dataset_meta,
            "bq_dataset_linkedin": t.bq_dataset_linkedin,
            "google_ads_customer_id": t.google_ads_customer_id,
            "linkedin_account_id": t.linkedin_account_id,
            "meta_account_id": t.meta_account_id,
        }
        for t in load_sync_clients().values()
    ]
