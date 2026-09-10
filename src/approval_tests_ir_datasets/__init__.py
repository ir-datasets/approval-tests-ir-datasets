def verify(dataset_id: str) -> None:
    """Verify a dataset identifier.

    The current minimal implementation always raises ``ValueError`` because no
    dataset registry has been added yet.
    """
    raise ValueError(f"Dataset '{dataset_id}' does not exist.")


__all__ = ["verify"]
