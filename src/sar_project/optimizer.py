"""Sample-in parameter search for the SAR project."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List


@dataclass(frozen=True)
class SarParams:
    """Strategy signal parameters."""

    acceleration: float = 0.02
    maximum: float = 0.2
    volume_threshold: float = 1.5
    rsi_ceiling: float = 70.0
    max_positions: int = 10
    rebalance_interval: int = 5
    stop_loss: float = 0.05
    take_profit: float = 0.20


@dataclass(frozen=True)
class ParameterGrid:
    """Explicit parameter grid for real sample-in backtests."""

    accelerations: Iterable[float]
    maximums: Iterable[float]
    volume_thresholds: Iterable[float]
    rsi_ceilings: Iterable[float]
    max_positions: Iterable[int] = (10,)
    rebalance_intervals: Iterable[int] = (5,)
    stop_losses: Iterable[float] = (0.05,)
    take_profits: Iterable[float] = (0.20,)

    def combinations(self) -> Iterable[SarParams]:
        for acceleration in self.accelerations:
            for maximum in self.maximums:
                for volume_threshold in self.volume_thresholds:
                    for rsi_ceiling in self.rsi_ceilings:
                        for max_positions in self.max_positions:
                            for rebalance_interval in self.rebalance_intervals:
                                for stop_loss in self.stop_losses:
                                    for take_profit in self.take_profits:
                                        yield SarParams(
                                            acceleration,
                                            maximum,
                                            volume_threshold,
                                            rsi_ceiling,
                                            max_positions,
                                            rebalance_interval,
                                            stop_loss,
                                            take_profit,
                                        )


@dataclass(frozen=True)
class OptimizationResult:
    """Best parameter set and all evaluated sample-in metrics."""

    best_params: SarParams
    results: List[Dict[str, float]]


def choose_best_parameters(
    grid: ParameterGrid,
    train_start: str,
    train_end: str,
    run_once: Callable[[SarParams, str, str], Dict[str, float]],
    min_average_exposure: float = 0.45,
    min_average_positions: float = 5.0,
    max_low_exposure_day_ratio: float = 0.35,
) -> OptimizationResult:
    """Run each grid point on the sample-in period and choose a benchmark-aware result."""

    rows: List[Dict[str, float]] = []
    best_params = None
    best_key = None

    for params in grid.combinations():
        metrics = run_once(params, train_start, train_end)
        row = {
            "acceleration": params.acceleration,
            "maximum": params.maximum,
            "volume_threshold": params.volume_threshold,
            "rsi_ceiling": params.rsi_ceiling,
            "max_positions": params.max_positions,
            "rebalance_interval": params.rebalance_interval,
            "stop_loss": params.stop_loss,
            "take_profit": params.take_profit,
            **metrics,
        }
        passes_constraints = (
            metrics.get("average_exposure", 1.0) >= min_average_exposure
            and metrics.get("average_positions", min_average_positions) >= min_average_positions
            and metrics.get("low_exposure_day_ratio", 0.0) <= max_low_exposure_day_ratio
        )
        row["passes_selection_constraints"] = float(passes_constraints)
        rows.append(row)
        key = (
            1 if passes_constraints else 0,
            metrics.get("excess_total_return", 0.0),
            metrics.get("sharpe_ratio", 0.0),
            metrics.get("max_drawdown", -1.0),
            -metrics.get("turnover", 0.0),
        )
        if best_key is None or key > best_key:
            best_key = key
            best_params = params

    if best_params is None:
        raise ValueError("parameter grid produced no combinations")
    return OptimizationResult(best_params=best_params, results=rows)
