import unittest

try:
    import ir_datasets.v2  # noqa: F401

    IR_DATASETS_V2_AVAILABLE = True
except ImportError:
    IR_DATASETS_V2_AVAILABLE = False

from approval_tests_ir_datasets.verifiers import QrelTableStatsVerifier


@unittest.skipUnless(IR_DATASETS_V2_AVAILABLE, "ir_datasets.v2 is not installed")
class QrelTableStatsVerifierTest(unittest.TestCase):
    def test_verify_computes_stats_for_cranfield_qrels(self) -> None:
        result = QrelTableStatsVerifier().verify("irds:cranfield-qrels")

        self.assertEqual(
            result,
            {
                "number_of_queries": 225,
                "relevance_counts": {-1: 225, 1: 128, 2: 387, 3: 734, 4: 363},
            },
        )

    def test_verify_returns_none_for_docs_table(self) -> None:
        result = QrelTableStatsVerifier().verify("irds:cranfield-docs")

        self.assertIsNone(result)

    def test_verify_returns_none_for_queries_table(self) -> None:
        result = QrelTableStatsVerifier().verify("irds:cranfield-queries")

        self.assertIsNone(result)

    def test_verify_returns_none_for_non_table_resources(self) -> None:
        result = QrelTableStatsVerifier().verify("irds:cranfield")

        self.assertIsNone(result)
