"""Validate configuration precedence and integration limits without services."""

from pathlib import Path
import shutil
import tempfile
import unittest

from core.config import Settings, load_settings
from core.config.loader import CONFIG_FILES
from core.exceptions import ConfigurationError
from core.schemas import RetrievalStrategy


REPO_CONFIGS = Path(__file__).resolve().parents[1] / "configs"


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="config-test-", dir=Path(__file__).resolve().parent,
        )
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "configs"
        self.directory.mkdir()
        for filename in CONFIG_FILES:
            shutil.copyfile(REPO_CONFIGS / filename, self.directory / filename)

    def load(self, environ=None):
        return load_settings(self.directory, environ={} if environ is None else environ)

    def test_repo_defaults_build_compatible_strategy_and_absolute_paths(self):
        settings = self.load()
        strategy = settings.retrieval.default_strategy()
        self.assertIsInstance(strategy, RetrievalStrategy)
        self.assertEqual((strategy.top_k, strategy.candidate_k), (5, 20))
        self.assertEqual(settings.pipeline.max_iterations, 3)
        self.assertEqual(settings.data_pipeline.raw_dir, self.directory.parent / "data/raw")
        self.assertFalse(settings.data_pipeline.raw_dir.exists())

    def test_environment_overrides_nested_values_and_json_lists(self):
        settings = self.load({
            "RAG__RETRIEVAL__TOP_K": "8",
            "RAG__RETRIEVAL__CANDIDATE_K": "40",
            "RAG__RETRIEVAL__USE_GRAPH": "true",
            "RAG__LLM__ANSWER_GENERATOR__MAX_OUTPUT_TOKENS": "1024",
            "RAG__API__CORS_ORIGINS": '["http://localhost:3000"]',
        })
        self.assertEqual(settings.retrieval.top_k, 8)
        self.assertEqual(settings.retrieval.candidate_k, 40)
        self.assertTrue(settings.retrieval.use_graph)
        self.assertEqual(settings.llm.answer_generator.max_output_tokens, 1024)
        self.assertEqual(settings.api.cors_origins, ("http://localhost:3000",))

    def test_defaults_fill_omitted_fields_in_present_sections(self):
        (self.directory / "retrieval.yml").write_text("retrieval: {}\n", encoding="utf-8")
        self.assertEqual(self.load().retrieval.top_k, 5)

    def test_directory_precedence(self):
        settings = load_settings(environ={"RAG_CONFIG_DIR": str(self.directory)})
        self.assertEqual(settings.retrieval.top_k, 5)
        settings = load_settings(self.directory, environ={"RAG_CONFIG_DIR": "does-not-exist"})
        self.assertEqual(settings.retrieval.top_k, 5)

    def test_environment_is_not_cached_or_mutated_between_loads(self):
        env = {"RAG__RETRIEVAL__TOP_K": "8"}
        self.assertEqual(self.load(env).retrieval.top_k, 8)
        self.assertEqual(self.load().retrieval.top_k, 5)
        self.assertEqual(env, {"RAG__RETRIEVAL__TOP_K": "8"})

    def test_unknown_options_and_wrong_limits_fail_early(self):
        invalid_provider_timeout = str(self.load().pipeline.timeout_s + 1)
        invalid = (
            {"RAG__RETRIEVAL__TOPK": "8"},
            {"RAG__RETRIEVAL__TOP_K": "0"},
            {"RAG__RETRIEVAL__TOP_K": "true"},
            {"RAG__RETRIEVAL__TOP_K": "21"},
            {"RAG__RETRIEVAL__CANDIDATE_K": "101"},
            {"RAG__RETRIEVAL__CANDIDATE_K": "4"},
            {"RAG__DATA_PIPELINE__CHUNKING__OVERLAP_TOKENS": "512"},
            {"RAG__PIPELINE__MAX_ITERATIONS": "0"},
            {"RAG__RETRIEVAL__GRAPH__MAX_DEPTH": "0"},
            {"RAG__LLM__TIMEOUT_S": invalid_provider_timeout},
            {"RAG__EMBEDDING__TIMEOUT_S": invalid_provider_timeout},
            {"RAG__LLM__TIMEOUT_S": '"NaN"'},
            {"RAG__API__PORT": "70000"},
            {"RAG__LOGGING__LEVEL": "verbose"},
        )
        for env in invalid:
            with self.subTest(env=env), self.assertRaises(ConfigurationError):
                self.load(env)

    def test_disabling_every_search_method_is_invalid(self):
        with self.assertRaises(ConfigurationError):
            self.load({
                "RAG__RETRIEVAL__USE_BM25": "false",
                "RAG__RETRIEVAL__USE_VECTOR": "false",
                "RAG__RETRIEVAL__USE_GRAPH": "false",
            })

    def test_token_budgets_include_context_prompt_and_output(self):
        field = "RAG__LLM__ANSWER_GENERATOR__CONTEXT_WINDOW_TOKENS"
        self.assertEqual(self.load({field: "7168"}).llm.answer_generator.context_window_tokens, 7168)
        with self.assertRaises(ConfigurationError):
            self.load({field: "7167"})
        with self.assertRaises(ConfigurationError):
            self.load({"RAG__LLM__QUERY_ANALYZER__CONTEXT_WINDOW_TOKENS": "512"})

    def test_router_and_feedback_strategies_cannot_exceed_hard_limits(self):
        retrieval = self.load().retrieval
        self.assertEqual(retrieval.validate_strategy(retrieval.default_strategy()).top_k, 5)
        for extra in ({"top_k": 21, "candidate_k": 30}, {"candidate_k": 101}):
            strategy = RetrievalStrategy(reason="Test override", **extra)
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                retrieval.validate_strategy(strategy)

    def test_secrets_keep_raw_string_and_are_redacted(self):
        raw = '123:{"sensitive":"example"}'
        settings = self.load({
            "RAG__LLM__API_KEY": raw,
            "RAG__EMBEDDING__API_KEY": "123",
            "RAG__DATABASE__VECTOR__PASSWORD": raw,
        })
        self.assertEqual(settings.llm.api_key.get_secret_value(), raw)
        self.assertEqual(settings.embedding.api_key.get_secret_value(), "123")
        self.assertNotIn(raw, settings.model_dump_json())
        self.assertNotIn(raw, repr(settings))
        self.assertIn("**********", settings.model_dump_json())
        with self.assertRaises(ConfigurationError):
            self.load({"RAG__LLM__API_KEY": " "})

    def test_yaml_credentials_are_rejected_without_echoing_values(self):
        path = self.directory / "llm.yml"
        path.write_text("llm:\n  api_key: do-not-echo-this-secret\n", encoding="utf-8")
        with self.assertRaises(ConfigurationError) as raised:
            self.load()
        self.assertNotIn("do-not-echo-this-secret", str(raised.exception))
        self.assertIn("environment", str(raised.exception))

    def test_duplicate_invalid_and_wrong_section_yaml_are_rejected(self):
        path = self.directory / "retrieval.yml"
        for content in (
            "retrieval:\n  top_k: 5\n  top_k: 8\n",
            "retrieval: [\n",
            "wrong_section: {}\n",
            "retrieval: {}\nextra: {}\n",
            "retrieval:\n  unexpected: true\n",
            "retrieval: !!python/object:builtins.object {}\n",
        ):
            path.write_text(content, encoding="utf-8")
            with self.subTest(content=content), self.assertRaises(ConfigurationError):
                self.load()

    def test_missing_file_is_an_error(self):
        (self.directory / "embedding.yml").unlink()
        with self.assertRaisesRegex(ConfigurationError, "embedding.yml"):
            self.load()

    def test_sample_loads_for_mocks_but_real_runtime_requires_model_choices(self):
        settings = Settings()
        with self.assertRaises(ConfigurationError) as raised:
            settings.validate_runtime()
        self.assertIn("embedding.dimension", str(raised.exception))
        self.assertIn("llm.query_analyzer.model", str(raised.exception))
        with self.assertRaises(ConfigurationError) as raised:
            settings.validate_runtime(purpose="ingestion")
        self.assertIn("chunking.tokenizer_model", str(raised.exception))

    def test_explicit_local_selections_pass_without_contacting_services(self):
        env = {
            "RAG__EMBEDDING__PROVIDER": "local",
            "RAG__EMBEDDING__MODEL": "test-only-embedding",
            "RAG__EMBEDDING__DIMENSION": "3",
            "RAG__LLM__PROVIDER": "local",
            "RAG__RETRIEVAL__RERANKER__MODEL": "test-only-reranker",
            "RAG__DATA_PIPELINE__CHUNKING__TOKENIZER_MODEL": "test-only-tokenizer",
        }
        for name in ("QUERY_ANALYZER", "RETRIEVAL_EVALUATOR", "ANSWER_GENERATOR", "CITATION_VERIFIER"):
            env[f"RAG__LLM__{name}__MODEL"] = "test-only-model"
            env[f"RAG__LLM__{name}__CONTEXT_WINDOW_TOKENS"] = "8192"
        settings = self.load(env)
        settings.validate_runtime()
        settings.validate_runtime(purpose="ingestion")
        env["RAG__LLM__PROVIDER"] = "openai"
        with self.assertRaisesRegex(ConfigurationError, "llm.api_key"):
            self.load(env).validate_runtime()

    def test_settings_are_frozen(self):
        settings = self.load()
        with self.assertRaises(ValueError):
            settings.retrieval.top_k = 8


if __name__ == "__main__":
    unittest.main()
