import json
import tempfile
import unittest
from pathlib import Path

from aira.comparison import build_suppression_matrix, load_scan


class ComparisonTests(unittest.TestCase):
    def test_build_suppression_matrix_counts_misses_by_check_and_boundary(self):
        static_scan = {
            "ai_failure_audit": {
                "exception_handling": "FAIL",
                "fallback_control": "FAIL",
            },
            "findings": [
                {
                    "check_id": "C03",
                    "severity": "HIGH",
                    "file": "service.py",
                    "line": 10,
                    "boundary_type": "exception_handler",
                    "semantic_fingerprint": "static-exception",
                    "fingerprint": "static-1",
                    "description": "Broad exception handler",
                },
                {
                    "check_id": "C04",
                    "severity": "LOW",
                    "file": "service.py",
                    "line": 40,
                    "boundary_type": "fallback_branch",
                    "semantic_fingerprint": "static-fallback",
                    "fingerprint": "static-2",
                    "description": "Fallback branch",
                },
            ],
        }
        model_scan = {
            "ai_failure_audit": {
                "exception_handling": "PASS",
                "fallback_control": "UNKNOWN",
            },
            "findings": [
                {
                    "check_id": "C03",
                    "severity": "MEDIUM",
                    "file": "service.py",
                    "line": 12,
                    "boundary_type": "exception_handler",
                    "semantic_fingerprint": "model-exception",
                    "fingerprint": "model-1",
                    "description": "Nearby exception concern",
                }
            ],
        }

        matrix = build_suppression_matrix(static_scan, model_scan, line_window=3)

        self.assertEqual(matrix["summary"]["static_findings"], 2)
        self.assertEqual(matrix["summary"]["model_findings"], 1)
        self.assertEqual(matrix["summary"]["matched_by_model"], 1)
        self.assertEqual(matrix["summary"]["missed_by_model"], 1)
        self.assertEqual(matrix["summary"]["static_fail_model_pass"], 1)
        self.assertEqual(matrix["summary"]["static_fail_model_unknown"], 1)
        self.assertEqual(matrix["by_check"]["C04"]["missed_by_model"], 1)
        self.assertEqual(matrix["by_boundary_type"]["fallback_branch"]["missed_by_model"], 1)
        self.assertEqual(matrix["matched_findings"][0]["match_type"], "same_check_line_window")

    def test_load_scan_accepts_standard_aira_json_wrapper(self):
        payload = {
            "aira_scan": {
                "ai_failure_audit": {"exception_handling": "PASS"},
                "findings": [],
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "scan.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            scan = load_scan(path)

        self.assertEqual(scan["ai_failure_audit"]["exception_handling"], "PASS")


if __name__ == "__main__":
    unittest.main()
