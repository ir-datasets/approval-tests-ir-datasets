import unittest

try:
    import ir_datasets.v2  # noqa: F401

    IR_DATASETS_V2_AVAILABLE = True
except ImportError:
    IR_DATASETS_V2_AVAILABLE = False

from approval_tests_ir_datasets.verifiers import TableLineCountVerifier


@unittest.skipUnless(IR_DATASETS_V2_AVAILABLE, "ir_datasets.v2 is not installed")
class TableLineCountVerifierTest(unittest.TestCase):
    def test_verify_counts_records_for_cranfield_docs(self) -> None:
        result = TableLineCountVerifier().verify("irds:cranfield-docs")

        self.assertEqual(result, {"length": 1400})

    def test_verify_counts_records_for_cranfield_queries(self) -> None:
        result = TableLineCountVerifier().verify("irds:cranfield-queries")

        self.assertEqual(result, {"length": 225})

    def test_verify_counts_records_for_cranfield_qrels(self) -> None:
        result = TableLineCountVerifier().verify("irds:cranfield-qrels")

        self.assertEqual(result, {"length": 1837})

    def test_verify_returns_none_for_non_table_resources(self) -> None:
        result = TableLineCountVerifier().verify("irds:cranfield")

        self.assertIsNone(result)
