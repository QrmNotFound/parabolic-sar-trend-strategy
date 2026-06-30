# SAR Stage-2 Fixed Ablation Summary

## Purpose

Stage 2 compares three fixed modules against the frozen Baseline V2. It does not run a new open-ended parameter search and does not treat 2021-2025 as a clean blind test.

- M1: CSI 300 moving-average market filter.
- M2: ATR trailing stop.
- M3: inverse-volatility sizing for new buys.

## Historical Validation Results

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

## Readout

E3 is the cleanest candidate for further study because it improves historical validation return without lowering exposure below the Baseline V2 level. M1-heavy variants look better on drawdown, but they also hold much less equity exposure, so they should be treated as risk-reduction variants rather than clear alpha improvements.

No variant should be described as a stable profitable strategy. The credible wording is that fixed module ablation identified inverse-volatility sizing as a promising course-project extension, while true blind validation requires data after the code and parameters are frozen.
