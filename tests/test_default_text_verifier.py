import hashlib
import unittest

try:
    import ir_datasets.v2  # noqa: F401

    IR_DATASETS_V2_AVAILABLE = True
except ImportError:
    IR_DATASETS_V2_AVAILABLE = False

from approval_tests_ir_datasets.verifiers import DefaultTextVerifier


def _expected_samples(dataset_id: str, id_field: str):
    import ir_datasets.v2 as ir_datasets_v2

    node = ir_datasets_v2.load(dataset_id)
    ranked = sorted(
        node, key=lambda record: hashlib.md5(str(getattr(record, id_field)).encode("utf-8")).hexdigest()
    )
    return [
        {"id": getattr(record, id_field), "text": record.default_text()}
        for record in ranked[:2]
    ]


@unittest.skipUnless(
    IR_DATASETS_V2_AVAILABLE, "ir_datasets.v2 is required (available in the dev container)"
)
class DefaultTextVerifierTest(unittest.TestCase):
    def test_verify_samples_2_deterministically_chosen_docs(self) -> None:
        result = DefaultTextVerifier().verify("irds:cranfield-docs")

        self.assertEqual(result, {"samples": _expected_samples("irds:cranfield-docs", "doc_id")})
        self.assertEqual(len(result["samples"]), 2)

    def test_verify_samples_2_deterministically_chosen_queries(self) -> None:
        # DefaultTextVerifier applies to any table whose records expose
        # default_text() -- not just document tables -- so query tables are
        # sampled too, just like PyTerrierIndexVerifier.
        result = DefaultTextVerifier().verify("irds:cranfield-queries")

        self.assertEqual(
            result, {"samples": _expected_samples("irds:cranfield-queries", "query_id")}
        )
        self.assertEqual(len(result["samples"]), 2)

    def test_verify_is_deterministic_across_calls(self) -> None:
        first = DefaultTextVerifier().verify("irds:cranfield-docs")
        second = DefaultTextVerifier().verify("irds:cranfield-docs")

        self.assertEqual(first, second)

    def test_verify_returns_none_for_qrels_table(self) -> None:
        result = DefaultTextVerifier().verify("irds:cranfield-qrels")

        self.assertIsNone(result)

    def test_verify_returns_none_for_non_table_resources(self) -> None:
        result = DefaultTextVerifier().verify("irds:cranfield")

        self.assertIsNone(result)
