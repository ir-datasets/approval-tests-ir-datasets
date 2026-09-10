import pytest

from approval_tests_ir_datasets import verify


def test_verify_raises_for_unknown_dataset() -> None:
    with pytest.raises(ValueError, match="Dataset 'dataset-id' does not exist\\."):
        verify("dataset-id")
