import unittest

try:
    import ir_datasets.v2  # noqa: F401

    IR_DATASETS_V2_AVAILABLE = True
except ImportError:
    IR_DATASETS_V2_AVAILABLE = False

try:
    import tira  # noqa: F401

    TIRA_AVAILABLE = True
except ImportError:
    TIRA_AVAILABLE = False

try:
    import ir_measures  # noqa: F401

    IR_MEASURES_AVAILABLE = True
except ImportError:
    IR_MEASURES_AVAILABLE = False

from approval_tests_ir_datasets.verifiers import EvaluationVerifier, RetrievalVerifier

REQUIREMENTS_AVAILABLE = IR_DATASETS_V2_AVAILABLE and TIRA_AVAILABLE and IR_MEASURES_AVAILABLE

EXPECTED_APPROACH_NAMES = {"BM25", "DirichletLM", "DPH", "Hiemstra_LM", "PL2"}
EXPECTED_METRIC_NAMES = {"nDCG@10", "recip_rank", "Recall@100"}


@unittest.skipUnless(
    REQUIREMENTS_AVAILABLE,
    "ir_datasets.v2, tira, docker and ir_measures are required (available in the dev container)",
)
class EvaluationVerifierTest(unittest.TestCase):
    def test_verify_reports_metrics_for_all_approaches_for_cranfield_benchmark(self) -> None:
        result = EvaluationVerifier().verify("irds:cranfield")

        self.assertEqual(set(result.keys()), EXPECTED_APPROACH_NAMES)
        for name, metrics in result.items():
            self.assertEqual(set(metrics.keys()), EXPECTED_METRIC_NAMES)
            for metric_name, value in metrics.items():
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)

    def test_verify_populates_the_retrieval_cache_itself(self) -> None:
        # EvaluationVerifier doesn't rely on RetrievalVerifier already
        # having run (e.g. because of entry point iteration order) -- it
        # (re)runs it itself.
        result = EvaluationVerifier().verify("irds:cranfield")

        self.assertIsNotNone(result)
        run_path = RetrievalVerifier().cached_run_path("irds:cranfield")
        self.assertIsNotNone(run_path)
        self.assertTrue(run_path.is_file())

    def test_verify_returns_none_for_docs_only_resource(self) -> None:
        result = EvaluationVerifier().verify("irds:cranfield-docs")

        self.assertIsNone(result)

    def test_verify_returns_none_for_queries_only_resource(self) -> None:
        result = EvaluationVerifier().verify("irds:cranfield-queries")

        self.assertIsNone(result)
