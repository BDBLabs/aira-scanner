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

    def test_one_model_finding_cannot_match_two_static_findings(self):
        static_scan = {
            "findings": [
                {
                    "check_id": "C03",
                    "file": "src/service.py",
                    "line": 10,
                    "boundary_type": "exception_handler",
                    "semantic_fingerprint": "same-signal",
                },
                {
                    "check_id": "C03",
                    "file": "src/service.py",
                    "line": 11,
                    "boundary_type": "exception_handler",
                    "semantic_fingerprint": "same-signal",
                },
            ]
        }
        model_scan = {
            "findings": [
                {
                    "check_id": "C03",
                    "file": "src/service.py",
                    "line": 10,
                    "boundary_type": "exception_handler",
                    "semantic_fingerprint": "same-signal",
                }
            ]
        }

        matrix = build_suppression_matrix(static_scan, model_scan)

        self.assertEqual(matrix["summary"]["matched_by_model"], 1)
        self.assertEqual(matrix["summary"]["missed_by_model"], 1)
        self.assertLessEqual(
            matrix["summary"]["matched_by_model"],
            matrix["summary"]["model_findings"],
        )
        self.assertTrue(matrix["invariants"]["one_to_one_model_matching"])

    def test_identical_basenames_in_different_directories_do_not_match(self):
        static_scan = {
            "findings": [
                {
                    "check_id": "C03",
                    "file": "src/a/index.py",
                    "line": 20,
                    "boundary_type": "exception_handler",
                    "semantic_fingerprint": "static-signal",
                }
            ]
        }
        model_scan = {
            "findings": [
                {
                    "check_id": "C03",
                    "file": "src/b/index.py",
                    "line": 20,
                    "boundary_type": "exception_handler",
                    "semantic_fingerprint": "model-signal",
                }
            ]
        }

        matrix = build_suppression_matrix(static_scan, model_scan)

        self.assertEqual(matrix["summary"]["matched_by_model"], 0)
        self.assertEqual(matrix["summary"]["missed_by_model"], 1)
        self.assertEqual(matrix["summary"]["model_only_findings"], 1)

    def test_semantic_fingerprint_requires_same_artifact(self):
        static_scan = {
            "findings": [
                {
                    "check_id": "C03",
                    "file": "src/first.py",
                    "line": 8,
                    "boundary_type": "exception_handler",
                    "semantic_fingerprint": "shared-semantic-fingerprint",
                }
            ]
        }
        model_scan = {
            "findings": [
                {
                    "check_id": "C03",
                    "file": "src/second.py",
                    "line": 8,
                    "boundary_type": "exception_handler",
                    "semantic_fingerprint": "shared-semantic-fingerprint",
                }
            ]
        }

        matrix = build_suppression_matrix(static_scan, model_scan)

        self.assertEqual(matrix["summary"]["matched_by_model"], 0)
        self.assertEqual(matrix["summary"]["missed_by_model"], 1)

    def test_noncanonical_artifact_paths_are_never_matched(self):
        static_scan = {
            "findings": [
                {
                    "check_id": "C03",
                    "file": "../outside.py",
                    "line": 8,
                    "boundary_type": "exception_handler",
                    "semantic_fingerprint": "shared-semantic-fingerprint",
                }
            ]
        }
        model_scan = {
            "findings": [
                {
                    "check_id": "C03",
                    "file": "../outside.py",
                    "line": 8,
                    "boundary_type": "exception_handler",
                    "semantic_fingerprint": "shared-semantic-fingerprint",
                }
            ]
        }

        matrix = build_suppression_matrix(static_scan, model_scan)

        self.assertEqual(matrix["summary"]["matched_by_model"], 0)

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
