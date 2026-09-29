import importlib.metadata
from typing import Any, Dict, List

#: Entry point group under which verifier classes register themselves.
#: Each entry point is expected to resolve to a class that can be
#: instantiated without arguments and that exposes a
#: ``verify(dataset_id: str)`` method.
ENTRY_POINT_GROUP = "approval_tests_ir_datasets.verifiers"


class DatasetNotFoundError(LookupError):
    """Raised when `verify` is asked to check an unknown dataset."""


def verify(dataset_id: str) -> None:
    """Verify a dataset identifier.

    The current minimal implementation always raises
    ``DatasetNotFoundError`` for every input because no dataset registry has
    been added yet.
    """
    raise DatasetNotFoundError(f"Dataset '{dataset_id}' does not exist.")


def _discover_verifiers() -> List[importlib.metadata.EntryPoint]:
    """Return the entry points registered under ``ENTRY_POINT_GROUP``.

    Handles both the ``EntryPoints.select`` API (Python >= 3.10) and the
    dict-like API returned by ``importlib.metadata.entry_points`` on
    Python 3.9.
    """
    entry_points = importlib.metadata.entry_points()
    if hasattr(entry_points, "select"):
        return list(entry_points.select(group=ENTRY_POINT_GROUP))
    return list(entry_points.get(ENTRY_POINT_GROUP, []))


class IrDatasetsApprovalTest:
    """Applies every registered verifier to an ir_datasets dataset id.

    Verifier classes are discovered via the
    ``approval_tests_ir_datasets.verifiers`` Python entry point group. Each
    discovered class is instantiated without arguments, and its
    ``verify(dataset_id)`` method is called with the dataset id passed to
    :meth:`verify`. If no verifiers are registered, an empty dict is
    returned.
    """

    def verify(self, dataset_id: str) -> Dict[str, Any]:
        """Run every registered verifier against ``dataset_id``.

        Returns a dict mapping each verifier's entry point name to the
        result of its ``verify(dataset_id)`` call.
        """
        results: Dict[str, Any] = {}
        for entry_point in _discover_verifiers():
            verifier_cls = entry_point.load()
            verifier = verifier_cls()
            results[entry_point.name] = verifier.verify(dataset_id)
        return results


__all__ = ["DatasetNotFoundError", "IrDatasetsApprovalTest", "verify"]
