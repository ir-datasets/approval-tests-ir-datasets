import unittest

import pytest

from approval_tests_ir_datasets import DatasetNotFoundError, cached_result, verify

try:
    import ir_datasets.v2  # noqa: F401

    IR_DATASETS_V2_AVAILABLE = True
except ImportError:
    IR_DATASETS_V2_AVAILABLE = False


def test_verify_raises_for_unknown_dataset() -> None:
    with pytest.raises(
        DatasetNotFoundError,
        match="Dataset 'dataset-id' does not exist\\.",
    ):
        verify("dataset-id")


@unittest.skipUnless(IR_DATASETS_V2_AVAILABLE, "ir_datasets.v2 is not installed")
class VerifyKnownDatasetTest(unittest.TestCase):
    def test_verify_succeeds_for_known_table_dataset(self) -> None:
        result = verify("irds:cranfield-docs", return_result=True)

        # Only assert on the always-available verifier's result: depending on
        # the environment, other verifiers (e.g. PyTerrierIndexVerifier, which
        # additionally requires "tira", "tira-cli" and Docker) may or may not
        # contribute to the aggregated result.
        self.assertEqual(result.get("table_line_count"), {"length": 1400})

    def test_cached_result_returns_the_previously_verified_result(self) -> None:
        result = verify("irds:cranfield-docs", return_result=True)

        cached = cached_result("irds:cranfield-docs")

        self.assertEqual(cached, result)

    def test_cached_result_returns_none_without_a_prior_verify_call(self) -> None:
        cached = cached_result("irds:a-dataset-that-was-never-verified")

        self.assertIsNone(cached)

    def test_verify_returns_none_by_default(self) -> None:
        # return_result defaults to False so that a bare verify(...) call
        # left as a notebook cell's last expression doesn't also
        # auto-display its (much noisier) raw result dict right below the
        # printed summary.
        result = verify("irds:cranfield-docs")

        self.assertIsNone(result)

