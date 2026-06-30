import unittest

import pandas as pd

from sar_project.backtest import (
    BacktestInputs,
    ExecutionParams,
    Position,
    StrategyParams,
    calculate_buy_capacity,
    calculate_trade_cost,
    run_backtest,
    with_price_lookup,
)


def _price_frame(close_values, *, up_limits=None, down_limits=None):
    dates = ["20210101", "20210104", "20210105", "20210106"]
    up_limits = up_limits or [99, 99, 99, 99]
    down_limits = down_limits or [1, 1, 1, 1]
    return pd.DataFrame(
        {
            "trade_date": dates,
            "open_adj": close_values,
            "high_adj": [value + 0.2 for value in close_values],
            "low_adj": [value - 0.2 for value in close_values],
            "close_adj": close_values,
            "sar": [value - 1 for value in close_values],
            "rsi": [50, 50, 50, 50],
            "volume_ratio": [2.0, 2.0, 2.0, 2.0],
            "signal_strength": [1.0, 1.0, 1.0, 1.0],
            "atr20": [1.0, 1.0, 1.0, 1.0],
            "ma60": close_values,
            "up_limit_adj": up_limits,
            "down_limit_adj": down_limits,
        }
    )


def _price_frame_with_raw(raw_values, adjusted_values):
    frame = _price_frame(adjusted_values)
    frame["open"] = raw_values
    frame["high"] = [value + 0.2 for value in raw_values]
    frame["low"] = [value - 0.2 for value in raw_values]
    frame["close"] = raw_values
    frame["up_limit"] = [value * 1.1 for value in raw_values]
    frame["down_limit"] = [value * 0.9 for value in raw_values]
    return frame


class SarBacktestTest(unittest.TestCase):
    def test_trade_cost_distinguishes_buy_and_sell_tax(self):
        params = ExecutionParams(
            commission_rate=0.0003,
            stamp_tax_rate=0.001,
            slippage_rate=0.0005,
            minimum_commission=0.0,
        )

        buy = calculate_trade_cost(10000, "buy", params)
        sell = calculate_trade_cost(10000, "sell", params)

        self.assertAlmostEqual(buy.commission, 3.0)
        self.assertAlmostEqual(buy.stamp_tax, 0.0)
        self.assertAlmostEqual(sell.commission, 3.0)
        self.assertAlmostEqual(sell.stamp_tax, 10.0)

    def test_trade_cost_applies_minimum_commission(self):
        params = ExecutionParams(commission_rate=0.0003, stamp_tax_rate=0.001, minimum_commission=5.0)

        buy = calculate_trade_cost(1000, "buy", params)
        sell = calculate_trade_cost(1000, "sell", params)

        self.assertAlmostEqual(buy.commission, 5.0)
        self.assertAlmostEqual(sell.commission, 5.0)
        self.assertAlmostEqual(sell.stamp_tax, 1.0)

    def test_buy_capacity_rounds_to_board_lot_and_includes_costs(self):
        params = ExecutionParams(commission_rate=0.0003, slippage_rate=0.0005, minimum_commission=0.0, lot_size=100)

        shares = calculate_buy_capacity(cash=100000, raw_open_price=10.0, params=params)

        self.assertEqual(shares % 100, 0)
        self.assertLessEqual(shares, 9900)

    def test_multi_buy_allocation_uses_remaining_buy_count(self):
        prices = {symbol: _price_frame([10.0, 10.0, 10.0, 10.0]) for symbol in ["AAA", "BBB", "CCC"]}
        inputs = BacktestInputs(
            trading_dates=["20210101", "20210104", "20210105", "20210106"],
            prices=prices,
            universe_by_date={date: ["AAA", "BBB", "CCC"] for date in ["20210101", "20210104", "20210105", "20210106"]},
        )

        result = run_backtest(
            inputs,
            StrategyParams(max_positions=3, rebalance_interval=1, initial_capital=30000),
            ExecutionParams(
                commission_rate=0.0,
                stamp_tax_rate=0.0,
                slippage_rate=0.0,
                minimum_commission=0.0,
                lot_size=100,
            ),
        )

        buys = result.trades[result.trades["action"] == "buy"].sort_values("symbol")
        self.assertEqual(buys["shares"].tolist(), [1000, 1000, 1000])
        self.assertAlmostEqual(result.portfolio.iloc[1]["cash"], 0.0)

    def test_signals_execute_on_next_trading_day_not_same_close(self):
        prices = {"AAA": _price_frame([10.0, 11.0, 12.0, 13.0])}
        inputs = BacktestInputs(
            trading_dates=["20210101", "20210104", "20210105", "20210106"],
            prices=prices,
            universe_by_date={date: ["AAA"] for date in ["20210101", "20210104", "20210105", "20210106"]},
        )

        result = run_backtest(
            inputs,
            StrategyParams(max_positions=1, rebalance_interval=1, initial_capital=100000),
            ExecutionParams(lot_size=100),
        )

        buy_trades = result.trades[result.trades["action"] == "buy"]
        self.assertEqual(len(buy_trades), 1)
        self.assertEqual(buy_trades.iloc[0]["signal_date"], "20210101")
        self.assertEqual(buy_trades.iloc[0]["trade_date"], "20210104")

    def test_market_filter_blocks_new_buys(self):
        prices = {"AAA": _price_frame([10.0, 11.0, 12.0, 13.0])}
        benchmark = pd.DataFrame(
            {
                "trade_date": ["20210101", "20210104", "20210105", "20210106"],
                "benchmark_value": [100.0, 99.0, 98.0, 97.0],
            }
        )
        inputs = BacktestInputs(
            trading_dates=["20210101", "20210104", "20210105", "20210106"],
            prices=prices,
            universe_by_date={date: ["AAA"] for date in ["20210101", "20210104", "20210105", "20210106"]},
            benchmark=benchmark,
        )

        result = run_backtest(
            inputs,
            StrategyParams(
                max_positions=1,
                rebalance_interval=1,
                initial_capital=100000,
                use_market_filter=True,
                market_ma_window=2,
            ),
            ExecutionParams(lot_size=100),
        )

        self.assertTrue(result.trades.empty)

    def test_atr_trailing_stop_sells_after_close_signal(self):
        frame = _price_frame_with_raw(
            raw_values=[10.0, 10.0, 10.0, 10.0],
            adjusted_values=[10.0, 10.0, 10.0, 10.0],
        )
        frame["atr20"] = [1.0, 1.0, 1.0, 1.0]
        position = Position(
            symbol="AAA",
            shares=1000,
            cost_basis=10.0,
            entry_date="20201231",
            last_price=12.0,
            highest_price=12.0,
        )
        inputs = BacktestInputs(
            trading_dates=["20210101", "20210104", "20210105", "20210106"],
            prices={"AAA": frame},
            universe_by_date={date: ["AAA"] for date in ["20210101", "20210104", "20210105", "20210106"]},
            starting_positions={"AAA": position},
            starting_cash=0.0,
        )

        result = run_backtest(
            inputs,
            StrategyParams(
                max_positions=1,
                rebalance_interval=10,
                initial_capital=10000,
                stop_loss=1.0,
                take_profit=10.0,
                use_atr_trailing_stop=True,
                atr_stop_multiplier=1.0,
            ),
            ExecutionParams(
                commission_rate=0.0,
                stamp_tax_rate=0.0,
                slippage_rate=0.0,
                minimum_commission=0.0,
                lot_size=100,
            ),
        )

        sells = result.trades[result.trades["action"] == "sell"]
        self.assertEqual(len(sells), 1)
        self.assertEqual(sells.iloc[0]["signal_date"], "20210101")
        self.assertEqual(sells.iloc[0]["trade_date"], "20210104")

    def test_inverse_volatility_sizing_allocates_more_to_lower_volatility(self):
        low_vol = _price_frame([10.0, 10.0, 10.0, 10.0])
        high_vol = _price_frame([10.0, 10.0, 10.0, 10.0])
        low_vol["atr20"] = [1.0, 1.0, 1.0, 1.0]
        high_vol["atr20"] = [4.0, 4.0, 4.0, 4.0]
        inputs = BacktestInputs(
            trading_dates=["20210101", "20210104", "20210105", "20210106"],
            prices={"AAA": low_vol, "BBB": high_vol},
            universe_by_date={date: ["AAA", "BBB"] for date in ["20210101", "20210104", "20210105", "20210106"]},
        )

        result = run_backtest(
            inputs,
            StrategyParams(
                max_positions=2,
                rebalance_interval=1,
                initial_capital=100000,
                use_inverse_volatility_sizing=True,
            ),
            ExecutionParams(
                commission_rate=0.0,
                stamp_tax_rate=0.0,
                slippage_rate=0.0,
                minimum_commission=0.0,
                lot_size=100,
            ),
        )

        buys = result.trades[result.trades["action"] == "buy"].set_index("symbol")
        self.assertGreater(int(buys.loc["AAA", "shares"]), int(buys.loc["BBB", "shares"]))

    def test_execution_and_valuation_use_raw_prices_when_available(self):
        frame = _price_frame_with_raw(
            raw_values=[100.0, 100.0, 101.0, 102.0],
            adjusted_values=[10.0, 10.0, 10.1, 10.2],
        )
        inputs = BacktestInputs(
            trading_dates=["20210101", "20210104", "20210105", "20210106"],
            prices={"AAA": frame},
            universe_by_date={date: ["AAA"] for date in ["20210101", "20210104", "20210105", "20210106"]},
        )

        result = run_backtest(
            inputs,
            StrategyParams(max_positions=1, rebalance_interval=1, initial_capital=10000),
            ExecutionParams(
                commission_rate=0.0,
                stamp_tax_rate=0.0,
                slippage_rate=0.0,
                minimum_commission=0.0,
                lot_size=100,
            ),
        )

        buy = result.trades[result.trades["action"] == "buy"].iloc[0]
        self.assertEqual(int(buy["shares"]), 100)
        self.assertAlmostEqual(buy["price"], 100.0)
        self.assertAlmostEqual(result.portfolio.iloc[1]["portfolio_value"], 10000.0)
        self.assertAlmostEqual(result.portfolio.iloc[2]["portfolio_value"], 10100.0)

    def test_raw_down_limit_blocks_sell_execution(self):
        frame = _price_frame_with_raw(
            raw_values=[10.0, 9.0, 8.0, 8.0],
            adjusted_values=[50.0, 50.0, 50.0, 50.0],
        )
        frame["down_limit"] = [1.0, 9.0, 8.0, 1.0]
        frame["down_limit_adj"] = [1.0, 1.0, 1.0, 1.0]
        frame.loc[0, "sar"] = 60.0
        position = Position(symbol="AAA", shares=1000, cost_basis=10.0, entry_date="20201231", last_price=10.0)
        inputs = BacktestInputs(
            trading_dates=["20210101", "20210104", "20210105", "20210106"],
            prices={"AAA": frame},
            universe_by_date={date: ["AAA"] for date in ["20210101", "20210104", "20210105", "20210106"]},
            starting_positions={"AAA": position},
            starting_cash=0.0,
        )

        result = run_backtest(
            inputs,
            StrategyParams(max_positions=1, rebalance_interval=1, initial_capital=10000),
            ExecutionParams(lot_size=100),
        )

        blocked = result.trades[result.trades["action"] == "blocked_sell"]
        self.assertGreaterEqual(len(blocked), 1)
        self.assertEqual(blocked.iloc[0]["trade_date"], "20210104")

    def test_missing_close_uses_last_valid_valuation_price(self):
        frame = _price_frame_with_raw(
            raw_values=[10.0, 11.0, 12.0, 13.0],
            adjusted_values=[10.0, 11.0, 12.0, 13.0],
        )
        frame.loc[2, "close"] = pd.NA
        frame.loc[2, "close_adj"] = pd.NA
        position = Position(symbol="AAA", shares=1000, cost_basis=8.0, entry_date="20201231", last_price=10.0)
        inputs = BacktestInputs(
            trading_dates=["20210101", "20210104", "20210105", "20210106"],
            prices={"AAA": frame},
            universe_by_date={date: ["AAA"] for date in ["20210101", "20210104", "20210105", "20210106"]},
            starting_positions={"AAA": position},
            starting_cash=0.0,
        )

        result = run_backtest(
            inputs,
            StrategyParams(max_positions=1, rebalance_interval=10, initial_capital=8000, take_profit=1.0),
            ExecutionParams(
                commission_rate=0.0,
                stamp_tax_rate=0.0,
                slippage_rate=0.0,
                minimum_commission=0.0,
                lot_size=100,
            ),
        )

        self.assertAlmostEqual(result.portfolio.iloc[0]["portfolio_value"], 10000.0)
        self.assertAlmostEqual(result.portfolio.iloc[1]["portfolio_value"], 11000.0)
        self.assertAlmostEqual(result.portfolio.iloc[2]["portfolio_value"], 11000.0)

    def test_down_limit_blocks_sell_execution(self):
        frame = _price_frame(
            [10.0, 9.0, 8.0, 8.0],
            down_limits=[1.0, 9.0, 8.0, 1.0],
        )
        frame.loc[0, "sar"] = 11.0
        frame.loc[1, "sar"] = 10.0
        position = Position(symbol="AAA", shares=1000, cost_basis=10.0, entry_date="20201231")
        inputs = BacktestInputs(
            trading_dates=["20210101", "20210104", "20210105", "20210106"],
            prices={"AAA": frame},
            universe_by_date={date: ["AAA"] for date in ["20210101", "20210104", "20210105", "20210106"]},
            starting_positions={"AAA": position},
            starting_cash=0.0,
        )

        result = run_backtest(
            inputs,
            StrategyParams(max_positions=1, rebalance_interval=1, initial_capital=10000),
            ExecutionParams(lot_size=100),
        )

        blocked = result.trades[result.trades["action"] == "blocked_sell"]
        self.assertGreaterEqual(len(blocked), 1)
        self.assertEqual(blocked.iloc[0]["trade_date"], "20210104")

    def test_sell_trade_records_calendar_holding_days(self):
        frame = _price_frame([10.0, 11.0, 12.0, 9.0])
        frame.loc[2, "sar"] = 13.0
        inputs = BacktestInputs(
            trading_dates=["20210101", "20210104", "20210105", "20210106"],
            prices={"AAA": frame},
            universe_by_date={date: ["AAA"] for date in ["20210101", "20210104", "20210105", "20210106"]},
        )

        result = run_backtest(
            inputs,
            StrategyParams(max_positions=1, rebalance_interval=1, initial_capital=100000),
            ExecutionParams(lot_size=100),
        )

        sells = result.trades[result.trades["action"] == "sell"]
        self.assertEqual(len(sells), 1)
        self.assertEqual(int(sells.iloc[0]["holding_days"]), 2)

    def test_sell_trade_return_pct_includes_buy_and_sell_costs(self):
        frame = _price_frame([10.0, 10.0, 10.0, 12.0])
        frame.loc[2, "sar"] = 13.0
        inputs = BacktestInputs(
            trading_dates=["20210101", "20210104", "20210105", "20210106"],
            prices={"AAA": frame},
            universe_by_date={date: ["AAA"] for date in ["20210101", "20210104", "20210105", "20210106"]},
        )

        result = run_backtest(
            inputs,
            StrategyParams(max_positions=1, rebalance_interval=1, initial_capital=100000),
            ExecutionParams(commission_rate=0.01, stamp_tax_rate=0.02, slippage_rate=0.0, lot_size=100),
        )

        buy = result.trades[result.trades["action"] == "buy"].iloc[0]
        sell = result.trades[result.trades["action"] == "sell"].iloc[0]
        shares = int(buy["shares"])
        entry_cash = shares * 10.0 * 1.01
        exit_cash = shares * 12.0 * (1 - 0.01 - 0.02)
        self.assertAlmostEqual(sell["return_pct"], exit_cash / entry_cash - 1)
        self.assertAlmostEqual(sell["realized_pnl"], exit_cash - entry_cash)

    def test_cached_price_lookup_preserves_backtest_results(self):
        prices = {"AAA": _price_frame([10.0, 11.0, 12.0, 13.0])}
        inputs = BacktestInputs(
            trading_dates=["20210101", "20210104", "20210105", "20210106"],
            prices=prices,
            universe_by_date={date: ["AAA"] for date in ["20210101", "20210104", "20210105", "20210106"]},
        )
        params = StrategyParams(max_positions=1, rebalance_interval=1, initial_capital=100000)

        normal = run_backtest(inputs, params, ExecutionParams(lot_size=100))
        cached = run_backtest(with_price_lookup(inputs), params, ExecutionParams(lot_size=100))

        pd.testing.assert_frame_equal(normal.portfolio, cached.portfolio)
        pd.testing.assert_frame_equal(normal.trades, cached.trades)


if __name__ == "__main__":
    unittest.main()
