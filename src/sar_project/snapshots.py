"""Auditable raw-response snapshots for SAR data intake."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional


SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


def write_json_snapshot(
    output_root: Path,
    provider: str,
    endpoint: str,
    params: Mapping[str, object],
    payload: object,
    captured_at: Optional[datetime] = None,
) -> Path:
    """Write one immutable raw JSON snapshot with source metadata."""

    _validate_safe_name("provider", provider)
    _validate_safe_name("endpoint", endpoint)

    captured = captured_at or datetime.now(timezone.utc)
    if captured.tzinfo is None:
        raise ValueError("captured_at must be timezone-aware")

    metadata = {
        "provider": provider,
        "endpoint": endpoint,
        "params": dict(params),
        "captured_at_utc": captured.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    record = {"metadata": metadata, "payload": payload}
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:12]
    timestamp = captured.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    directory = output_root / provider / endpoint
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{timestamp}_{digest}.json"
    if path.exists():
        raise FileExistsError(f"snapshot already exists: {path}")
    path.write_bytes(encoded)
    return path


def _validate_safe_name(field: str, value: str) -> None:
    if not SAFE_NAME.fullmatch(value):
        raise ValueError(f"{field} must contain only letters, numbers, underscores, or hyphens")
