import unittest

from aira.deterministic_scan import scan_inline_source, scan_inline_sources

try:
    import esprima  # type: ignore  # noqa: F401
except ImportError:  # pragma: no cover - optional parser dependency
    esprima = None


class DeterministicScanTests(unittest.TestCase):
    def test_python_deterministic_scan_is_parser_backed(self):
        code = (
            "def save_record(db, record):\n"
            "    try:\n"
            "        write_audit(record)\n"
            "        db.insert(record)\n"
            "    except Exception:\n"
            "        return True\n"
        )

        result = scan_inline_source(code, "python")

        self.assertTrue(result["meta"]["parser_backed"])
        self.assertEqual(result["checks"]["success_integrity"], "FAIL")
        self.assertEqual(result["checks"]["exception_handling"], "FAIL")
        self.assertEqual(result["checks"]["audit_integrity"], "FAIL")

    def test_python_deterministic_scan_is_repeatable(self):
        code = (
            "def score_record(model, payload):\n"
            "    return model.predict(payload, temperature=0.7)\n"
        )

        first = scan_inline_source(code, "python")
        second = scan_inline_source(code, "python")

        self.assertEqual(first, second)
        self.assertEqual(first["checks"]["determinism"], "FAIL")

    def test_python_findings_include_location_metadata(self):
        code = (
            "def save_record(db, record):\n"
            "    try:\n"
            "        db.insert(record)\n"
            "    except Exception:\n"
            "        return True\n"
        )

        result = scan_inline_source(code, "python")
        finding = next(item for item in result["findings"] if item["check_id"] == "C01")

        self.assertEqual(finding["boundary_type"], "exception_handler")
        self.assertEqual(finding["context"]["parser"], "python_ast")
        self.assertEqual(finding["context"]["enclosing_function"], "save_record")
        self.assertIn("ExceptHandler", finding["context"]["ast_path"])
        self.assertEqual(finding["fingerprint_version"], "aira-finding-v1")
        self.assertTrue(finding["fingerprint"])
        self.assertTrue(finding["semantic_fingerprint"])
        self.assertTrue(finding["location_fingerprint"])

    def test_javascript_decimal_temperature_is_flagged(self):
        result = scan_inline_source(
            "const result = client.chat({ temperature: 0.7, messages });\n",
            "javascript",
        )

        self.assertEqual(result["checks"]["determinism"], "FAIL")

    @unittest.skipUnless(esprima is not None, "esprima parser is not installed")
    def test_javascript_deterministic_scan_uses_ast_rules_when_available(self):
        code = (
            "async function initSystem() {\n"
            "  try {\n"
            "    writeAudit(event);\n"
            "  } catch (e) {\n"
            "    console.error(e);\n"
            "    return true;\n"
            "  }\n"
            "}\n"
        )

        result = scan_inline_source(code, "javascript")

        self.assertTrue(result["meta"]["parser_backed"])
        self.assertEqual(result["checks"]["exception_handling"], "FAIL")
        self.assertEqual(result["checks"]["success_integrity"], "FAIL")
        self.assertEqual(result["checks"]["audit_integrity"], "FAIL")
        self.assertEqual(result["checks"]["startup_integrity"], "FAIL")

    def test_unsupported_language_is_rejected(self):
        with self.assertRaises(ValueError):
            scan_inline_source("print('hello')", "ruby")

    def test_javascript_language_aliases_use_shared_static_scanner(self):
        for lang in ("js", "jsx", "mjs", "cjs"):
            with self.subTest(lang=lang):
                result = scan_inline_source("try { writeAudit(event); } catch (e) { return true; }", lang)
                self.assertEqual(result["meta"]["language"], "javascript")
                self.assertEqual(result["checks"]["audit_integrity"], "FAIL")
                self.assertEqual(result["summary"]["files_discovered"], 1)
                if result["meta"]["parser_backed"]:
                    self.assertEqual(result["summary"]["files_scanned"], 1)
                else:
                    self.assertEqual(result["summary"]["files_scanned"], 0)
                    self.assertEqual(result["summary"]["files_partial"], 1)

    def test_multi_file_deterministic_scan_matches_directory_style_behavior(self):
        result = scan_inline_sources([
            {
                "path": "src/service.py",
                "code": (
                    "def save_record(db, record):\n"
                    "    try:\n"
                    "        write_audit(record)\n"
                    "        db.insert(record)\n"
                    "    except Exception:\n"
                    "        return True\n"
                ),
            },
            {
                "path": "tests/test_service.py",
                "code": (
                    "def test_save_record_handles_failure():\n"
                    "    assert save_record(None, None) is True\n"
                ),
            },
        ])

        self.assertEqual(result["summary"]["files_scanned"], 2)
        self.assertGreater(result["summary"]["total"], 0)
        self.assertEqual(result["checks"]["success_integrity"], "FAIL")
        self.assertEqual(result["checks"]["audit_integrity"], "FAIL")
        self.assertTrue(any(finding["file"] == "src/service.py" for finding in result["findings"]))
        self.assertTrue(any(
            artifact["path"] == "tests/test_service.py"
            for artifact in result["meta"]["artifact_manifest"]
        ))
        self.assertIn("logic_consistency (C07)", result["summary"]["requires_human_review"])


if __name__ == "__main__":
    unittest.main()
