import json
import tempfile
import unittest
from pathlib import Path

from sar_project.pipeline import main


class SarPipelineIntegrationTest(unittest.TestCase):
    def test_offline_pipeline_generates_processed_outputs_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            main(["all", "--root", str(root), "--offline-ok"])

            processed = root / "data" / "processed" / "sar_project"
            docs = root / "docs" / "sar_project"
            self.assertTrue((processed / "optimization_results.csv").exists())
            self.assertTrue((processed / "portfolio_test.csv").exists())
            self.assertTrue((processed / "trades_test.csv").exists())
            self.assertTrue((docs / "sar_project_report.md").exists())
            self.assertTrue((docs / "sar_project_report.pdf").exists())
            audit = docs / "audit"
            self.assertTrue((audit / "portfolio_sample_out.csv").exists())
            self.assertTrue((audit / "trade_ledger_sample_out.csv").exists())
            self.assertTrue((audit / "round_trip_trades_sample_out.csv").exists())
            self.assertTrue((audit / "optimization_results_sample_in.csv").exists())
            self.assertTrue((audit / "best_params.json").exists())
            self.assertTrue((audit / "README.md").exists())
            self.assertTrue((audit / "data_coverage.csv").exists())
            self.assertTrue((audit / "market_data_used.csv.gz").exists())
            self.assertTrue((audit / "source_data_inventory.csv").exists())
            self.assertTrue((audit / "raw_snapshot_manifest.csv").exists())
            self.assertTrue((audit / "audit_manifest.csv").exists())

            metrics = json.loads((processed / "metrics_test.json").read_text(encoding="utf-8"))
            self.assertIn("trade_win_rate", metrics)
            self.assertIn("positive_day_ratio", metrics)

            ledger = (audit / "trade_ledger_sample_out.csv").read_text(encoding="utf-8")
            self.assertIn("signal_close_adj", ledger)
            self.assertIn("signal_sar", ledger)
            self.assertIn("raw_open", ledger)
            self.assertIn("execution_price", ledger)
            self.assertIn("slippage_cost", ledger)
            self.assertIn("entry_reason", ledger)
            self.assertIn("exit_reason", ledger)
            self.assertIn("realized_pnl", ledger)
            round_trips = (audit / "round_trip_trades_sample_out.csv").read_text(encoding="utf-8")
            self.assertIn("entry_trade_date", round_trips)
            self.assertIn("exit_trade_date", round_trips)
            manifest = (audit / "audit_manifest.csv").read_text(encoding="utf-8")
            self.assertIn("trade_ledger_sample_out.csv", manifest)
            self.assertIn("sha256", manifest)


if __name__ == "__main__":
    unittest.main()
