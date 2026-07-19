import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aira.llm import LLMConfig
from aira.scanner import AIRAScanner


class StaticScanIntegrityTests(unittest.TestCase):
    def test_malformed_python_is_failed_and_cannot_produce_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "broken.py"
            target.write_text("def broken(:\n    pass\n", encoding="utf-8")

            result = AIRAScanner(str(target)).scan(mode="static")

        self.assertEqual(result.summary["files_discovered"], 1)
        self.assertEqual(result.summary["files_scanned"], 0)
        self.assertEqual(result.summary["files_analyzed"], 0)
        self.assertEqual(result.summary["files_partial"], 0)
        self.assertEqual(result.summary["files_failed"], 1)
        self.assertEqual(result.summary["scan_completeness"], "failed")
        self.assertEqual(result.summary["checks_passed"], 0)
        self.assertEqual(result.summary["checks_unknown"], 15)
        self.assertTrue(all(status == "UNKNOWN" for status in result.check_results.values()))
        self.assertEqual(result.metadata["artifacts"][0]["status"], "failed")

    def test_one_failed_artifact_makes_unproven_aggregate_checks_unknown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "safe.py").write_text("value = 1\n", encoding="utf-8")
            (root / "broken.py").write_text("def broken(:\n", encoding="utf-8")

            result = AIRAScanner(str(root)).scan(mode="static")

        self.assertEqual(result.summary["files_discovered"], 2)
        self.assertEqual(result.summary["files_analyzed"], 1)
        self.assertEqual(result.summary["files_failed"], 1)
        self.assertEqual(result.summary["scan_completeness"], "partial")
        self.assertEqual(result.summary["checks_passed"], 0)

    def test_typescript_lexical_fallback_is_partial_not_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "types.ts"
            target.write_text(
                "interface User { id: string }\nconst user: User = { id: '1' };\n",
                encoding="utf-8",
            )

            result = AIRAScanner(str(target)).scan(mode="static")

        self.assertEqual(result.summary["files_discovered"], 1)
        self.assertEqual(result.summary["files_scanned"], 0)
        self.assertEqual(result.summary["files_analyzed"], 0)
        self.assertEqual(result.summary["files_partial"], 1)
        self.assertEqual(result.summary["scan_completeness"], "partial")
        self.assertEqual(result.summary["checks_passed"], 0)
        self.assertEqual(result.metadata["artifacts"][0]["parser"], "lexical_fallback")

    def test_read_failure_is_failed_and_cannot_produce_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "unreadable.py"
            target.write_text("value = 1\n", encoding="utf-8")

            with mock.patch(
                "aira.checkers.python_checker.Path.read_text",
                side_effect=OSError("denied"),
            ):
                result = AIRAScanner(str(target)).scan(mode="static")

        self.assertEqual(result.summary["files_failed"], 1)
        self.assertEqual(result.summary["files_analyzed"], 0)
        self.assertEqual(result.summary["checks_passed"], 0)
        self.assertEqual(result.findings[0]["check_id"], "SCANNER")

    def test_test_analysis_failure_only_withholds_c14_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "test_app.py"
            target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

            with mock.patch(
                "aira.checkers.test_coverage_checker.analyze_test_file",
                side_effect=OSError("denied"),
            ):
                result = AIRAScanner(str(target.parent)).scan(mode="static")

        self.assertEqual(result.summary["files_analyzed"], 1)
        self.assertEqual(result.summary["scan_completeness"], "complete")
        self.assertEqual(result.check_results["test_coverage_symmetry"], "UNKNOWN")
        self.assertEqual(result.check_results["success_integrity"], "PASS")
        self.assertIn("test_coverage_symmetry", result.metadata["capability_gaps"])


class LLMScanIntegrityTests(unittest.TestCase):
    @staticmethod
    def _llm_response(findings):
        return {
            "provider": "openai-compatible",
            "model": "test-model",
            "text": json.dumps({"ai_failure_audit": {}, "findings": findings}),
        }

    def test_model_paths_outside_scan_manifest_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "allowed.py").write_text("value = 1\n", encoding="utf-8")
            response = self._llm_response([
                {
                    "check_id": "C03",
                    "severity": "HIGH",
                    "file": "../outside.py",
                    "line": 1,
                    "description": "Traversal path",
                },
                {
                    "check_id": "C03",
                    "severity": "HIGH",
                    "file": str(root / "allowed.py"),
                    "line": 1,
                    "description": "Absolute path",
                },
            ])

            with mock.patch("aira.scanner.run_llm_json_audit", return_value=response):
                result = AIRAScanner(str(root)).scan(
                    mode="llm",
                    llm_config=LLMConfig(provider="openai-compatible", model="test-model"),
                )

        self.assertEqual(result.findings, [])
        self.assertEqual(result.metadata["rejected_findings_count"], 2)
        self.assertEqual(
            {item["reason"] for item in result.metadata["rejected_findings"]},
            {"noncanonical_artifact_path"},
        )

    def test_model_finding_must_name_exact_manifest_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src").mkdir()
            (root / "src" / "service.py").write_text("value = 1\n", encoding="utf-8")
            response = self._llm_response([
                {
                    "check_id": "C03",
                    "severity": "HIGH",
                    "file": "service.py",
                    "line": 1,
                    "description": "Basename is ambiguous identity",
                },
                {
                    "check_id": "C03",
                    "severity": "HIGH",
                    "file": "src/service.py",
                    "line": 1,
                    "description": "Exact manifest artifact",
                },
            ])

            with mock.patch("aira.scanner.run_llm_json_audit", return_value=response):
                result = AIRAScanner(str(root)).scan(
                    mode="llm",
                    llm_config=LLMConfig(provider="openai-compatible", model="test-model"),
                )

        self.assertEqual(len(result.findings), 1)
        self.assertEqual(result.findings[0]["file"], "src/service.py")
        self.assertEqual(result.metadata["rejected_findings_count"], 1)
        self.assertEqual(result.metadata["rejected_findings"][0]["reason"], "artifact_not_in_manifest")

    def test_truncated_llm_input_cannot_produce_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "one.py").write_text("value = '" + ("x" * 200) + "'\n", encoding="utf-8")
            (root / "two.py").write_text("value = 2\n", encoding="utf-8")
            response = {
                "provider": "openai-compatible",
                "model": "test-model",
                "text": json.dumps(
                    {
                        "ai_failure_audit": {
                            "success_integrity": "PASS",
                            "exception_handling": "PASS",
                        },
                        "findings": [],
                    }
                ),
            }

            with mock.patch("aira.scanner.run_llm_json_audit", return_value=response):
                result = AIRAScanner(str(root)).scan(
                    mode="llm",
                    llm_config=LLMConfig(
                        provider="openai-compatible",
                        model="test-model",
                        max_context_chars=80,
                    ),
                )

        self.assertEqual(result.summary["files_discovered"], 2)
        self.assertEqual(result.summary["files_scanned"], 0)
        self.assertEqual(result.summary["files_analyzed"], 0)
        self.assertEqual(result.summary["files_partial"], 1)
        self.assertEqual(result.summary["files_omitted"], 1)
        self.assertEqual(result.summary["scan_completeness"], "partial")
        self.assertEqual(result.check_results["success_integrity"], "UNKNOWN")
        self.assertEqual(result.check_results["exception_handling"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
