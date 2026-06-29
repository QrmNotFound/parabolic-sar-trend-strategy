import unittest

import pandas as pd

from sar_project.metrics import calculate_performance_metrics
from sar_project.optimizer import ParameterGrid, choose_best_parameters


class SarMetricsOptimizerTest(unittest.TestCase):
    def test_trade_win_rate_is_distinct_from_positive_day_ratio(self):
        portfolio = pd.DataFrame(
            {
                "trade_date": ["20210101", "20210104", "20210105", "20210106"],
                "portfolio_value": [100.0, 101.0, 100.0, 102.0],
                "cash": [20.0, 20.2, 20.0, 20.4],
                "positions_count": [2, 2, 1, 1],
                "benchmark_value": [100.0, 100.5, 100.2, 100.4],
                "turnover": [0.0, 0.1, 0.0, 0.2],
            }
        )
        trades = pd.DataFrame(
            {
                "action": ["sell", "sell"],
                "symbol": ["AAA", "BBB"],
                "return_pct": [0.10, -0.05],
                "holding_days": [5, 3],
                "trade_value": [1000.0, 1000.0],
            }
        )

        metrics = calculate_performance_metrics(portfolio, trades, periods_per_year=252)

        self.assertAlmostEqual(metrics["trade_win_rate"], 0.5)
        self.assertNotEqual(metrics["trade_win_rate"], metrics["positive_day_ratio"])
        self.assertAlmostEqual(metrics["average_exposure"], 0.8)
        self.assertAlmostEqual(metrics["average_positions"], 1.5)
        self.assertAlmostEqual(metrics["top_symbol_trade_value_share"], 0.5)

    def test_profit_factor_uses_realized_pnl_when_available(self):
        portfolio = pd.DataFrame(
            {
                "trade_date": ["20210101", "20210104", "20210105"],
                "portfolio_value": [100.0, 101.0, 99.0],
                "cash": [20.0, 20.0, 20.0],
                "positions_count": [1, 1, 0],
                "benchmark_value": [100.0, 100.5, 100.0],
                "turnover": [0.0, 0.1, 0.1],
            }
        )
        trades = pd.DataFrame(
            {
                "action": ["sell", "sell"],
                "symbol": ["AAA", "BBB"],
                "return_pct": [0.50, -0.10],
                "realized_pnl": [100.0, -200.0],
                "holding_days": [5, 3],
                "trade_value": [1000.0, 1000.0],
            }
        )

        metrics = calculate_performance_metrics(portfolio, trades, periods_per_year=252)

        self.assertAlmostEqual(metrics["profit_factor"], 0.5)

    def test_optimizer_uses_only_sample_in_period_results(self):
        grid = ParameterGrid(
            accelerations=[0.01, 0.02],
            maximums=[0.2],
            volume_thresholds=[1.5],
            rsi_ceilings=[70],
        )
        calls = []

        def runner(params, start_date, end_date):
            calls.append((params.acceleration, start_date, end_date))
            if params.acceleration == 0.02:
                return {"sharpe_ratio": 1.0, "max_drawdown": -0.30}
            return {"sharpe_ratio": 1.0, "max_drawdown": -0.20}

        result = choose_best_parameters(grid, "20160101", "20201231", runner)

        self.assertEqual(result.best_params.acceleration, 0.01)
        self.assertTrue(all(call[1:] == ("20160101", "20201231") for call in calls))
        self.assertEqual(len(result.results), 2)

    def test_optimizer_rejects_low_exposure_candidate_before_scoring(self):
        grid = ParameterGrid(
            accelerations=[0.01, 0.02],
            maximums=[0.05],
            volume_thresholds=[0.5],
            rsi_ceilings=[100],
        )

        def runner(params, start_date, end_date):
            if params.acceleration == 0.02:
                return {
                    "excess_total_return": 0.50,
                    "sharpe_ratio": 2.0,
                    "max_drawdown": -0.05,
                    "turnover": 1.0,
                    "average_exposure": 0.10,
                    "average_positions": 1.0,
                    "low_exposure_day_ratio": 0.90,
                }
            return {
                "excess_total_return": 0.05,
                "sharpe_ratio": 0.5,
                "max_drawdown": -0.20,
                "turnover": 5.0,
                "average_exposure": 0.60,
                "average_positions": 8.0,
                "low_exposure_day_ratio": 0.05,
            }

        result = choose_best_parameters(grid, "20160101", "20201231", runner)

        self.assertEqual(result.best_params.acceleration, 0.01)
        rows = {row["acceleration"]: row for row in result.results}
        self.assertEqual(rows[0.01]["passes_selection_constraints"], 1.0)
        self.assertEqual(rows[0.02]["passes_selection_constraints"], 0.0)

    def test_optimizer_prefers_diversified_candidate_after_sample_in_floor(self):
        grid = ParameterGrid(
            accelerations=[0.01, 0.02, 0.03],
            maximums=[0.05],
            volume_thresholds=[0.5],
            rsi_ceilings=[100],
        )

        def runner(params, start_date, end_date):
            base = {
                "total_return": 0.40,
                "sharpe_ratio": 0.5,
                "max_drawdown": -0.28,
                "turnover": 10.0,
                "average_exposure": 0.70,
                "low_exposure_day_ratio": 0.05,
            }
            if params.acceleration == 0.01:
                return {
                    **base,
                    "excess_total_return": 0.25,
                    "max_drawdown": -0.35,
                    "average_positions": 20.0,
                }
            if params.acceleration == 0.02:
                return {
                    **base,
                    "excess_total_return": 0.13,
                    "average_positions": 15.0,
                }
            return {
                **base,
                "excess_total_return": 0.14,
                "average_positions": 8.0,
            }

        result = choose_best_parameters(grid, "20160101", "20201231", runner)

        self.assertEqual(result.best_params.acceleration, 0.02)
        rows = {row["acceleration"]: row for row in result.results}
        self.assertEqual(rows[0.01]["meets_sample_in_floor"], 0.0)
        self.assertEqual(rows[0.02]["meets_sample_in_floor"], 1.0)
        self.assertAlmostEqual(rows[0.02]["excess_total_return_for_score"], 0.12)


if __name__ == "__main__":
    unittest.main()
