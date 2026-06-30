# Experiment Log

## 2026-06-30 SAR Rebuild

| Item | Value |
| --- | --- |
| Status | exploratory |
| Code path | `src/sar_project/` |
| Data period | 2016-2025 |
| Sample-in | 2016-2020 |
| Historical validation | 2021-2025 |
| Universe | Monthly historical CSI 300 top-50 by index weight |
| Best parameters | `acceleration=0.003`, `maximum=0.10`, `volume_threshold=0.5`, `rsi_ceiling=100`, `max_positions=30`, `rebalance_interval=60`, `stop_loss=0.30`, `take_profit=10.0` |
| Execution semantics | Signals use adjusted prices; t+1 execution, costs, board-lot sizing, limit checks and valuation use raw prices when available |
| Cost semantics | 0.03% commission with 5 CNY minimum, 0.10% sell-side stamp tax, 0.05% one-way slippage |
| Verification | `PYTHONPATH=src python3 -m unittest discover -s tests`; `PYTHONPATH=src python3 -m sar_project.pipeline all --offline-ok`; `PYTHONPATH=src python3 -m sar_project.pipeline report` |

## Result Summary

| Metric | Sample-in | Historical validation |
| --- | ---: | ---: |
| Strategy total return | 19.58% | -9.92% |
| CSI 300 total return | 50.22% | -12.11% |
| Excess vs CSI 300 | -30.65% | 2.19% |
| Dynamic top-50 equal-weight return | not primary in optimizer | -8.19% |
| Max drawdown | -30.83% | -40.25% |
| Sharpe ratio | 0.05 | -0.37 |
| Average exposure | 46.95% | 41.44% |
| Trade win rate | 38.36% | 34.71% |
| Profit factor | 1.20 | 0.80 |

## Interpretation

The corrected Baseline V2 no longer supports a “stable profitable strategy” claim. It is slightly better than CSI 300 after costs, worse than the dynamic top-50 equal-weight benchmark, and has negative absolute return. It should be used as a course-level research and internship portfolio artifact, not as evidence of a deployable trading strategy. Later strategy modules must be evaluated against this frozen baseline without treating 2021-2025 as a clean blind test.
