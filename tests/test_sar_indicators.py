import unittest

import numpy as np
import pandas as pd

from sar_project.indicators import IndicatorParams, add_indicators, calculate_rsi, calculate_sar


class SarIndicatorTest(unittest.TestCase):
    def test_calculate_sar_is_deterministic_and_populates_values(self):
        frame = pd.DataFrame(
            {
                "high_adj": [10.0, 10.5, 11.0, 11.5, 12.0, 11.8, 11.4],
                "low_adj": [9.5, 9.8, 10.2, 10.7, 11.0, 10.9, 10.6],
                "close_adj": [9.8, 10.3, 10.8, 11.2, 11.6, 11.0, 10.8],
            }
        )

        first = calculate_sar(frame, acceleration=0.02, maximum=0.2)
        second = calculate_sar(frame, acceleration=0.02, maximum=0.2)

        self.assertTrue(first["sar"].iloc[1:].notna().any())
        pd.testing.assert_series_equal(first["sar"], second["sar"])

    def test_calculate_rsi_bounds_values_between_zero_and_one_hundred(self):
        close = pd.Series([10, 11, 10.5, 12, 11.8, 12.5, 13, 12.7, 13.2])

        rsi = calculate_rsi(close, window=3)

        valid = rsi.dropna()
        self.assertTrue(((valid >= 0) & (valid <= 100)).all())

    def test_add_indicators_handles_zero_volume_without_infinite_ratio(self):
        frame = pd.DataFrame(
            {
                "trade_date": ["20210101", "20210104", "20210105", "20210106", "20210107"],
                "open_adj": [10, 10, 10, 10, 10],
                "high_adj": [11, 11, 11, 11, 11],
                "low_adj": [9, 9, 9, 9, 9],
                "close_adj": [10, 10.2, 10.4, 10.1, 10.5],
                "vol": [0, 0, 0, 1000, 1200],
            }
        )

        enriched = add_indicators(frame, IndicatorParams(rsi_window=2, volume_window=2))

        self.assertIn("sar", enriched.columns)
        self.assertIn("rsi", enriched.columns)
        self.assertIn("volume_ratio", enriched.columns)
        finite_or_missing = np.isfinite(enriched["volume_ratio"].dropna())
        self.assertTrue(finite_or_missing.all())


if __name__ == "__main__":
    unittest.main()
