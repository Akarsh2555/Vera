from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .store import ContextStore


UTC = timezone.utc


def bootstrap_demo_data(store: ContextStore, project_root: Path) -> dict[str, int]:
    dataset_dir = project_root / "dataset"
    categories_dir = dataset_dir / "categories"
    delivered_at = datetime.now(UTC)

    store.clear()

    version_counter = 1
    for category_file in sorted(categories_dir.glob("*.json")):
        payload = json.loads(category_file.read_text(encoding="utf-8"))
        store.upsert_context(
            "category",
            payload["slug"],
            version_counter,
            payload,
            delivered_at,
        )

    seed_files = {
        "merchant": dataset_dir / "merchants_seed.json",
        "customer": dataset_dir / "customers_seed.json",
        "trigger": dataset_dir / "triggers_seed.json",
    }
    collection_keys = {"merchant": "merchants", "customer": "customers", "trigger": "triggers"}
    identity_keys = {"merchant": "merchant_id", "customer": "customer_id", "trigger": "id"}

    for scope, file_path in seed_files.items():
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        for item in payload[collection_keys[scope]]:
            store.upsert_context(
                scope,
                item[identity_keys[scope]],
                version_counter,
                item,
                delivered_at,
            )

    return store.counts()
