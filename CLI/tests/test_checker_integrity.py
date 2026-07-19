import tempfile
import unittest
from pathlib import Path

from aira.checkers.test_coverage_checker import analyze_test_file
from aira.scanner import AIRAScanner


def _findings_for(code: str, suffix: str, check_id: str):
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / f"sample{suffix}"
        target.write_text(code, encoding="utf-8")
        result = AIRAScanner(str(target)).scan(mode="static")
    return [finding for finding in result.findings if finding["check_id"] == check_id]


class SuccessIntegrityTests(unittest.TestCase):
    def test_python_error_shaped_return_is_not_c01_and_does_not_duplicate(self):
        findings = _findings_for(
            "def save():\n"
            "    try:\n"
            "        persist()\n"
            "    except Exception:\n"
            "        return {'status': 'error', 'success': False}\n",
            ".py",
            "C01",
        )

        self.assertEqual(findings, [])

    def test_python_success_dict_is_one_structural_c01_event(self):
        findings = _findings_for(
            "def save():\n"
            "    try:\n"
            "        persist()\n"
            "    except Exception:\n"
            "        return {'status': 'ok', 'success': True}\n",
            ".py",
            "C01",
        )

        self.assertEqual(len(findings), 1)

    def test_javascript_error_shaped_return_is_not_c01(self):
        findings = _findings_for(
            "function save() {\n"
            "  try { persist(); }\n"
            "  catch (error) {\n"
            "    return { status: 'error', success: false };\n"
            "  }\n"
            "}\n",
            ".js",
            "C01",
        )

        self.assertEqual(findings, [])


class BackgroundTaskTests(unittest.TestCase):
    def test_assigned_and_awaited_python_task_is_supervised(self):
        findings = _findings_for(
            "import asyncio\n"
            "async def run():\n"
            "    task = asyncio.create_task(work())\n"
            "    await task\n",
            ".py",
            "C08",
        )

        self.assertEqual(findings, [])

    def test_discarded_python_task_is_c08(self):
        findings = _findings_for(
            "import asyncio\n"
            "async def run():\n"
            "    asyncio.create_task(work())\n",
            ".py",
            "C08",
        )

        self.assertEqual(len(findings), 1)

    def test_assigned_but_never_awaited_python_task_is_c08(self):
        findings = _findings_for(
            "import asyncio\n"
            "async def run():\n"
            "    task = asyncio.create_task(work())\n"
            "    return task.done()\n",
            ".py",
            "C08",
        )

        self.assertEqual(len(findings), 1)

    def test_task_group_owned_task_is_supervised(self):
        findings = _findings_for(
            "import asyncio\n"
            "async def run():\n"
            "    async with asyncio.TaskGroup() as group:\n"
            "        group.create_task(work())\n",
            ".py",
            "C08",
        )

        self.assertEqual(findings, [])

    def test_promise_all_is_not_unsupervised_background_work(self):
        findings = _findings_for(
            "async function run() {\n"
            "  const values = await Promise.all([first(), second()]);\n"
            "  return values;\n"
            "}\n",
            ".js",
            "C08",
        )

        self.assertEqual(findings, [])


class TestCoverageClassificationTests(unittest.TestCase):
    def test_python_test_function_counts_once_even_with_multiple_assertions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "test_service.py"
            target.write_text(
                "def test_happy_path():\n"
                "    assert service()\n"
                "    assert service() == 1\n"
                "    assert service() is not None\n",
                encoding="utf-8",
            )

            report = analyze_test_file(str(target))

        self.assertEqual(report.total_tests, 1)
        self.assertEqual(report.happy_path_tests, 1)
        self.assertEqual(report.failure_path_tests, 0)
        self.assertEqual(report.unclassified_tests, 0)

    def test_python_failure_and_unclassified_tests_are_separate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "test_service.py"
            target.write_text(
                "import pytest\n"
                "def test_rejects_invalid_input():\n"
                "    with pytest.raises(ValueError):\n"
                "        service(None)\n"
                "\n"
                "def test_service_contract():\n"
                "    service()\n",
                encoding="utf-8",
            )

            report = analyze_test_file(str(target))

        self.assertEqual(report.total_tests, 2)
        self.assertEqual(report.happy_path_tests, 0)
        self.assertEqual(report.failure_path_tests, 1)
        self.assertEqual(report.unclassified_tests, 1)
        self.assertEqual(report.flagged_findings, [])

    def test_c14_language_describes_observed_surface_not_authorship(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "test_service.py"
            target.write_text("def test_success():\n    assert service()\n", encoding="utf-8")

            report = analyze_test_file(str(target))

        self.assertEqual(len(report.flagged_findings), 1)
        description = report.flagged_findings[0]["description"]
        self.assertIn("Observed test-surface asymmetry", description)
        self.assertNotIn("AI-generated", description)


class LexicalFalsePositiveTests(unittest.TestCase):
    def test_python_rule_literals_and_comments_do_not_trigger_lexical_checks(self):
        code = (
            "TEMPERATURE_PATTERN = r'temperature=0.7'\n"
            "ENV_PATTERN = 'if debug: skip_validation'\n"
            "# temperature=0.9 and skip_validation in documentation\n"
        )

        self.assertEqual(_findings_for(code, ".py", "C09"), [])
        self.assertEqual(_findings_for(code, ".py", "C11"), [])

    def test_javascript_regex_strings_and_comments_do_not_trigger_rules(self):
        code = (
            "const temperaturePattern = /temperature\\s*[:=]\\s*0.7/;\n"
            "const fixture = 'skipValidation = true; fallback retry charge';\n"
            "// process.env.NODE_ENV !== 'production'; forcePass = true;\n"
        )

        for check_id in ("C04", "C05", "C09", "C11", "C15"):
            with self.subTest(check_id=check_id):
                self.assertEqual(_findings_for(code, ".js", check_id), [])


if __name__ == "__main__":
    unittest.main()
