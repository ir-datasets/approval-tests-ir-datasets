import shutil
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

TIRA_CLI_AVAILABLE = shutil.which("tira-cli") is not None

from approval_tests_ir_datasets.verifiers import RetrievalVerifier

REQUIREMENTS_AVAILABLE = (
    IR_DATASETS_V2_AVAILABLE and TIRA_AVAILABLE and TIRA_CLI_AVAILABLE
)


@unittest.skipUnless(
    REQUIREMENTS_AVAILABLE,
    "ir_datasets.v2, tira, tira-cli and docker are required (available in the dev container)",
)
class RetrievalVerifierTest(unittest.TestCase):
    def test_verify_runs_bm25_for_cranfield_benchmark(self) -> None:
        result = RetrievalVerifier().verify("irds:cranfield")

        self.assertEqual(result.get("num_queries"), 225)
        self.assertGreater(result.get("num_results", 0), 0)

    def test_verify_returns_none_for_docs_only_resource(self) -> None:
        result = RetrievalVerifier().verify("irds:cranfield-docs")

        self.assertIsNone(result)

    def test_verify_returns_none_for_queries_only_resource(self) -> None:
        result = RetrievalVerifier().verify("irds:cranfield-queries")

        self.assertIsNone(result)

    def test_cached_run_path_finds_the_run_file_produced_by_verify(self) -> None:
        import approval_tests_ir_datasets as atid

        atid.verify("irds:cranfield")

        run_path = RetrievalVerifier().cached_run_path("irds:cranfield")

        self.assertIsNotNone(run_path)
        self.assertTrue(run_path.is_file())

    def test_cached_run_path_returns_none_without_a_prior_verify_call(self) -> None:
        run_path = RetrievalVerifier().cached_run_path(
            "irds:a-dataset-that-was-never-verified"
        )

        self.assertIsNone(run_path)
