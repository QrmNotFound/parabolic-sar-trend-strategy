"""Dataset download, cache, and fixture construction for the SAR project."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from sar_project.data_client import TinyshareClient, snapshot_frame
from sar_project.indicators import IndicatorParams, add_indicators
from sar_project.optimizer import SarParams


@dataclass(frozen=True)
class ProjectPaths:
    root: Path = Path(".")

    @property
    def raw_root(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def interim_root(self) -> Path:
        return self.root / "data" / "interim" / "sar_project"

    @property
    def processed_root(self) -> Path:
        return self.root / "data" / "processed" / "sar_project"

    @property
    def docs_root(self) -> Path:
        return self.root / "docs" / "sar_project"

    @property
    def price_root(self) -> Path:
        return self.interim_root / "prices"

    def ensure(self) -> None:
        for path in (self.raw_root, self.interim_root, self.processed_root, self.docs_root, self.price_root):
            path.mkdir(parents=True, exist_ok=True)


@dataclass
class SarDataset:
    trading_dates: Sequence[str]
    weights: pd.DataFrame
    prices: Dict[str, pd.DataFrame]
    benchmark: pd.DataFrame
    universe_by_date: Dict[str, Sequence[str]]
    equal_weight_benchmark: pd.DataFrame


def download_dataset(
    paths: ProjectPaths,
    client: TinyshareClient,
    start_date: str = "20160101",
    end_date: str = "20251231",
    top_n: int = 50,
) -> None:
    """Download and cache all raw/interim inputs required by the project."""

    paths.ensure()
    calendar = _call_and_snapshot(
        paths,
        client,
        "trade_cal",
        {"exchange": "SSE", "start_date": start_date, "end_date": end_date},
    )
    calendar = calendar.sort_values("cal_date")
    calendar.to_csv(paths.interim_root / "trade_calendar.csv", index=False)
    trading_dates = calendar.loc[calendar["is_open"] == 1, "cal_date"].astype(str).tolist()

    weight_frames = []
    for year in range(int(start_date[:4]), int(end_date[:4]) + 1):
        frame = _call_and_snapshot(
            paths,
            client,
            "index_weight",
            {"index_code": "000300.SH", "start_date": f"{year}0101", "end_date": f"{year}1231"},
        )
        if not frame.empty:
            weight_frames.append(frame)
    weights = pd.concat(weight_frames, ignore_index=True) if weight_frames else pd.DataFrame()
    weights = weights.sort_values(["trade_date", "weight"], ascending=[True, False])
    top_weights = weights.groupby("trade_date", as_index=False, group_keys=False).head(top_n)
    top_weights.to_csv(paths.interim_root / "index_weight_top50.csv", index=False)

    benchmark = _call_and_snapshot(
        paths,
        client,
        "index_daily",
        {"ts_code": "000300.SH", "start_date": start_date, "end_date": end_date},
    )
    benchmark.sort_values("trade_date").to_csv(paths.interim_root / "index_daily.csv", index=False)

    symbols = sorted(top_weights["con_code"].dropna().unique().tolist())
    (paths.interim_root / "symbols.json").write_text(json.dumps(symbols, ensure_ascii=False, indent=2), encoding="utf-8")

    for index, symbol in enumerate(symbols, start=1):
        out_path = paths.price_root / f"{symbol}.csv"
        if out_path.exists():
            continue
        try:
            daily = _call_and_snapshot(
                paths,
                client,
                "daily",
                {"ts_code": symbol, "start_date": start_date, "end_date": end_date},
            )
            adj = _call_and_snapshot(
                paths,
                client,
                "adj_factor",
                {"ts_code": symbol, "start_date": start_date, "end_date": end_date},
            )
            limits = _call_and_snapshot(
                paths,
                client,
                "stk_limit",
                {"ts_code": symbol, "start_date": start_date, "end_date": end_date},
            )
        except Exception as exc:
            print(f"[download] skip {symbol}: {type(exc).__name__}: {exc}")
            continue
        merged = prepare_price_frame(daily, adj, limits)
        if not merged.empty:
            merged.to_csv(out_path, index=False)
        print(f"[download] {index}/{len(symbols)} {symbol} rows={len(merged)}")


def load_dataset(paths: ProjectPaths) -> SarDataset:
    """Load cached SAR data from interim files."""

    weights = pd.read_csv(paths.interim_root / "index_weight_top50.csv", dtype={"trade_date": str})
    calendar = pd.read_csv(paths.interim_root / "trade_calendar.csv", dtype={"cal_date": str})
    trading_dates = calendar.loc[calendar["is_open"] == 1, "cal_date"].astype(str).tolist()
    benchmark_raw = pd.read_csv(paths.interim_root / "index_daily.csv", dtype={"trade_date": str})
    benchmark = build_index_benchmark(benchmark_raw, trading_dates)

    prices: Dict[str, pd.DataFrame] = {}
    symbols_path = paths.interim_root / "symbols.json"
    allowed_symbols = set(json.loads(symbols_path.read_text(encoding="utf-8"))) if symbols_path.exists() else None
    for path in sorted(paths.price_root.glob("*.csv")):
        if allowed_symbols is not None and path.stem not in allowed_symbols:
            continue
        prices[path.stem] = pd.read_csv(path, dtype={"trade_date": str})

    universe = build_universe_by_date(weights, trading_dates)
    equal_weight = build_equal_weight_benchmark(prices, universe, trading_dates)
    return SarDataset(trading_dates, weights, prices, benchmark, universe, equal_weight)


def build_data_coverage(paths: ProjectPaths) -> Dict[str, object]:
    """Summarize expected versus cached symbols for disclosure."""

    symbols_path = paths.interim_root / "symbols.json"
    symbols = json.loads(symbols_path.read_text(encoding="utf-8")) if symbols_path.exists() else []
    cached = {path.stem for path in paths.price_root.glob("*.csv")}
    downloaded = [symbol for symbol in symbols if symbol in cached]
    missing = [symbol for symbol in symbols if symbol not in cached]
    return {
        "expected_symbols": len(symbols),
        "downloaded_symbols": len(downloaded),
        "missing_symbols": len(missing),
        "missing_list": missing,
    }


def build_inputs_for_params(dataset: SarDataset, params: SarParams, start_date: str, end_date: str):
    """Build backtest inputs for a date slice and parameter set."""

    from sar_project.backtest import BacktestInputs

    indicator_params = IndicatorParams(params.acceleration, params.maximum)
    prices = {
        symbol: _with_signal_strength(add_indicators(frame, indicator_params), params)
        for symbol, frame in dataset.prices.items()
    }
    trading_dates = [date for date in dataset.trading_dates if start_date <= date <= end_date]
    universe = {date: dataset.universe_by_date.get(date, ()) for date in trading_dates}
    benchmark = dataset.benchmark[(dataset.benchmark["trade_date"] >= start_date) & (dataset.benchmark["trade_date"] <= end_date)]
    equal_weight = dataset.equal_weight_benchmark[
        (dataset.equal_weight_benchmark["trade_date"] >= start_date)
        & (dataset.equal_weight_benchmark["trade_date"] <= end_date)
    ]
    return BacktestInputs(trading_dates, prices, universe, benchmark, equal_weight)


def create_offline_fixture(paths: ProjectPaths) -> None:
    """Create a deterministic small dataset for offline integration tests."""

    paths.ensure()
    dates = pd.bdate_range("2016-01-04", "2025-12-31", freq="20B").strftime("%Y%m%d").tolist()
    calendar = pd.DataFrame({"exchange": "SSE", "cal_date": dates, "is_open": 1, "pretrade_date": [""] + dates[:-1]})
    calendar.to_csv(paths.interim_root / "trade_calendar.csv", index=False)

    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    weights = []
    for date in dates[::2]:
        for rank, symbol in enumerate(symbols):
            weights.append({"index_code": "000300.SH", "con_code": symbol, "trade_date": date, "weight": 10 - rank})
    pd.DataFrame(weights).to_csv(paths.interim_root / "index_weight_top50.csv", index=False)
    (paths.interim_root / "symbols.json").write_text(json.dumps(symbols, indent=2), encoding="utf-8")

    index_close = np.linspace(1000, 1500, len(dates)) + np.sin(np.arange(len(dates)) / 5) * 60
    pd.DataFrame({"ts_code": "000300.SH", "trade_date": dates, "close": index_close}).to_csv(
        paths.interim_root / "index_daily.csv", index=False
    )

    for offset, symbol in enumerate(symbols):
        base = 20 + offset * 3
        trend = np.linspace(0, 8 + offset, len(dates))
        wave = np.sin(np.arange(len(dates)) / (3 + offset)) * (1.5 + offset * 0.2)
        close = base + trend + wave
        volume = (
            1_000_000
            + offset * 100_000
            + (np.arange(len(dates)) % (4 + offset) == 0).astype(int) * 1_200_000
        )
        frame = pd.DataFrame(
            {
                "trade_date": dates,
                "open_adj": close * (1 + np.cos(np.arange(len(dates))) * 0.002),
                "high_adj": close * 1.02,
                "low_adj": close * 0.98,
                "close_adj": close,
                "vol": volume,
                "up_limit_adj": close * 1.10,
                "down_limit_adj": close * 0.90,
            }
        )
        frame.to_csv(paths.price_root / f"{symbol}.csv", index=False)


def prepare_price_frame(daily: pd.DataFrame, adj: pd.DataFrame, limits: pd.DataFrame) -> pd.DataFrame:
    """Merge daily bars, adjustment factors, and limit prices into adjusted fields."""

    if daily.empty or adj.empty:
        return pd.DataFrame()
    merged = daily.merge(adj[["ts_code", "trade_date", "adj_factor"]], on=["ts_code", "trade_date"], how="left")
    if not limits.empty:
        merged = merged.merge(limits[["ts_code", "trade_date", "up_limit", "down_limit"]], on=["ts_code", "trade_date"], how="left")
    merged = merged.sort_values("trade_date").reset_index(drop=True)
    merged["adj_factor"] = merged["adj_factor"].ffill().bfill()
    base_factor = merged["adj_factor"].iloc[-1]
    for column in ["open", "high", "low", "close", "pre_close"]:
        if column in merged:
            merged[f"{column}_adj"] = merged[column] * merged["adj_factor"] / base_factor
    for column in ["up_limit", "down_limit"]:
        if column in merged:
            merged[f"{column}_adj"] = merged[column] * merged["adj_factor"] / base_factor
    return merged


def build_universe_by_date(weights: pd.DataFrame, trading_dates: Sequence[str]) -> Dict[str, Sequence[str]]:
    """Map each trading date to the latest known monthly top-50 constituent list."""

    by_weight_date = {
        date: group.sort_values("weight", ascending=False)["con_code"].tolist()
        for date, group in weights.groupby(weights["trade_date"].astype(str))
    }
    known_dates = sorted(by_weight_date)
    result: Dict[str, Sequence[str]] = {}
    pointer = 0
    current: Sequence[str] = []
    for date in trading_dates:
        while pointer < len(known_dates) and known_dates[pointer] <= date:
            current = by_weight_date[known_dates[pointer]]
            pointer += 1
        result[date] = current
    return result


def build_index_benchmark(index_daily: pd.DataFrame, trading_dates: Sequence[str], initial_value: float = 1_000_000.0) -> pd.DataFrame:
    """Create an indexed buy-and-hold benchmark series."""

    if index_daily.empty:
        return pd.DataFrame({"trade_date": trading_dates, "benchmark_value": initial_value})
    frame = index_daily.sort_values("trade_date").copy()
    frame = frame[frame["trade_date"].isin(trading_dates)]
    first = frame["close"].astype(float).iloc[0]
    frame["benchmark_value"] = frame["close"].astype(float) / first * initial_value
    return frame[["trade_date", "benchmark_value"]]


def build_equal_weight_benchmark(
    prices: Mapping[str, pd.DataFrame],
    universe_by_date: Mapping[str, Sequence[str]],
    trading_dates: Sequence[str],
    initial_value: float = 1_000_000.0,
) -> pd.DataFrame:
    """Build a dynamic top-50 equal-weight close-to-close benchmark."""

    close_lookup = {
        symbol: frame.set_index("trade_date")["close_adj"].astype(float).to_dict()
        for symbol, frame in prices.items()
        if "close_adj" in frame
    }
    value = initial_value
    rows = []
    previous_date: Optional[str] = None
    for date in trading_dates:
        if previous_date is not None:
            returns = []
            for symbol in universe_by_date.get(previous_date, ()):
                symbol_close = close_lookup.get(symbol, {})
                if previous_date in symbol_close and date in symbol_close and symbol_close[previous_date]:
                    returns.append(symbol_close[date] / symbol_close[previous_date] - 1)
            if returns:
                value *= 1 + float(np.mean(returns))
        rows.append({"trade_date": date, "equal_weight_value": value})
        previous_date = date
    return pd.DataFrame(rows)


def _with_signal_strength(frame: pd.DataFrame, params: SarParams) -> pd.DataFrame:
    enriched = frame.copy()
    buy = (
        (enriched["close_adj"] > enriched["sar"])
        & (enriched["volume_ratio"] > params.volume_threshold)
        & (enriched["rsi"] < params.rsi_ceiling)
    )
    enriched["signal_strength"] = 0.0
    enriched.loc[buy, "signal_strength"] = (
        0.5
        + (enriched.loc[buy, "volume_ratio"].clip(upper=3.0) / 3.0) * 0.3
        + ((params.rsi_ceiling - enriched.loc[buy, "rsi"]).clip(lower=0) / params.rsi_ceiling) * 0.2
    )
    return enriched


def _call_and_snapshot(paths: ProjectPaths, client: TinyshareClient, endpoint: str, params: Mapping[str, object]) -> pd.DataFrame:
    frame = client.call(endpoint, **params)
    snapshot_frame(paths.raw_root, endpoint, params, frame)
    return frame
