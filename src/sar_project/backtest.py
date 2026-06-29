"""Long-only SAR backtest engine with t+1 execution and A-share constraints."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, Optional, Sequence

import pandas as pd

from sar_project.metrics import calculate_performance_metrics


@dataclass(frozen=True)
class ExecutionParams:
    """Market frictions and A-share execution constraints."""

    commission_rate: float = 0.0003
    stamp_tax_rate: float = 0.001
    slippage_rate: float = 0.0005
    lot_size: int = 100


@dataclass(frozen=True)
class StrategyParams:
    """Portfolio construction and signal thresholds."""

    max_positions: int = 10
    rebalance_interval: int = 5
    initial_capital: float = 1_000_000.0
    stop_loss: float = 0.05
    take_profit: float = 0.20
    volume_threshold: float = 1.5
    rsi_ceiling: float = 70.0


@dataclass
class Position:
    symbol: str
    shares: int
    cost_basis: float
    entry_date: str


@dataclass(frozen=True)
class TradeCost:
    commission: float
    stamp_tax: float
    total: float


@dataclass(frozen=True)
class BacktestInputs:
    trading_dates: Sequence[str]
    prices: Mapping[str, pd.DataFrame]
    universe_by_date: Mapping[str, Sequence[str]]
    benchmark: Optional[pd.DataFrame] = None
    equal_weight_benchmark: Optional[pd.DataFrame] = None
    starting_positions: Mapping[str, Position] = field(default_factory=dict)
    starting_cash: Optional[float] = None
    price_lookup: Optional[Mapping[str, Mapping[str, Mapping[str, object]]]] = None


@dataclass(frozen=True)
class BacktestResult:
    portfolio: pd.DataFrame
    trades: pd.DataFrame
    metrics: Dict[str, float]


@dataclass(frozen=True)
class PendingOrders:
    signal_date: str
    sells: Sequence[str]
    buys: Sequence[str]


def calculate_trade_cost(trade_value: float, side: str, params: ExecutionParams) -> TradeCost:
    """Calculate commission and sell-side stamp tax."""

    commission = trade_value * params.commission_rate
    stamp_tax = trade_value * params.stamp_tax_rate if side == "sell" else 0.0
    return TradeCost(commission=commission, stamp_tax=stamp_tax, total=commission + stamp_tax)


def calculate_buy_capacity(cash: float, raw_open_price: float, params: ExecutionParams) -> int:
    """Return board-lot shares purchasable after slippage and commission."""

    if cash <= 0 or raw_open_price <= 0:
        return 0
    execution_price = raw_open_price * (1 + params.slippage_rate)
    gross_lot_cost = execution_price * params.lot_size * (1 + params.commission_rate)
    lots = int(cash // gross_lot_cost)
    return lots * params.lot_size


def run_backtest(
    inputs: BacktestInputs,
    strategy_params: StrategyParams,
    execution_params: ExecutionParams,
) -> BacktestResult:
    """Run a deterministic long-only backtest with next-open execution."""

    price_lookup = inputs.price_lookup if inputs.price_lookup is not None else _build_price_lookup(inputs.prices)
    positions = {symbol: Position(**vars(position)) for symbol, position in inputs.starting_positions.items()}
    cash = strategy_params.initial_capital if inputs.starting_cash is None else inputs.starting_cash
    pending: Optional[PendingOrders] = None
    portfolio_rows = []
    trade_rows = []

    for index, trade_date in enumerate(inputs.trading_dates):
        turnover = 0.0
        if pending is not None:
            cash, turnover = _execute_pending_orders(
                pending,
                trade_date,
                cash,
                positions,
                price_lookup,
                strategy_params,
                execution_params,
                trade_rows,
            )

        close_value = _portfolio_value(cash, positions, price_lookup, trade_date)
        portfolio_rows.append(
            {
                "trade_date": trade_date,
                "cash": cash,
                "positions_count": len(positions),
                "portfolio_value": close_value,
                "turnover": turnover / close_value if close_value else 0.0,
            }
        )

        pending = _make_pending_orders(
            signal_date=trade_date,
            rebalance_now=index % strategy_params.rebalance_interval == 0,
            positions=positions,
            price_lookup=price_lookup,
            universe=inputs.universe_by_date.get(trade_date, ()),
            strategy_params=strategy_params,
        )

    portfolio = pd.DataFrame(portfolio_rows)
    portfolio = _attach_benchmarks(portfolio, inputs.benchmark, inputs.equal_weight_benchmark)
    trades = pd.DataFrame(trade_rows)
    metrics = calculate_performance_metrics(portfolio, trades)
    return BacktestResult(portfolio=portfolio, trades=trades, metrics=metrics)


def with_price_lookup(inputs: BacktestInputs) -> BacktestInputs:
    """Return inputs with a cached price lookup for repeated strategy runs."""

    return BacktestInputs(
        trading_dates=inputs.trading_dates,
        prices=inputs.prices,
        universe_by_date=inputs.universe_by_date,
        benchmark=inputs.benchmark,
        equal_weight_benchmark=inputs.equal_weight_benchmark,
        starting_positions=inputs.starting_positions,
        starting_cash=inputs.starting_cash,
        price_lookup=inputs.price_lookup or _build_price_lookup(inputs.prices),
    )


def _build_price_lookup(prices: Mapping[str, pd.DataFrame]) -> Dict[str, Dict[str, pd.Series]]:
    lookup: Dict[str, Dict[str, Mapping[str, object]]] = {}
    for symbol, frame in prices.items():
        if "trade_date" not in frame:
            raise ValueError(f"{symbol} price frame missing trade_date")
        lookup[symbol] = {str(row["trade_date"]): row for row in frame.to_dict(orient="records")}
    return lookup


def _execute_pending_orders(
    pending: PendingOrders,
    trade_date: str,
    cash: float,
    positions: Dict[str, Position],
    price_lookup: Mapping[str, Mapping[str, pd.Series]],
    strategy_params: StrategyParams,
    execution_params: ExecutionParams,
    trade_rows: list,
) -> tuple[float, float]:
    turnover = 0.0

    for symbol in pending.sells:
        position = positions.get(symbol)
        row = price_lookup.get(symbol, {}).get(trade_date)
        if position is None:
            continue
        if row is None or pd.isna(row.get("open_adj")):
            trade_rows.append(_blocked_trade(pending.signal_date, trade_date, symbol, "blocked_sell", "missing_open"))
            continue
        raw_open = float(row["open_adj"])
        if _at_down_limit(row, raw_open):
            trade_rows.append(_blocked_trade(pending.signal_date, trade_date, symbol, "blocked_sell", "down_limit"))
            continue

        execution_price = raw_open * (1 - execution_params.slippage_rate)
        trade_value = execution_price * position.shares
        costs = calculate_trade_cost(trade_value, "sell", execution_params)
        cash += trade_value - costs.total
        turnover += trade_value
        return_pct = execution_price / position.cost_basis - 1 if position.cost_basis else 0.0
        trade_rows.append(
            {
                "signal_date": pending.signal_date,
                "trade_date": trade_date,
                "symbol": symbol,
                "action": "sell",
                "shares": position.shares,
                "price": execution_price,
                "trade_value": trade_value,
                "commission": costs.commission,
                "stamp_tax": costs.stamp_tax,
                "return_pct": return_pct,
                "holding_days": _calendar_days_between(position.entry_date, trade_date),
                "reason": "signal_or_risk",
            }
        )
        del positions[symbol]

    buy_slots = max(strategy_params.max_positions - len(positions), 0)
    buy_symbols = [symbol for symbol in pending.buys if symbol not in positions][:buy_slots]
    for symbol in buy_symbols:
        if cash <= 0:
            break
        row = price_lookup.get(symbol, {}).get(trade_date)
        if row is None or pd.isna(row.get("open_adj")):
            trade_rows.append(_blocked_trade(pending.signal_date, trade_date, symbol, "blocked_buy", "missing_open"))
            continue
        raw_open = float(row["open_adj"])
        if _at_up_limit(row, raw_open):
            trade_rows.append(_blocked_trade(pending.signal_date, trade_date, symbol, "blocked_buy", "up_limit"))
            continue
        allocation = cash / max(len(buy_symbols), 1)
        shares = calculate_buy_capacity(allocation, raw_open, execution_params)
        if shares <= 0:
            continue
        execution_price = raw_open * (1 + execution_params.slippage_rate)
        trade_value = execution_price * shares
        costs = calculate_trade_cost(trade_value, "buy", execution_params)
        total_cash_needed = trade_value + costs.total
        if total_cash_needed > cash:
            shares = calculate_buy_capacity(cash, raw_open, execution_params)
            trade_value = execution_price * shares
            costs = calculate_trade_cost(trade_value, "buy", execution_params)
            total_cash_needed = trade_value + costs.total
        if shares <= 0:
            continue
        cash -= total_cash_needed
        turnover += trade_value
        positions[symbol] = Position(symbol=symbol, shares=shares, cost_basis=execution_price, entry_date=trade_date)
        trade_rows.append(
            {
                "signal_date": pending.signal_date,
                "trade_date": trade_date,
                "symbol": symbol,
                "action": "buy",
                "shares": shares,
                "price": execution_price,
                "trade_value": trade_value,
                "commission": costs.commission,
                "stamp_tax": costs.stamp_tax,
                "return_pct": pd.NA,
                "holding_days": pd.NA,
                "reason": "signal_buy",
            }
        )

    return cash, turnover


def _make_pending_orders(
    signal_date: str,
    rebalance_now: bool,
    positions: Mapping[str, Position],
    price_lookup: Mapping[str, Mapping[str, pd.Series]],
    universe: Iterable[str],
    strategy_params: StrategyParams,
) -> PendingOrders:
    universe_set = set(universe)
    sells = []
    for symbol, position in positions.items():
        row = price_lookup.get(symbol, {}).get(signal_date)
        if row is None:
            sells.append(symbol)
            continue
        close = float(row["close_adj"])
        sell_signal = (
            close < float(row.get("sar", close))
            or float(row.get("rsi", 50.0)) > strategy_params.rsi_ceiling
            or close < position.cost_basis * (1 - strategy_params.stop_loss)
            or close > position.cost_basis * (1 + strategy_params.take_profit)
            or symbol not in universe_set
        )
        if sell_signal:
            sells.append(symbol)

    buys = []
    if rebalance_now:
        for symbol in universe:
            if symbol in positions:
                continue
            row = price_lookup.get(symbol, {}).get(signal_date)
            if row is None:
                continue
            close = float(row["close_adj"])
            sar = float(row.get("sar", close))
            rsi = float(row.get("rsi", 50.0))
            volume_ratio = float(row.get("volume_ratio", 0.0))
            if close > sar and volume_ratio > strategy_params.volume_threshold and rsi < strategy_params.rsi_ceiling:
                buys.append((symbol, float(row.get("signal_strength", 0.0))))
        buys.sort(key=lambda item: (-item[1], item[0]))

    return PendingOrders(signal_date=signal_date, sells=sells, buys=[symbol for symbol, _ in buys])


def _portfolio_value(
    cash: float,
    positions: Mapping[str, Position],
    price_lookup: Mapping[str, Mapping[str, pd.Series]],
    trade_date: str,
) -> float:
    value = cash
    for symbol, position in positions.items():
        row = price_lookup.get(symbol, {}).get(trade_date)
        if row is not None and not pd.isna(row.get("close_adj")):
            value += position.shares * float(row["close_adj"])
        else:
            value += position.shares * position.cost_basis
    return float(value)


def _attach_benchmarks(
    portfolio: pd.DataFrame,
    benchmark: Optional[pd.DataFrame],
    equal_weight_benchmark: Optional[pd.DataFrame],
) -> pd.DataFrame:
    result = portfolio.copy()
    if benchmark is not None and not benchmark.empty:
        result = result.merge(benchmark[["trade_date", "benchmark_value"]], on="trade_date", how="left")
    if "benchmark_value" not in result:
        result["benchmark_value"] = result["portfolio_value"].iloc[0]
    result["benchmark_value"] = result["benchmark_value"].ffill().bfill()
    if equal_weight_benchmark is not None and not equal_weight_benchmark.empty:
        result = result.merge(equal_weight_benchmark[["trade_date", "equal_weight_value"]], on="trade_date", how="left")
        result["equal_weight_value"] = result["equal_weight_value"].ffill().bfill()
    return result


def _at_up_limit(row: pd.Series, raw_open: float) -> bool:
    limit = row.get("up_limit_adj")
    return limit is not None and not pd.isna(limit) and raw_open >= float(limit) * 0.999


def _at_down_limit(row: pd.Series, raw_open: float) -> bool:
    limit = row.get("down_limit_adj")
    return limit is not None and not pd.isna(limit) and raw_open <= float(limit) * 1.001


def _blocked_trade(signal_date: str, trade_date: str, symbol: str, action: str, reason: str) -> Dict[str, object]:
    return {
        "signal_date": signal_date,
        "trade_date": trade_date,
        "symbol": symbol,
        "action": action,
        "shares": 0,
        "price": pd.NA,
        "trade_value": 0.0,
        "commission": 0.0,
        "stamp_tax": 0.0,
        "return_pct": pd.NA,
        "holding_days": pd.NA,
        "reason": reason,
    }


def _calendar_days_between(start_date: str, end_date: str) -> int:
    try:
        start = pd.to_datetime(start_date, format="%Y%m%d")
        end = pd.to_datetime(end_date, format="%Y%m%d")
        return int((end - start).days)
    except Exception:
        return 0
