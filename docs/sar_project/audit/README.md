# SAR Audit Attachments

This directory contains commit-friendly audit outputs for the SAR baseline and report.

| File | Purpose |
| --- | --- |
| `trade_ledger_sample_out.csv` | All historical-validation executions and blocked orders with signal and execution context |
| `round_trip_trades_sample_out.csv` | Buy/sell matched trade rounds under the one-position-per-symbol assumption |
| `portfolio_sample_out.csv` | Daily portfolio value, cash, position count and benchmark values |
| `optimization_results_sample_in.csv` | Real sample-in backtest result for every parameter combination |
| `best_params.json` | Parameters selected from the sample-in period |
| `data_coverage.csv` | Expected, cached and missing symbols |
| `source_data_inventory.csv` | Local cache file metadata and SHA-256 hashes |
| `raw_snapshot_manifest.csv` | Raw provider snapshot manifest without credentials |
| `audit_manifest.csv` | SHA-256 hashes for the audit attachments |

Raw provider data and credentials are not committed. Market data extracts should be checked against the data provider's redistribution rules before public release.
