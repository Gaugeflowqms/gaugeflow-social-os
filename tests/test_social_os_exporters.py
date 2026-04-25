import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath("src"))

from gaugeflow_social_os.data import INITIATIVES, RITUAL_SLOTS, SIGNALS, TEAM_MEMBERS
from gaugeflow_social_os.exporters import export_initiatives_csv, export_plan_json, export_summary_markdown


class SocialOSExporterTests(unittest.TestCase):
    def test_exports_are_written(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            csv_path = base / "initiatives.csv"
            md_path = base / "summary.md"
            json_path = base / "plan.json"

            export_initiatives_csv(INITIATIVES, csv_path)
            export_summary_markdown(TEAM_MEMBERS, INITIATIVES, SIGNALS, RITUAL_SLOTS, md_path)
            export_plan_json(TEAM_MEMBERS, INITIATIVES, RITUAL_SLOTS, json_path)

            self.assertTrue(csv_path.exists())
            self.assertTrue(md_path.exists())
            self.assertTrue(json_path.exists())
            self.assertIn("GF-17-01", csv_path.read_text(encoding="utf-8"))
            self.assertIn("Critical Chain", md_path.read_text(encoding="utf-8"))
            self.assertIn("unplanned_initiatives", json_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
