import pytest

from approval_tests_ir_datasets import DatasetNotFoundError, verify


def test_verify_raises_for_unknown_dataset() -> None:
    with pytest.raises(
        DatasetNotFoundError,
        match="Dataset 'dataset-id' does not exist\\.",
    ):
        verify("dataset-id")
