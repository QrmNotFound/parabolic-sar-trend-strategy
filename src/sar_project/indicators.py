"""Technical indicators for the SAR project."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class IndicatorParams:
    """Parameters for deterministic technical indicator calculation."""

    sar_acceleration: float = 0.02
    sar_maximum: float = 0.2
    rsi_window: int = 14
    volume_window: int = 20
    ma_window: int = 60
    atr_window: int = 20


def calculate_sar(frame: pd.DataFrame, acceleration: float = 0.02, maximum: float = 0.2) -> pd.DataFrame:
    """Calculate a simple parabolic SAR series from adjusted high/low columns."""

    required = {"high_adj", "low_adj"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing SAR columns: {sorted(missing)}")

    result = frame.copy()
    sar_values = np.full(len(result), np.nan)
    if len(result) < 2:
        result["sar"] = sar_values
        return result

    high = result["high_adj"].astype(float).to_numpy()
    low = result["low_adj"].astype(float).to_numpy()

    trend = 1
    extreme_point = high[0]
    sar = low[0]
    acceleration_factor = acceleration

    for index in range(1, len(result)):
        next_sar = sar + acceleration_factor * (extreme_point - sar)

        if trend == 1:
            if low[index] < next_sar:
                trend = -1
                next_sar = extreme_point
                extreme_point = low[index]
                acceleration_factor = acceleration
            else:
                if high[index] > extreme_point:
                    extreme_point = high[index]
                    acceleration_factor = min(acceleration_factor + acceleration, maximum)
        else:
            if high[index] > next_sar:
                trend = 1
                next_sar = extreme_point
                extreme_point = high[index]
                acceleration_factor = acceleration
            else:
                if low[index] < extreme_point:
                    extreme_point = low[index]
                    acceleration_factor = min(acceleration_factor + acceleration, maximum)

        sar_values[index] = next_sar
        sar = next_sar

    result["sar"] = sar_values
    return result


def calculate_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Calculate RSI with simple rolling average gains and losses."""

    delta = close.astype(float).diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=window, min_periods=window).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=window, min_periods=window).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0).clip(lower=0, upper=100)


def add_indicators(frame: pd.DataFrame, params: IndicatorParams) -> pd.DataFrame:
    """Return a price frame enriched with SAR, RSI, volume ratio, and signal strength."""

    required = {"close_adj", "high_adj", "low_adj", "vol"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing indicator columns: {sorted(missing)}")

    enriched = calculate_sar(frame, params.sar_acceleration, params.sar_maximum)
    enriched["ma60"] = enriched["close_adj"].astype(float).rolling(window=params.ma_window, min_periods=1).mean()
    enriched["atr20"] = _calculate_atr(enriched, params.atr_window)
    enriched["rsi"] = calculate_rsi(enriched["close_adj"], params.rsi_window)
    volume_ma = enriched["vol"].astype(float).rolling(window=params.volume_window, min_periods=1).mean()
    enriched["volume_ratio"] = enriched["vol"].astype(float) / volume_ma.replace(0, np.nan)
    enriched["volume_ratio"] = enriched["volume_ratio"].replace([np.inf, -np.inf], np.nan)
    enriched["signal_strength"] = 0.0
    return enriched


def _calculate_atr(frame: pd.DataFrame, window: int = 20) -> pd.Series:
    high = _price_series(frame, "high", "high_adj")
    low = _price_series(frame, "low", "low_adj")
    close = _price_series(frame, "close", "close_adj")
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window=window, min_periods=1).mean()


def _price_series(frame: pd.DataFrame, raw_column: str, adjusted_column: str) -> pd.Series:
    column = raw_column if raw_column in frame else adjusted_column
    return frame[column].astype(float)
