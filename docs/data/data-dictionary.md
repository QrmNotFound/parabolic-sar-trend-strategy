# Data Dictionary

## Market Data

| Field | Meaning | Main Use |
| --- | --- | --- |
| `ts_code` | Security code | Stock and index identifier |
| `trade_date` | Trading date in `YYYYMMDD` | Dataset join key |
| `open`, `high`, `low`, `close` | Raw OHLC prices | Execution, valuation and limit checks |
| `vol`, `amount` | Trading volume and amount | Liquidity context and volume ratio |
| `adj_factor` | Adjustment factor | Adjusted price construction |
| `up_limit`, `down_limit` | Raw daily price limits | Buy/sell execution blocking |
| `open_adj`, `high_adj`, `low_adj`, `close_adj` | Adjusted OHLC prices | SAR, RSI and signal calculations |
| `up_limit_adj`, `down_limit_adj` | Adjusted limit prices | Offline fallback and diagnostics |

## Signals

| Field | Meaning |
| --- | --- |
| `sar` | Parabolic SAR value calculated from adjusted high/low |
| `ma60` | Rolling moving average of adjusted close, currently used for diagnostics |
| `atr20` | Rolling average true range, using raw OHLC when available and adjusted OHLC as fallback |
| `rsi` | 14-day RSI calculated from adjusted close |
| `volume_ratio` | Current volume divided by rolling 20-day average volume |
| `signal_strength` | Ranking score used to order buy candidates |

## Stage-2 Ablation

| Field | Meaning |
| --- | --- |
| `experiment` | Fixed ablation id from `E0_baseline` to `E7_all_modules` |
| `period` | `sample_in` or `historical_validation` |
| `use_market_filter` | Whether the CSI 300 moving-average market filter is enabled |
| `use_atr_trailing_stop` | Whether the ATR trailing stop module is enabled |
| `use_inverse_volatility_sizing` | Whether new buys use inverse-volatility cash allocation |

## Portfolio And Trades

| Field | Meaning |
| --- | --- |
| `portfolio_value` | Daily cash plus marked-to-market holdings |
| `cash` | Remaining cash after executions |
| `positions_count` | Number of held stocks |
| `turnover` | Daily traded value divided by portfolio value |
| `benchmark_value` | CSI 300 price-index benchmark value |
| `equal_weight_value` | Dynamic top-50 equal-weight benchmark value |
| `signal_date` | Date when the signal is formed after close |
| `trade_date` | Next trading date used for execution |
| `action` | `buy`, `sell`, `blocked_buy` or `blocked_sell` |
| `shares` | Executed shares, rounded to 100-share board lots for buys |
| `raw_open` | Raw next-day open price used before slippage |
| `execution_price` | Slippage-adjusted raw execution price |
| `price` | Slippage-adjusted raw execution price |
| `commission`, `stamp_tax` | Transaction costs |
| `slippage_cost` | Estimated one-way slippage amount |
| `realized_pnl`, `return_pct` | Sell-side realized PnL and round-trip return |
| `holding_days` | Calendar days between entry and exit |
| `entry_reason`, `exit_reason` | Explicit audit reasons for entry and exit where applicable |
| `inferred_reason` | Audit-layer inferred buy/sell/block reason |
