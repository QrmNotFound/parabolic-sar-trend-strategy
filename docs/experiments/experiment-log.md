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

## 2026-06-30 Stage-2 Fixed Ablation

| Item | Value |
| --- | --- |
| Status | exploratory |
| Baseline | `baseline-v2` / `E0_baseline` |
| Scope | Fixed E0-E7 ablation only; no new parameter search |
| Modules | M1 CSI 300 market filter, M2 ATR trailing stop, M3 inverse-volatility sizing |
| Output | `docs/sar_project/stage2_ablation_results.csv` |
| Verification | `PYTHONPATH=src python3 -m unittest discover -s tests`; `PYTHONPATH=src python3 -m sar_project.pipeline ablate` |

### Historical Validation Snapshot

| Experiment | Modules | Total return | Excess vs CSI 300 | Max drawdown | Average exposure | Average positions |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| E0 | Baseline V2 | -9.92% | 2.19% | -40.25% | 41.44% | 7.80 |
| E1 | M1 | -2.71% | 9.39% | -11.57% | 15.98% | 4.07 |
| E2 | M2 | -7.81% | 4.30% | -34.26% | 35.02% | 6.56 |
| E3 | M3 | -1.49% | 10.62% | -34.40% | 43.14% | 7.61 |
| E4 | M1+M2 | -5.01% | 7.10% | -11.85% | 12.89% | 3.30 |
| E5 | M1+M3 | -1.40% | 10.70% | -9.36% | 16.44% | 3.82 |
| E6 | M2+M3 | -2.11% | 10.00% | -30.77% | 36.04% | 6.42 |
| E7 | M1+M2+M3 | -3.48% | 8.63% | -9.68% | 13.34% | 3.15 |

### Interpretation

M1 materially reduces drawdown but also reduces exposure and average positions, so it should not be used to claim improvement without an exposure floor. M3 is the cleanest exploratory improvement because it improves historical validation return while keeping exposure close to Baseline V2. None of the E0-E7 variants is a stable profitable strategy, and 2021-2025 remains historical validation rather than a clean blind test.
