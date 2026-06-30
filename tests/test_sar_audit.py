import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from sar_project.audit import _write_source_inventory
from sar_project.dataset import ProjectPaths


class SarAuditTest(unittest.TestCase):
    def test_source_inventory_filters_price_cache_to_project_symbols(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = ProjectPaths(root)
            paths.ensure()
            (paths.interim_root / "symbols.json").write_text(json.dumps(["AAA"]), encoding="utf-8")
            frame = pd.DataFrame({"trade_date": ["20210101"], "close": [10.0]})
            frame.to_csv(paths.price_root / "AAA.csv", index=False)
            frame.to_csv(paths.price_root / "FIXTURE.csv", index=False)

            output = root / "inventory.csv"
            _write_source_inventory(paths, output)

            inventory = pd.read_csv(output)
            listed = inventory["relative_path"].tolist()
            self.assertIn("data/interim/sar_project/prices/AAA.csv", listed)
            self.assertNotIn("data/interim/sar_project/prices/FIXTURE.csv", listed)


if __name__ == "__main__":
    unittest.main()
