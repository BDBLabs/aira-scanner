import unittest
from pathlib import Path


class BrowserFallbackContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).parents[2] / "index.html").read_text(encoding="utf-8")
        start = cls.source.index("function buildHeuristicResult")
        end = cls.source.index("// ── RENDER RESULTS", start)
        cls.heuristic_source = cls.source[start:end]

    def test_fallback_is_presented_as_warning_and_partial(self):
        self.assertIn("Browser heuristics are partial.', 'warning'", self.source)
        self.assertIn("scan_completeness: 'partial'", self.heuristic_source)
        self.assertIn("upstream_failure_reason", self.source)

    def test_heuristic_fallback_never_synthesizes_pass(self):
        self.assertNotIn("result.checks[key] = 'PASS'", self.heuristic_source)
        self.assertIn("const evaluated = new Set();", self.heuristic_source)

    def test_multifile_fallback_preserves_artifact_paths(self):
        self.assertIn("artifact_manifest", self.heuristic_source)
        self.assertIn("file: String(file?.path || '')", self.heuristic_source)


if __name__ == "__main__":
    unittest.main()
