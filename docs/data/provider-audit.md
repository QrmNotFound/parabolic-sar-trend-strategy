# Data Provider Audit

## SAR Project

| Item | Value |
| --- | --- |
| Project | SAR A-share trend-following backtest |
| Provider path | tinyshare proxy for Tushare Pro |
| Data period | 2016-01-01 to 2025-12-31 |
| Local cache | `data/raw/tinyshare/`, `data/interim/sar_project/` |
| Credential policy | Token must be supplied through `.env` or environment variables only |
| Git policy | `.env`, API tokens, raw snapshots and large cache outputs are not committed |
| Current coverage | 142 historical top-50 CSI 300 names expected, 140 cached, 2 missing |
| Missing symbols | `601127.SH`, `601336.SH` |
| Audit status | exploratory, reproducible from local cache |

## Interfaces

| Interface | Use | Key Parameters | Saved Output |
| --- | --- | --- | --- |
| `trade_cal` | A-share trading calendar | `start_date`, `end_date` | `data/interim/sar_project/trade_calendar.csv` |
| `index_weight` | Monthly CSI 300 constituents and weights | `index_code=000300.SH`, date range | `data/interim/sar_project/index_weight_top50.csv` |
| `index_daily` | CSI 300 benchmark prices | `ts_code=000300.SH`, date range | `data/interim/sar_project/index_daily.csv` |
| `daily` | Stock OHLCV data | `ts_code`, date range | `data/interim/sar_project/prices/*.csv` |
| `adj_factor` | Adjustment factors | `ts_code`, date range | merged into price cache |
| `stk_limit` | Daily up/down limit prices | `ts_code`, date range | merged into price cache |

## Known Limits

- The project uses monthly historical CSI 300 top-50 weights, not the full historical constituent universe.
- Two symbols in the union stock pool are missing from the current local cache and are disclosed in `docs/sar_project/data_coverage.csv`.
- Raw API response snapshots are intentionally excluded from GitHub; commit-friendly audit extracts are published under `docs/sar_project/audit/`.
- Signal calculations use adjusted prices; execution, cash accounting, board-lot sizing, limit checks and valuation use raw prices when available.
- Transaction costs include 0.03% commission with a 5 CNY minimum, 0.10% sell-side stamp tax and 0.05% one-way slippage.
