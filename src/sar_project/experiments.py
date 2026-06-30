"""Fixed ablation experiments for the SAR stage-2 modules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from sar_project.backtest import ExecutionParams, StrategyParams, run_backtest, with_price_lookup
from sar_project.dataset import ProjectPaths, build_inputs_for_params, load_dataset
from sar_project.optimizer import SarParams


@dataclass(frozen=True)
class ModuleConfig:
    experiment: str
    use_market_filter: bool = False
    use_atr_trailing_stop: bool = False
    use_inverse_volatility_sizing: bool = False


ABLATION_CONFIGS: tuple[ModuleConfig, ...] = (
    ModuleConfig("E0_baseline"),
    ModuleConfig("E1_market_filter", use_market_filter=True),
    ModuleConfig("E2_atr_trailing_stop", use_atr_trailing_stop=True),
    ModuleConfig("E3_inverse_volatility_sizing", use_inverse_volatility_sizing=True),
    ModuleConfig("E4_market_filter_atr", use_market_filter=True, use_atr_trailing_stop=True),
    ModuleConfig("E5_market_filter_inverse_vol", use_market_filter=True, use_inverse_volatility_sizing=True),
    ModuleConfig("E6_atr_inverse_vol", use_atr_trailing_stop=True, use_inverse_volatility_sizing=True),
    ModuleConfig(
        "E7_all_modules",
        use_market_filter=True,
        use_atr_trailing_stop=True,
        use_inverse_volatility_sizing=True,
    ),
)


def run_stage2_ablation(
    paths: ProjectPaths,
    train_start: str,
    train_end: str,
    validation_start: str,
    validation_end: str,
    configs: Iterable[ModuleConfig] = ABLATION_CONFIGS,
) -> pd.DataFrame:
    """Run E0-E7 without changing the frozen Baseline V2 parameter set."""

    params = _load_best_params(paths.processed_root / "best_params.json")
    dataset = load_dataset(paths)
    inputs_by_period = {
        "sample_in": with_price_lookup(build_inputs_for_params(dataset, params, train_start, train_end)),
        "historical_validation": with_price_lookup(
            build_inputs_for_params(dataset, params, validation_start, validation_end)
        ),
    }
    rows = []
    for config in configs:
        for period, inputs in inputs_by_period.items():
            result = run_backtest(
                inputs,
                _strategy_from_params(params, config),
                ExecutionParams(),
            )
            rows.append(
                {
                    "experiment": config.experiment,
                    "period": period,
                    "use_market_filter": config.use_market_filter,
                    "use_atr_trailing_stop": config.use_atr_trailing_stop,
                    "use_inverse_volatility_sizing": config.use_inverse_volatility_sizing,
                    **result.metrics,
                }
            )
    result_frame = pd.DataFrame(rows)
    result_frame.to_csv(paths.processed_root / "stage2_ablation_results.csv", index=False)
    result_frame.to_csv(paths.docs_root / "stage2_ablation_results.csv", index=False)
    return result_frame


def _load_best_params(path: Path) -> SarParams:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return SarParams(**payload)


def _strategy_from_params(params: SarParams, config: ModuleConfig) -> StrategyParams:
    return StrategyParams(
        max_positions=params.max_positions,
        rebalance_interval=params.rebalance_interval,
        stop_loss=params.stop_loss,
        take_profit=params.take_profit,
        volume_threshold=params.volume_threshold,
        rsi_ceiling=params.rsi_ceiling,
        use_market_filter=config.use_market_filter,
        use_atr_trailing_stop=config.use_atr_trailing_stop,
        use_inverse_volatility_sizing=config.use_inverse_volatility_sizing,
    )
