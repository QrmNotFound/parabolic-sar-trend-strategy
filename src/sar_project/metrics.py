"""Performance metrics for SAR project backtests."""

from __future__ import annotations

import math
from typing import Dict

import numpy as np
import pandas as pd


def calculate_performance_metrics(
    portfolio: pd.DataFrame,
    trades: pd.DataFrame,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.03,
) -> Dict[str, float]:
    """Calculate portfolio, risk, and trade-level metrics."""

    if portfolio.empty or "portfolio_value" not in portfolio:
        return {}

    values = portfolio["portfolio_value"].astype(float)
    returns = values.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    total_return = values.iloc[-1] / values.iloc[0] - 1 if values.iloc[0] else 0.0
    years = max(len(values) / periods_per_year, 1 / periods_per_year)
    annual_return = (1 + total_return) ** (1 / years) - 1 if total_return > -1 else -1.0
    annual_volatility = returns.std(ddof=0) * math.sqrt(periods_per_year) if len(returns) else 0.0
    sharpe_ratio = (
        (annual_return - risk_free_rate) / annual_volatility if annual_volatility > 0 else 0.0
    )

    running_max = values.cummax()
    drawdown = values / running_max - 1
    max_drawdown = float(drawdown.min()) if len(drawdown) else 0.0
    calmar_ratio = annual_return / abs(max_drawdown) if max_drawdown < 0 else 0.0

    benchmark_value = portfolio.get("benchmark_value")
    information_ratio = 0.0
    benchmark_total_return = 0.0
    excess_total_return = 0.0
    benchmark_annual_return = 0.0
    excess_annual_return = 0.0
    benchmark_max_drawdown = 0.0
    max_drawdown_gap = 0.0
    if benchmark_value is not None:
        benchmark_values = benchmark_value.astype(float)
        benchmark_returns = benchmark_values.pct_change().replace([np.inf, -np.inf], np.nan)
        active_returns = (portfolio["portfolio_value"].pct_change() - benchmark_returns).dropna()
        if len(active_returns) and active_returns.std(ddof=0) > 0:
            information_ratio = active_returns.mean() / active_returns.std(ddof=0) * math.sqrt(periods_per_year)
        if len(benchmark_values) and benchmark_values.iloc[0]:
            benchmark_total_return = benchmark_values.iloc[-1] / benchmark_values.iloc[0] - 1
            benchmark_annual_return = (1 + benchmark_total_return) ** (1 / years) - 1 if benchmark_total_return > -1 else -1.0
            benchmark_drawdown = benchmark_values / benchmark_values.cummax() - 1
            benchmark_max_drawdown = float(benchmark_drawdown.min())
            excess_total_return = total_return - benchmark_total_return
            excess_annual_return = annual_return - benchmark_annual_return
            max_drawdown_gap = max_drawdown - benchmark_max_drawdown

    sell_trades = trades[trades.get("action", pd.Series(dtype=str)) == "sell"] if not trades.empty else trades
    trade_returns = sell_trades.get("return_pct", pd.Series(dtype=float)).dropna().astype(float)
    wins = trade_returns[trade_returns > 0]
    losses = trade_returns[trade_returns < 0]
    trade_win_rate = float((trade_returns > 0).mean()) if len(trade_returns) else 0.0
    average_win = float(wins.mean()) if len(wins) else 0.0
    average_loss = float(losses.mean()) if len(losses) else 0.0
    profit_factor = float(wins.sum() / abs(losses.sum())) if abs(losses.sum()) > 0 else 0.0
    payoff_ratio = float(average_win / abs(average_loss)) if average_loss < 0 else 0.0

    turnover = portfolio.get("turnover", pd.Series(dtype=float)).fillna(0).astype(float)
    holding_days = sell_trades.get("holding_days", pd.Series(dtype=float)).dropna().astype(float)
    cash = portfolio.get("cash", pd.Series([0.0] * len(portfolio))).astype(float)
    exposure = (1 - cash / values.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0).clip(0, 1)
    positions_count = portfolio.get("positions_count", pd.Series([0] * len(portfolio))).fillna(0).astype(float)
    if not trades.empty:
        actions = trades["action"] if "action" in trades else pd.Series("", index=trades.index)
        executed_trades = trades[actions.isin(["buy", "sell"])]
    else:
        executed_trades = trades
    trade_value = executed_trades.get("trade_value", pd.Series(dtype=float)).fillna(0).astype(float)
    symbol_trade_value = (
        executed_trades.assign(_trade_value=trade_value).groupby("symbol")["_trade_value"].sum()
        if not executed_trades.empty and "symbol" in executed_trades
        else pd.Series(dtype=float)
    )
    total_trade_value = float(symbol_trade_value.sum()) if len(symbol_trade_value) else 0.0
    top_symbol_trade_value_share = (
        float(symbol_trade_value.max() / total_trade_value) if total_trade_value > 0 else 0.0
    )

    return {
        "total_return": float(total_return),
        "annual_return": float(annual_return),
        "annual_volatility": float(annual_volatility),
        "sharpe_ratio": float(sharpe_ratio),
        "max_drawdown": max_drawdown,
        "benchmark_total_return": float(benchmark_total_return),
        "excess_total_return": float(excess_total_return),
        "benchmark_annual_return": float(benchmark_annual_return),
        "excess_annual_return": float(excess_annual_return),
        "benchmark_max_drawdown": float(benchmark_max_drawdown),
        "max_drawdown_gap": float(max_drawdown_gap),
        "beats_benchmark_total_return": float(excess_total_return > 0),
        "beats_benchmark_annual_return": float(excess_annual_return >= 0),
        "calmar_ratio": float(calmar_ratio),
        "information_ratio": float(information_ratio),
        "positive_day_ratio": float((returns > 0).mean()) if len(returns) else 0.0,
        "trade_win_rate": trade_win_rate,
        "average_win": average_win,
        "average_loss": average_loss,
        "payoff_ratio": payoff_ratio,
        "profit_factor": profit_factor,
        "average_holding_days": float(holding_days.mean()) if len(holding_days) else 0.0,
        "turnover": float(turnover.sum()),
        "average_exposure": float(exposure.mean()) if len(exposure) else 0.0,
        "median_exposure": float(exposure.median()) if len(exposure) else 0.0,
        "low_exposure_day_ratio": float((exposure < 0.2).mean()) if len(exposure) else 0.0,
        "average_positions": float(positions_count.mean()) if len(positions_count) else 0.0,
        "zero_position_day_ratio": float((positions_count == 0).mean()) if len(positions_count) else 0.0,
        "executed_trade_count": float(len(executed_trades)),
        "sell_trade_count": float(len(sell_trades)),
        "unique_symbols_traded": float(executed_trades["symbol"].nunique()) if not executed_trades.empty and "symbol" in executed_trades else 0.0,
        "top_symbol_trade_value_share": top_symbol_trade_value_share,
        "final_value": float(values.iloc[-1]),
    }


def max_drawdown_series(values: pd.Series) -> pd.Series:
    """Return drawdown series for plotting."""

    running_max = values.astype(float).cummax()
    return values.astype(float) / running_max - 1
