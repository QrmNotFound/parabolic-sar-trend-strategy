"""Audit artifact generation for SAR project reports."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Mapping, Optional

import pandas as pd

from sar_project.dataset import ProjectPaths, build_inputs_for_params, load_dataset
from sar_project.optimizer import SarParams


AUDIT_FILES = (
    "market_data_used.csv.gz",
    "trade_ledger_sample_out.csv",
    "round_trip_trades_sample_out.csv",
    "portfolio_sample_out.csv",
    "source_data_inventory.csv",
    "raw_snapshot_manifest.csv",
    "optimization_results_sample_in.csv",
    "best_params.json",
    "audit_manifest.csv",
)


def generate_audit_artifacts(paths: ProjectPaths, start_date: str, end_date: str) -> None:
    """Write lightweight, commit-friendly audit files under docs/sar_project/audit."""

    audit_root = paths.docs_root / "audit"
    audit_root.mkdir(parents=True, exist_ok=True)
    best_params = json.loads((paths.processed_root / "best_params.json").read_text(encoding="utf-8"))
    params = SarParams(**best_params)
    dataset = load_dataset(paths)
    inputs = build_inputs_for_params(dataset, params, start_date, end_date)

    _write_market_data(inputs.prices, audit_root / "market_data_used.csv.gz", start_date, end_date)
    ledger = _write_trade_ledger(paths, inputs, params, audit_root / "trade_ledger_sample_out.csv")
    _write_round_trips(ledger, audit_root / "round_trip_trades_sample_out.csv")
    _copy_result(paths.processed_root / "portfolio_test.csv", audit_root / "portfolio_sample_out.csv")
    _copy_result(paths.processed_root / "optimization_results.csv", audit_root / "optimization_results_sample_in.csv")
    _copy_result(paths.processed_root / "best_params.json", audit_root / "best_params.json")
    _write_source_inventory(paths, audit_root / "source_data_inventory.csv")
    _write_raw_snapshot_manifest(paths.raw_root / "tinyshare", audit_root / "raw_snapshot_manifest.csv")
    _write_audit_manifest(audit_root)


def _write_market_data(
    prices: Mapping[str, pd.DataFrame],
    path: Path,
    start_date: str,
    end_date: str,
) -> None:
    columns = [
        "symbol",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "vol",
        "amount",
        "adj_factor",
        "up_limit",
        "down_limit",
        "open_adj",
        "high_adj",
        "low_adj",
        "close_adj",
        "up_limit_adj",
        "down_limit_adj",
        "sar",
        "rsi",
        "volume_ratio",
        "signal_strength",
    ]
    frames = []
    for symbol, frame in sorted(prices.items()):
        if "trade_date" not in frame:
            continue
        sample = frame[(frame["trade_date"].astype(str) >= start_date) & (frame["trade_date"].astype(str) <= end_date)].copy()
        if sample.empty:
            continue
        sample.insert(0, "symbol", symbol)
        for column in columns:
            if column not in sample:
                sample[column] = pd.NA
        frames.append(sample[columns])
    market_data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
    market_data.to_csv(path, index=False, compression="gzip")


def _write_trade_ledger(paths: ProjectPaths, inputs, params: SarParams, path: Path) -> pd.DataFrame:
    trades = pd.read_csv(
        paths.processed_root / "trades_test.csv",
        dtype={"signal_date": str, "trade_date": str, "symbol": str},
    )
    signal_fields = ["close_adj", "sar", "rsi", "volume_ratio", "signal_strength"]
    execution_fields = ["open", "open_adj", "up_limit", "down_limit", "up_limit_adj", "down_limit_adj"]
    lookups = {
        symbol: frame.set_index(frame["trade_date"].astype(str)).to_dict(orient="index")
        for symbol, frame in inputs.prices.items()
        if "trade_date" in frame
    }
    open_positions: Dict[str, list[dict[str, object]]] = {}
    rows = []
    for raw in trades.to_dict(orient="records"):
        row = dict(raw)
        symbol = str(row.get("symbol", ""))
        signal_date = str(row.get("signal_date", ""))
        trade_date = str(row.get("trade_date", ""))
        signal_row = lookups.get(symbol, {}).get(signal_date, {})
        execution_row = lookups.get(symbol, {}).get(trade_date, {})
        for field in signal_fields:
            row[f"signal_{field}"] = signal_row.get(field, pd.NA)
        for field in execution_fields:
            row[f"execution_{field}"] = execution_row.get(field, pd.NA)
        row["signal_in_universe"] = symbol in set(inputs.universe_by_date.get(signal_date, ()))
        row["matched_entry_trade_date"] = pd.NA
        row["matched_entry_price"] = pd.NA

        action = str(row.get("action", ""))
        if action == "buy":
            row["inferred_reason"] = "signal_buy"
            open_positions.setdefault(symbol, []).append(
                {
                    "trade_date": trade_date,
                    "price": row.get("price"),
                    "shares": row.get("shares"),
                    "entry_value": row.get("entry_value"),
                }
            )
        elif action == "sell":
            entry = open_positions.get(symbol, [{}]).pop(0)
            row["matched_entry_trade_date"] = entry.get("trade_date", pd.NA)
            row["matched_entry_price"] = entry.get("price", pd.NA)
            row["inferred_reason"] = _infer_sell_reason(row, params)
        elif action == "blocked_sell":
            entry = open_positions.get(symbol, [{}])[0] if open_positions.get(symbol) else {}
            row["matched_entry_trade_date"] = entry.get("trade_date", pd.NA)
            row["matched_entry_price"] = entry.get("price", pd.NA)
            row["inferred_reason"] = row.get("reason", "blocked_sell")
        else:
            row["inferred_reason"] = row.get("reason", action)
        rows.append(row)

    ledger = pd.DataFrame(rows)
    ledger.to_csv(path, index=False)
    return ledger


def _infer_sell_reason(row: Mapping[str, object], params: SarParams) -> str:
    if row.get("signal_in_universe") is False:
        return "left_universe"
    close = _to_float(row.get("signal_close_adj"))
    sar = _to_float(row.get("signal_sar"))
    rsi = _to_float(row.get("signal_rsi"))
    entry_price = _to_float(row.get("matched_entry_price"))
    if close is not None and sar is not None and close < sar:
        return "sar_break"
    if rsi is not None and rsi > params.rsi_ceiling:
        return "rsi_ceiling"
    if close is not None and entry_price is not None and close < entry_price * (1 - params.stop_loss):
        return "stop_loss"
    if close is not None and entry_price is not None and close > entry_price * (1 + params.take_profit):
        return "take_profit"
    return "signal_or_risk"


def _write_round_trips(ledger: pd.DataFrame, path: Path) -> None:
    sells = ledger[ledger.get("action", pd.Series(dtype=str)) == "sell"].copy()
    columns = [
        "symbol",
        "entry_trade_date",
        "exit_trade_date",
        "entry_price",
        "exit_price",
        "shares",
        "entry_value",
        "exit_net_value",
        "realized_pnl",
        "return_pct",
        "holding_days",
        "exit_reason",
        "signal_close_adj",
        "signal_sar",
        "signal_rsi",
        "signal_volume_ratio",
        "signal_strength",
    ]
    if sells.empty:
        pd.DataFrame(columns=columns).to_csv(path, index=False)
        return
    result = pd.DataFrame(
        {
            "symbol": sells["symbol"],
            "entry_trade_date": sells["matched_entry_trade_date"],
            "exit_trade_date": sells["trade_date"],
            "entry_price": sells["matched_entry_price"],
            "exit_price": sells["price"],
            "shares": sells["shares"],
            "entry_value": sells["entry_value"],
            "exit_net_value": sells["net_trade_value"],
            "realized_pnl": sells["realized_pnl"],
            "return_pct": sells["return_pct"],
            "holding_days": sells["holding_days"],
            "exit_reason": sells["inferred_reason"],
            "signal_close_adj": sells["signal_close_adj"],
            "signal_sar": sells["signal_sar"],
            "signal_rsi": sells["signal_rsi"],
            "signal_volume_ratio": sells["signal_volume_ratio"],
            "signal_strength": sells["signal_signal_strength"],
        }
    )
    result[columns].to_csv(path, index=False)


def _copy_result(source: Path, destination: Path) -> None:
    shutil.copyfile(source, destination)


def _write_source_inventory(paths: ProjectPaths, path: Path) -> None:
    rows = []
    sources = [
        paths.interim_root / "trade_calendar.csv",
        paths.interim_root / "index_weight_top50.csv",
        paths.interim_root / "index_daily.csv",
        paths.interim_root / "symbols.json",
        *sorted(paths.price_root.glob("*.csv")),
    ]
    for source in sources:
        if not source.exists():
            continue
        rows.append(_inventory_row(paths.root, source))
    pd.DataFrame(rows).to_csv(path, index=False)


def _inventory_row(root: Path, source: Path) -> dict[str, object]:
    row = {
        "relative_path": str(source.relative_to(root)),
        "bytes": source.stat().st_size,
        "sha256": _sha256(source),
        "rows": pd.NA,
        "start_date": pd.NA,
        "end_date": pd.NA,
        "columns": pd.NA,
    }
    if source.suffix == ".csv":
        frame = pd.read_csv(source, dtype=str)
        row["rows"] = len(frame)
        date_column = "trade_date" if "trade_date" in frame else "cal_date" if "cal_date" in frame else None
        if date_column is not None and len(frame):
            row["start_date"] = frame[date_column].min()
            row["end_date"] = frame[date_column].max()
        row["columns"] = "|".join(frame.columns)
    elif source.suffix == ".json":
        values = json.loads(source.read_text(encoding="utf-8"))
        row["rows"] = len(values) if isinstance(values, list) else 1
        row["columns"] = "json"
    return row


def _write_raw_snapshot_manifest(raw_root: Path, path: Path) -> None:
    rows = []
    if raw_root.exists():
        for source in sorted(raw_root.glob("*/*.json")):
            rows.append(_snapshot_row(raw_root.parent.parent, source))
    columns = ["relative_path", "endpoint", "captured_at_utc", "params", "payload_rows", "bytes", "sha256"]
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)


def _snapshot_row(root: Path, source: Path) -> dict[str, object]:
    row = {
        "relative_path": str(source.relative_to(root)),
        "endpoint": pd.NA,
        "captured_at_utc": pd.NA,
        "params": pd.NA,
        "payload_rows": pd.NA,
        "bytes": source.stat().st_size,
        "sha256": _sha256(source),
    }
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
        metadata = payload.get("metadata", {})
        row["endpoint"] = metadata.get("endpoint", pd.NA)
        row["captured_at_utc"] = metadata.get("captured_at_utc", pd.NA)
        row["params"] = json.dumps(metadata.get("params", {}), ensure_ascii=False, sort_keys=True)
        data = payload.get("payload", [])
        row["payload_rows"] = len(data) if hasattr(data, "__len__") else pd.NA
    except Exception as exc:
        row["endpoint"] = f"unreadable:{type(exc).__name__}"
    return row


def _write_audit_manifest(audit_root: Path) -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for source in sorted(audit_root.iterdir()):
        if source.name == "audit_manifest.csv" or not source.is_file():
            continue
        rows.append(
            {
                "file": source.name,
                "bytes": source.stat().st_size,
                "sha256": _sha256(source),
                "generated_at_utc": generated_at,
            }
        )
    pd.DataFrame(rows).to_csv(audit_root / "audit_manifest.csv", index=False)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _to_float(value: object) -> Optional[float]:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None
