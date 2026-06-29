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

            metrics = json.loads((processed / "metrics_test.json").read_text(encoding="utf-8"))
            self.assertIn("trade_win_rate", metrics)
            self.assertIn("positive_day_ratio", metrics)


if __name__ == "__main__":
    unittest.main()
