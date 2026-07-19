import os
import unittest
from unittest import mock

from aira.cli import build_parser
from aira.llm import LLMConfig, provider_health_snapshot


class ProviderHealthSnapshotTests(unittest.TestCase):
    def test_local_openai_compatible_is_detected(self):
        with mock.patch.dict(
            os.environ,
            {
                "AIRA_OPENAI_BASE_URL": "http://localhost:1234/v1",
                "AIRA_OPENAI_MODEL": "gpt-oss-120b",
            },
            clear=False,
        ):
            snapshot = provider_health_snapshot(LLMConfig())

        self.assertTrue(snapshot["ok"])
        self.assertIn("openai-compatible", snapshot["configured_providers"])
        self.assertEqual(snapshot["providers"]["openai-compatible"]["model"], "gpt-oss-120b")

    def test_ollama_defaults_host_when_model_present(self):
        with mock.patch.dict(os.environ, {"AIRA_OLLAMA_MODEL": "qwen3:32b"}, clear=False):
            with mock.patch(
                "aira.llm._fetch_ollama_models",
                return_value=[{"name": "qwen3:32b"}, {"name": "llama3.1:8b"}],
            ):
                snapshot = provider_health_snapshot(LLMConfig())

        self.assertIn("ollama", snapshot["configured_providers"])
        self.assertEqual(snapshot["providers"]["ollama"]["base_url"], "http://127.0.0.1:11434")
        self.assertTrue(snapshot["providers"]["ollama"]["reachable"])
        self.assertIn("qwen3:32b", snapshot["providers"]["ollama"]["available_models"])
        self.assertTrue(snapshot["providers"]["ollama"]["selected_model_available"])

    def test_groq_configured_with_api_key_alone_uses_default_model(self):
        env = {"AIRA_GROQ_API_KEY": "test-key"}
        removed = {name: "" for name in ("AIRA_GROQ_MODEL", "GROQ_MODEL")}
        with mock.patch.dict(os.environ, {**env, **removed}, clear=False):
            with mock.patch("aira.llm._fetch_ollama_models", return_value=[]):
                snapshot = provider_health_snapshot(LLMConfig())

        self.assertIn("groq", snapshot["configured_providers"])
        self.assertEqual(snapshot["providers"]["groq"]["model"], "llama-3.1-8b-instant")

    def test_cli_accepts_gemini_as_explicit_provider(self):
        args = build_parser().parse_args(["scan", "sample.py", "--engine", "llm", "--provider", "gemini"])

        self.assertEqual(args.provider, "gemini")

    def test_groq_env_model_overrides_default(self):
        env = {"AIRA_GROQ_API_KEY": "test-key", "AIRA_GROQ_MODEL": "openai/gpt-oss-120b"}
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch("aira.llm._fetch_ollama_models", return_value=[]):
                snapshot = provider_health_snapshot(LLMConfig())

        self.assertEqual(snapshot["providers"]["groq"]["model"], "openai/gpt-oss-120b")

    def test_explicit_config_model_overrides_groq_default(self):
        env = {"AIRA_GROQ_API_KEY": "test-key"}
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch("aira.llm._fetch_ollama_models", return_value=[]):
                snapshot = provider_health_snapshot(LLMConfig(model="qwen/qwen3-32b"))

        self.assertEqual(snapshot["providers"]["groq"]["model"], "qwen/qwen3-32b")

    def test_ollama_reports_missing_selected_model(self):
        with mock.patch.dict(os.environ, {"AIRA_OLLAMA_MODEL": "missing-model"}, clear=False):
            with mock.patch(
                "aira.llm._fetch_ollama_models",
                return_value=[{"name": "llama3.1:8b"}, {"name": "minimax-m2:cloud"}],
            ):
                snapshot = provider_health_snapshot(LLMConfig())

        self.assertIn("ollama", snapshot["configured_providers"])
        self.assertFalse(snapshot["providers"]["ollama"]["selected_model_available"])

    def test_explicit_provider_health_only_reports_selected_provider_as_configured(self):
        with mock.patch.dict(
            os.environ,
            {
                "AIRA_OPENAI_BASE_URL": "http://localhost:1234/v1",
                "AIRA_OPENAI_MODEL": "gpt-oss-120b",
                "AIRA_GROQ_API_KEY": "test-key",
            },
            clear=False,
        ):
            snapshot = provider_health_snapshot(LLMConfig(provider="groq", model="llama-3.1-8b-instant"))

        self.assertTrue(snapshot["ok"])
        self.assertEqual(snapshot["selected_provider"], "groq")
        self.assertEqual(snapshot["configured_providers"], ["groq"])
        self.assertEqual(snapshot["providers"]["groq"]["model"], "llama-3.1-8b-instant")


if __name__ == "__main__":
    unittest.main()
