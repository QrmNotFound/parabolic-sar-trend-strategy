"""Read-only tinyshare client with snapshot support."""

from __future__ import annotations

import os
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

import pandas as pd

from sar_project.snapshots import write_json_snapshot


ALLOWED_ENDPOINTS = {
    "daily",
    "adj_factor",
    "index_weight",
    "index_daily",
    "trade_cal",
    "stk_limit",
}


def load_token(env_path: Path = Path(".env")) -> Optional[str]:
    """Load the tinyshare token from environment or a local .env file."""

    for name in ("TINYSHARE_TOKEN", "TUSHARE_TOKEN", "TUSHARE_PRO_TOKEN"):
        value = os.environ.get(name)
        if value:
            return value.strip()

    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() in {"TINYSHARE_TOKEN", "TUSHARE_TOKEN", "TUSHARE_PRO_TOKEN"}:
                return value.strip().strip("'\"")
    return None


@dataclass
class TinyshareClient:
    """Small read-only adapter around tinyshare's pro API."""

    token: str
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        import tinyshare as ts

        ts.set_token(self.token)
        self._pro = ts.pro_api()

    def call(self, endpoint: str, **params: object) -> pd.DataFrame:
        """Call one whitelisted endpoint with a timeout."""

        if endpoint not in ALLOWED_ENDPOINTS:
            raise ValueError(f"endpoint is not whitelisted: {endpoint}")
        method = getattr(self._pro, endpoint)

        def raise_timeout(_signum, _frame):
            raise TimeoutError(f"{endpoint} timed out after {self.timeout_seconds} seconds")

        previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, raise_timeout)
        signal.setitimer(signal.ITIMER_REAL, self.timeout_seconds)
        try:
            frame = method(**params)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)

        if frame is None:
            return pd.DataFrame()
        if not isinstance(frame, pd.DataFrame):
            return pd.DataFrame(frame)
        return frame


def snapshot_frame(
    snapshot_root: Path,
    endpoint: str,
    params: Mapping[str, object],
    frame: pd.DataFrame,
) -> Path:
    """Persist an auditable raw DataFrame snapshot without credentials."""

    payload = frame.where(pd.notna(frame), None).to_dict(orient="records")
    safe_params = {key: value for key, value in params.items() if "token" not in key.lower()}
    return write_json_snapshot(
        output_root=snapshot_root,
        provider="tinyshare",
        endpoint=endpoint,
        params=safe_params,
        payload=payload,
    )
