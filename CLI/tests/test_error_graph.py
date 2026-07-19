import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from aira.cli import main
from aira.error_graph import GRAPH_SCHEMA_VERSION, error_graph_for_target
from aira.scanner import AIRAScanner
from aira.signals import inventory_errors


def _run_cli(argv):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with mock.patch("sys.argv", argv):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                main()
            except SystemExit as exc:
                return exc.code, stdout.getvalue(), stderr.getvalue()
    raise AssertionError("CLI did not exit")


class ErrorGraphTests(unittest.TestCase):
    PYTHON_SOURCE = """def low_level():
    raise IOError("offline")

def translate():
    try:
        low_level()
    except IOError as exc:
        raise DomainError("translated") from exc

def erase_cause():
    try:
        low_level()
    except IOError:
        raise DomainError("generic")

def api(record):
    try:
        low_level()
    except IOError:
        database.write(record)
        logger.error("offline")
        retry_operation()
        fallback_default()
        return {"status": "error", "status_code": 503}

def compensate(record):
    try:
        database.write(record)
    except IOError:
        transaction.rollback()
        raise
"""

    def test_python_graph_covers_error_flow_and_keeps_unresolved_calls_explicit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "service.py"
            path.write_text(self.PYTHON_SOURCE, encoding="utf-8")

            graph = error_graph_for_target(str(path))

        self.assertEqual(graph["schema_version"], GRAPH_SCHEMA_VERSION)
        edge_kinds = {edge["kind"] for edge in graph["edges"]}
        self.assertTrue({
            "contains", "catches", "sequence", "calls", "may_raise", "wraps",
            "drops_cause", "rethrows", "logs", "retries", "falls_back",
            "returns_status", "writes_before", "rolls_back",
        }.issubset(edge_kinds))
        self.assertGreater(graph["summary"]["unresolved_call_nodes"], 0)
        unresolved = [node for node in graph["nodes"] if node["type"] == "unresolved_call"]
        self.assertTrue(any(node["callee"] == "database.write" for node in unresolved))
        self.assertTrue(any(
            edge["kind"] == "calls" and edge["resolved"] and edge["attributes"].get("callee") == "low_level"
            for edge in graph["edges"]
        ))
        node_ids = {node["id"] for node in graph["nodes"]}
        for edge in graph["edges"]:
            self.assertIn(edge["source"], node_ids)
            self.assertIn(edge["target"], node_ids)
            self.assertTrue(edge["evidence"])
            self.assertRegex(edge["edge_id"], r"^edge-[a-f0-9]{24}$")

    def test_graph_generation_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "service.py"
            path.write_text(self.PYTHON_SOURCE, encoding="utf-8")

            first = error_graph_for_target(str(path))
            second = error_graph_for_target(str(path))

        self.assertEqual(first, second)

    def test_typescript_flow_is_structural(self):
        source = """interface Result { ok: boolean }
export function load(record: Result): boolean {
  try {
    load_remote(record)
  } catch (err) {
    database.persist(record)
    console.error(err)
    return false
  }
}
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "service.ts"
            path.write_text(source, encoding="utf-8")
            inventory = inventory_errors(path)
            graph = error_graph_for_target(str(path))

        artifact = inventory["artifacts"][0]
        self.assertEqual(artifact["parser"], "tree_sitter")
        self.assertEqual(artifact["status"], "analyzed")
        self.assertTrue(artifact["structural"])
        edge_kinds = {edge["kind"] for edge in graph["edges"]}
        self.assertTrue({"catches", "logs", "returns_status", "writes_before"}.issubset(edge_kinds))
        self.assertEqual(graph["parser_diagnostics"], [])

    def test_cli_graph_and_scan_attachment_do_not_change_canonical_result(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "service.py"
            path.write_text("def load():\n    return False\n", encoding="utf-8")
            baseline = AIRAScanner(str(path)).scan()

            code, stdout, stderr = _run_cli(["aira", "error-graph", str(path), "--output", "json"])
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(json.loads(stdout)["schema_version"], GRAPH_SCHEMA_VERSION)

            code, stdout, stderr = _run_cli([
                "aira", "scan", str(path), "--output", "json", "--include-error-graph",
            ])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)["aira_scan"]
        self.assertEqual(payload["ai_failure_audit"], baseline.check_results)
        self.assertEqual(payload["summary"], baseline.summary)
        self.assertIn("error_graph", payload["metadata"])
        self.assertNotIn("signal_inventory", payload["metadata"])


if __name__ == "__main__":
    unittest.main()
