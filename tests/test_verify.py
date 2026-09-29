import unittest

import pytest

from approval_tests_ir_datasets import DatasetNotFoundError, verify

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
        result = verify("irds:cranfield-docs")

        self.assertEqual(result, {"table_line_count": {"length": 1400}})

