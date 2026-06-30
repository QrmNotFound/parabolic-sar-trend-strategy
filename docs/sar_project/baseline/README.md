# Baseline V2

This directory freezes the corrected baseline after fixing execution price semantics, missing-close valuation, minimum commission, and audit fields.

- Signals use adjusted prices.
- Execution, board-lot sizing, limit checks, costs, and valuation use raw prices when available.
- Minimum commission is 5 CNY per trade.
- Strategy modules such as market filter, ATR trailing stop, and volatility sizing are not enabled yet.

These files are the comparison base for later ablation experiments and should not be overwritten by future pipeline runs.
