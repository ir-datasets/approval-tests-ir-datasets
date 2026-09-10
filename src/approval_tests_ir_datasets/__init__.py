def verify(dataset_id: str) -> None:
    raise ValueError(f"Dataset '{dataset_id}' does not exist.")


__all__ = ["verify"]
