class DatasetNotFoundError(LookupError):
    """Raised when `verify` is asked to check an unknown dataset."""


def verify(dataset_id: str) -> None:
    """Verify a dataset identifier.

    The current minimal implementation always raises
    ``DatasetNotFoundError`` for every input because no dataset registry has
    been added yet.
    """
    raise DatasetNotFoundError(f"Dataset '{dataset_id}' does not exist.")


__all__ = ["DatasetNotFoundError", "verify"]
