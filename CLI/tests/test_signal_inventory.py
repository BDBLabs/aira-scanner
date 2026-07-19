import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from aira.cli import main
from aira.scanner import AIRAScanner
from aira.signals import INVENTORY_SCHEMA_VERSION, inventory_errors


def _run_cli(argv):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with mock.patch("sys.argv", argv):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            with unittest.TestCase().assertRaises(SystemExit) as context:
                main()
    return context.exception.code, stdout.getvalue(), stderr.getvalue()


class SignalInventoryTests(unittest.TestCase):
    SOURCE = """def process(record):
    try:
        database.write(record)
    except ValueError as exc:
        logger.error("write failed")
        raise DomainError("write failed") from exc
    return {"status": "ok", "success": True}
"""

    def test_python_inventory_emits_exact_observations_without_risk_checks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "service.py"
            path.write_text(self.SOURCE, encoding="utf-8")

            inventory = inventory_errors(path)

        self.assertEqual(inventory["schema_version"], INVENTORY_SCHEMA_VERSION)
        self.assertEqual(inventory["summary"]["artifacts_analyzed"], 1)
        self.assertEqual(inventory["artifacts"][0]["status"], "analyzed")
        self.assertTrue(inventory["artifacts"][0]["structural"])
        kinds = {signal["kind"] for signal in inventory["signals"]}
        self.assertTrue({"handler", "raise", "return", "log", "side_effect"}.issubset(kinds))
        for signal in inventory["signals"]:
            self.assertEqual(signal["artifact"], "service.py")
            self.assertRegex(signal["signal_id"], r"^sig-[a-f0-9]{24}$")
            self.assertGreaterEqual(signal["region"]["start_line"], 1)
            self.assertIn("hash", signal["evidence"])
            self.assertNotIn("check_id", signal)

        raised = next(signal for signal in inventory["signals"] if signal["kind"] == "raise")
        self.assertEqual(raised["error_identity"]["type"], "DomainError")
        self.assertTrue(raised["error_identity"]["preserves_cause"])
        returned = next(signal for signal in inventory["signals"] if signal["kind"] == "return")
        self.assertEqual(returned["outcome"]["success_state"], "success")

    def test_signal_ids_survive_whitespace_and_line_shift_mutations(self):
        with tempfile.TemporaryDirectory() as left_dir, tempfile.TemporaryDirectory() as right_dir:
            left = Path(left_dir) / "service.py"
            right = Path(right_dir) / "service.py"
            left.write_text(self.SOURCE, encoding="utf-8")
            right.write_text("\n\n" + self.SOURCE.replace("try:\n", "try:  \n"), encoding="utf-8")

            first = inventory_errors(left)
            second = inventory_errors(right)

        first_ids = {(item["kind"], item["signal_id"]) for item in first["signals"]}
        second_ids = {(item["kind"], item["signal_id"]) for item in second["signals"]}
        self.assertEqual(first_ids, second_ids)
        self.assertEqual(
            [item["region"]["start_line"] for item in first["signals"]],
            [item["region"]["start_line"] - 2 for item in second["signals"]],
        )

    def test_python_parser_failure_is_an_explicit_signal_and_failed_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "broken.py"
            path.write_text("def broken(:\n", encoding="utf-8")

            inventory = inventory_errors(path)

        self.assertEqual(inventory["summary"]["artifacts_failed"], 1)
        self.assertEqual(inventory["artifacts"][0]["status"], "failed")
        self.assertEqual(inventory["signals"][0]["kind"], "parser_error")
        self.assertEqual(inventory["signals"][0]["error_identity"]["type"], "SyntaxError")

    def test_javascript_parser_capability_is_never_silent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "service.ts"
            path.write_text(
                "interface Item { id: string }\n"
                "export function load() { try { save(); } catch (err) { console.error(err); return false; } }\n",
                encoding="utf-8",
            )

            inventory = inventory_errors(path)

        artifact = inventory["artifacts"][0]
        self.assertIn(artifact["status"], {"analyzed", "partial"})
        self.assertIn("structural", artifact)
        if artifact["status"] == "partial":
            self.assertFalse(artifact["structural"])
            self.assertTrue(artifact["limitations"])
            self.assertTrue(any(item["kind"].startswith("parser_") for item in inventory["signals"]))

    def test_tree_sitter_recovery_nodes_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "broken.js"
            path.write_text("function broken( { return true; }\n", encoding="utf-8")

            inventory = inventory_errors(path)

        artifact = inventory["artifacts"][0]
        self.assertEqual(artifact["parser"], "tree_sitter")
        self.assertEqual(artifact["status"], "partial")
        self.assertTrue(artifact["structural"])
        self.assertTrue(any(item["kind"] in {"parser_error", "parser_missing"} for item in inventory["signals"]))

    def test_cli_inventory_and_scan_attachment_do_not_change_check_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "safe.py"
            path.write_text("def value():\n    return None\n", encoding="utf-8")
            baseline = AIRAScanner(str(path)).scan()

            code, stdout, stderr = _run_cli(["aira", "inventory-errors", str(path), "--output", "json"])
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            inventory_payload = json.loads(stdout)
            self.assertEqual(inventory_payload["schema_version"], INVENTORY_SCHEMA_VERSION)

            code, stdout, stderr = _run_cli([
                "aira", "scan", str(path), "--output", "json", "--include-signal-inventory",
            ])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)["aira_scan"]
        self.assertEqual(payload["ai_failure_audit"], baseline.check_results)
        self.assertEqual(payload["summary"], baseline.summary)
        self.assertIn("signal_inventory", payload["metadata"])


if __name__ == "__main__":
    unittest.main()
