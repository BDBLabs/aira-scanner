import json
import unittest
from pathlib import Path

from aira.scanner import AIRAScanner


class VersionedMeasurementBaselineTests(unittest.TestCase):
    def test_measurement_integrity_v1_fixture(self):
        fixture_root = Path(__file__).parent / "fixtures" / "measurement_integrity_v1"
        expected = json.loads((fixture_root / "expected.json").read_text(encoding="utf-8"))

        result = AIRAScanner(str(fixture_root / expected["artifact"])).scan()

        observed = [
            {
                "check_id": finding["check_id"],
                "line": finding["line"],
                "severity": finding["severity"],
            }
            for finding in result.findings
        ]
        self.assertEqual(observed, expected["findings"])
        self.assertEqual(result.summary["scan_completeness"], expected["scan_completeness"])
        observed_ids = {finding["check_id"] for finding in result.findings}
        self.assertTrue(observed_ids.isdisjoint(expected["must_not_find"]))


if __name__ == "__main__":
    unittest.main()
