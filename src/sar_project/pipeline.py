"""Command-line pipeline for the SAR project."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict

import pandas as pd

from sar_project.backtest import ExecutionParams, StrategyParams, run_backtest, with_price_lookup
from sar_project.data_client import TinyshareClient, load_token
from sar_project.dataset import (
    ProjectPaths,
    build_data_coverage,
    build_inputs_for_params,
    create_offline_fixture,
    download_dataset,
    load_dataset,
)
from sar_project.optimizer import ParameterGrid, SarParams, choose_best_parameters
from sar_project.reporting import generate_report


TRAIN_START = "20160101"
TRAIN_END = "20201231"
TEST_START = "20210101"
TEST_END = "20251231"
START_DATE = "20160101"
END_DATE = "20251231"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="SAR project pipeline")
    parser.add_argument("command", choices=["download", "run", "report", "all"])
    parser.add_argument("--root", default=".", help="Project root")
    parser.add_argument("--offline-ok", action="store_true", help="Use deterministic fixture data if live data/token is unavailable")
    args = parser.parse_args(argv)

    paths = ProjectPaths(Path(args.root))
    paths.ensure()

    if args.command in {"download", "all"}:
        _download_or_fixture(paths, args.offline_ok)
    if args.command in {"run", "all"}:
        run_research(paths)
    if args.command in {"report", "all"}:
        offline = (paths.interim_root / "symbols.json").read_text(encoding="utf-8").find('"AAA"') >= 0
        coverage = build_data_coverage(paths)
        pd.DataFrame([coverage]).to_csv(paths.docs_root / "data_coverage.csv", index=False)
        generate_report(paths.processed_root, paths.docs_root, offline=offline, coverage=coverage)


def run_research(paths: ProjectPaths) -> None:
    """Run sample-in optimization, sample-out test, and full-period reference backtest."""

    dataset = load_dataset(paths)
    grid = ParameterGrid(
        accelerations=[0.003, 0.005, 0.01],
        maximums=[0.05, 0.10],
        volume_thresholds=[0.0, 0.5, 1.0],
        rsi_ceilings=[100],
        max_positions=[30, 50],
        rebalance_intervals=[20, 60],
        stop_losses=[0.30, 1.0],
        take_profits=[10.0],
    )
    input_cache = {}

    def inputs_for(params: SarParams, start_date: str, end_date: str):
        key = (
            params.acceleration,
            params.maximum,
            params.volume_threshold,
            params.rsi_ceiling,
            start_date,
            end_date,
        )
        if key not in input_cache:
            input_cache[key] = with_price_lookup(build_inputs_for_params(dataset, params, start_date, end_date))
        return input_cache[key]

    def run_once(params: SarParams, start_date: str, end_date: str) -> Dict[str, float]:
        inputs = inputs_for(params, start_date, end_date)
        result = run_backtest(
            inputs,
            _strategy_from_params(params),
            ExecutionParams(),
        )
        return result.metrics

    optimization = choose_best_parameters(grid, TRAIN_START, TRAIN_END, run_once)
    pd.DataFrame(optimization.results).to_csv(paths.processed_root / "optimization_results.csv", index=False)
    (paths.processed_root / "best_params.json").write_text(
        json.dumps(asdict(optimization.best_params), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    _run_and_save(paths, dataset, optimization.best_params, TRAIN_START, TRAIN_END, "train")
    _run_and_save(paths, dataset, optimization.best_params, TEST_START, TEST_END, "test")
    _run_and_save(paths, dataset, optimization.best_params, START_DATE, END_DATE, "full")


def _run_and_save(paths: ProjectPaths, dataset, params: SarParams, start_date: str, end_date: str, label: str) -> None:
    inputs = with_price_lookup(build_inputs_for_params(dataset, params, start_date, end_date))
    result = run_backtest(
        inputs,
        _strategy_from_params(params),
        ExecutionParams(),
    )
    result.portfolio.to_csv(paths.processed_root / f"portfolio_{label}.csv", index=False)
    trades = result.trades
    if trades.empty:
        trades = pd.DataFrame(
            columns=[
                "signal_date",
                "trade_date",
                "symbol",
                "action",
                "shares",
                "price",
                "trade_value",
                "commission",
                "stamp_tax",
                "net_trade_value",
                "entry_value",
                "realized_pnl",
                "return_pct",
                "holding_days",
                "reason",
            ]
        )
    trades.to_csv(paths.processed_root / f"trades_{label}.csv", index=False)
    (paths.processed_root / f"metrics_{label}.json").write_text(
        json.dumps(result.metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _strategy_from_params(params: SarParams) -> StrategyParams:
    return StrategyParams(
        max_positions=params.max_positions,
        rebalance_interval=params.rebalance_interval,
        stop_loss=params.stop_loss,
        take_profit=params.take_profit,
        volume_threshold=params.volume_threshold,
        rsi_ceiling=params.rsi_ceiling,
    )


def _download_or_fixture(paths: ProjectPaths, offline_ok: bool) -> None:
    token = load_token(paths.root / ".env")
    if token:
        download_dataset(paths, TinyshareClient(token), START_DATE, END_DATE, top_n=50)
        return
    if _has_cached_dataset(paths):
        print("[download] no token found; using cached sar_project dataset")
        return
    if offline_ok:
        create_offline_fixture(paths)
        return
    raise SystemExit("No TINYSHARE_TOKEN/TUSHARE_TOKEN found. Add .env or use --offline-ok.")


def _has_cached_dataset(paths: ProjectPaths) -> bool:
    return (
        (paths.interim_root / "trade_calendar.csv").exists()
        and (paths.interim_root / "index_weight_top50.csv").exists()
        and (paths.interim_root / "index_daily.csv").exists()
        and (paths.interim_root / "symbols.json").exists()
        and any(paths.price_root.glob("*.csv"))
    )


if __name__ == "__main__":
    main()
