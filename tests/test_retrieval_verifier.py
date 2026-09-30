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

EXPECTED_APPROACH_NAMES = {"BM25", "DirichletLM", "DPH", "Hiemstra_LM", "PL2"}


@unittest.skipUnless(
    REQUIREMENTS_AVAILABLE,
    "ir_datasets.v2, tira, tira-cli and docker are required (available in the dev container)",
)
class RetrievalVerifierTest(unittest.TestCase):
    def test_verify_runs_all_approaches_for_cranfield_benchmark(self) -> None:
        result = RetrievalVerifier().verify("irds:cranfield")

        self.assertEqual(result.get("num_queries"), 225)
        self.assertEqual(set(result.get("runs", {}).keys()), EXPECTED_APPROACH_NAMES)
        for name, run_result in result["runs"].items():
            self.assertGreater(run_result.get("num_results", 0), 0)

    def test_verify_reports_jaccard_similarity_to_bm25_for_other_approaches(self) -> None:
        result = RetrievalVerifier().verify("irds:cranfield")

        runs = result["runs"]
        self.assertNotIn("jaccard_similarity_to_bm25", runs["BM25"])
        for name in EXPECTED_APPROACH_NAMES - {"BM25"}:
            similarity = runs[name]["jaccard_similarity_to_bm25"]
            self.assertEqual(set(similarity.keys()), {"top_10", "top_100"})
            for value in similarity.values():
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)

    def test_verify_returns_none_for_docs_only_resource(self) -> None:
        result = RetrievalVerifier().verify("irds:cranfield-docs")

        self.assertIsNone(result)

    def test_verify_returns_none_for_queries_only_resource(self) -> None:
        result = RetrievalVerifier().verify("irds:cranfield-queries")

        self.assertIsNone(result)

    def test_cached_run_path_finds_the_bm25_run_file_by_default(self) -> None:
        import approval_tests_ir_datasets as atid

        atid.verify("irds:cranfield")

        run_path = RetrievalVerifier().cached_run_path("irds:cranfield")

        self.assertIsNotNone(run_path)
        self.assertTrue(run_path.is_file())

    def test_cached_run_path_finds_a_specific_approachs_run_file(self) -> None:
        import approval_tests_ir_datasets as atid

        atid.verify("irds:cranfield")

        run_path = RetrievalVerifier().cached_run_path(
            "irds:cranfield",
            "ir-benchmarks/tira-ir-starter/DPH (tira-ir-starter-pyterrier)",
        )

        self.assertIsNotNone(run_path)
        self.assertTrue(run_path.is_file())

    def test_cached_run_path_returns_none_without_a_prior_verify_call(self) -> None:
        run_path = RetrievalVerifier().cached_run_path(
            "irds:a-dataset-that-was-never-verified"
        )

        self.assertIsNone(run_path)


class JaccardSimilarityTest(unittest.TestCase):
    def test_identical_runs_have_similarity_one(self) -> None:
        run = {"q1": ["d1", "d2", "d3"]}

        similarity = RetrievalVerifier._jaccard_similarity(run, run, k=10)

        self.assertEqual(similarity, 1.0)

    def test_disjoint_runs_have_similarity_zero(self) -> None:
        run_a = {"q1": ["d1", "d2"]}
        run_b = {"q1": ["d3", "d4"]}

        similarity = RetrievalVerifier._jaccard_similarity(run_a, run_b, k=10)

        self.assertEqual(similarity, 0.0)

    def test_partially_overlapping_runs(self) -> None:
        run_a = {"q1": ["d1", "d2", "d3"]}
        run_b = {"q1": ["d2", "d3", "d4"]}

        # intersection {d2, d3} / union {d1, d2, d3, d4} = 2 / 4
        similarity = RetrievalVerifier._jaccard_similarity(run_a, run_b, k=10)

        self.assertEqual(similarity, 0.5)

    def test_respects_the_k_cutoff(self) -> None:
        run_a = {"q1": ["d1", "d2", "d3"]}
        run_b = {"q1": ["d1", "d4", "d5"]}

        # top_1: {d1} vs {d1} -> 1.0
        self.assertEqual(RetrievalVerifier._jaccard_similarity(run_a, run_b, k=1), 1.0)
        # top_3: {d1,d2,d3} vs {d1,d4,d5} -> 1/5
        self.assertEqual(RetrievalVerifier._jaccard_similarity(run_a, run_b, k=3), 0.2)

    def test_averages_over_multiple_queries(self) -> None:
        run_a = {"q1": ["d1"], "q2": ["d2"]}
        run_b = {"q1": ["d1"], "q2": ["d3"]}

        # q1: 1.0, q2: 0.0 -> average 0.5
        similarity = RetrievalVerifier._jaccard_similarity(run_a, run_b, k=10)

        self.assertEqual(similarity, 0.5)
