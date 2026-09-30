import importlib.metadata
import json
from typing import Any, Dict, List, Optional

#: Entry point group under which verifier classes register themselves.
#: Each entry point is expected to resolve to a class that can be
#: instantiated without arguments and that exposes a
#: ``verify(dataset_id: str)`` method.
ENTRY_POINT_GROUP = "approval_tests_ir_datasets.verifiers"

#: ir_datasets.v2 structural edge kinds that represent *provenance* (e.g. "this
#: table was derived from that raw archive"), as opposed to *content* (e.g.
#: "this benchmark has this document table"). Only content edges are followed
#: when traversing a dataset's sub resources -- provenance edges would pull in
#: raw, non-table resources that none of the verifiers apply to anyway.
_PROVENANCE_EDGE_KINDS = {"irds:derived_from"}


class DatasetNotFoundError(LookupError):
    """Raised when `verify` is asked to check an unknown dataset."""


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

    ``dataset_id`` is also traversed for sub resources (e.g. a benchmark's
    document, query and qrels tables) via ir_datasets.v2's structural edges,
    so that e.g. verifying a benchmark also verifies each of its tables (see
    :meth:`verify` for the exact result shape this produces).

    The aggregated result is also persisted as ``result.json`` under a
    deterministic directory rooted at ir_datasets' home directory (see
    :mod:`approval_tests_ir_datasets.paths`), on a best-effort basis: this is
    silently skipped if ``ir_datasets`` isn't installed. Every call to
    :meth:`verify` re-runs all verifiers from scratch and overwrites this
    persisted result; use :meth:`cached_result` to read it back without
    triggering a re-run.
    """

    def verify(self, dataset_id: str) -> Dict[str, Any]:
        """Run every registered verifier against ``dataset_id`` and its sub resources.

        ``dataset_id`` is first traversed for sub resources (e.g. a
        benchmark's document, query and qrels tables) by following
        ir_datasets.v2's structural "content" edges (``docs``, ``queries``,
        ``qrels``, ``docpairs``, ``scoreddocs``, ...) -- provenance edges
        (e.g. ``derived_from`` a raw archive) are not followed. This
        traversal requires ``ir_datasets``; if it isn't installed, or
        ``dataset_id`` doesn't expose any structural edges (e.g. it's
        already a leaf table), only ``dataset_id`` itself is checked.

        * If ``dataset_id`` has no sub resources, this returns a flat dict
          mapping each verifier's entry point name to the result of its
          ``verify(dataset_id)`` call (verifiers that return ``None`` are
          omitted) -- this is the original, single-resource result shape.
        * If ``dataset_id`` does have sub resources (e.g. it's a benchmark),
          this instead returns a dict mapping every visited dataset id
          (``dataset_id`` itself, plus each sub resource's qualified name)
          to its own flat verifier-name-to-result dict, as above.

        Each visited dataset id's flat result is persisted independently
        (see :meth:`cached_result`), in addition to the aggregated result
        being persisted for ``dataset_id`` itself. This always recomputes
        every verifier's result from scratch (e.g. rebuilding
        ``PyTerrierIndexVerifier``'s index) and overwrites any previously
        persisted result.
        """
        dataset_ids = self._collect_dataset_ids(dataset_id)

        if len(dataset_ids) == 1:
            results = self._run_verifiers(dataset_id)
        else:
            results = {}
            for sub_dataset_id in dataset_ids:
                sub_results = self._run_verifiers(sub_dataset_id)
                results[sub_dataset_id] = sub_results
                if sub_dataset_id != dataset_id:
                    self._persist_results(sub_dataset_id, sub_results)

        self._persist_results(dataset_id, results)
        return results

    @staticmethod
    def _run_verifiers(dataset_id: str) -> Dict[str, Any]:
        """Run every registered verifier against a single ``dataset_id``.

        Returns a dict mapping each verifier's entry point name to the
        result of its ``verify(dataset_id)`` call. Verifiers that return
        ``None`` (e.g. because the dataset isn't the kind of resource they
        apply to) are omitted from the result.
        """
        results: Dict[str, Any] = {}
        for entry_point in _discover_verifiers():
            verifier_cls = entry_point.load()
            verifier = verifier_cls()
            result = verifier.verify(dataset_id)
            if result is not None:
                results[entry_point.name] = result
        return results

    @staticmethod
    def _collect_dataset_ids(dataset_id: str) -> List[str]:
        """Return ``dataset_id`` plus the qualified names of every sub
        resource reachable from it via structural "content" edges (e.g. a
        benchmark's ``docs``, ``queries``, ``qrels``, ``docpairs`` and
        ``scoreddocs``), traversed breadth-first and deduplicated.

        Provenance edges (``derived_from``) are not followed. Returns just
        ``[dataset_id]`` if ``ir_datasets`` isn't installed, if
        ``dataset_id`` can't be resolved, or if it has no structural edges
        (e.g. it's already a leaf table).
        """
        try:
            import ir_datasets.v2 as ir_datasets_v2
        except ImportError:
            return [dataset_id]

        visited = [dataset_id]
        seen = {dataset_id}
        queue = [dataset_id]
        while queue:
            current_id = queue.pop(0)
            try:
                node = ir_datasets_v2.load(current_id)
            except KeyError:
                # Unresolvable id (e.g. a fake id used in tests, or one that
                # doesn't actually exist) -- leave resolving/raising for the
                # actual verifier calls, traversal simply stops here.
                continue
            structural_edges = getattr(node, "structural_edges", None)
            if not callable(structural_edges):
                continue
            for edge in structural_edges():
                if edge.kind in _PROVENANCE_EDGE_KINDS:
                    continue
                target_id = edge.target.qualified_name
                if target_id in seen:
                    continue
                seen.add(target_id)
                visited.append(target_id)
                queue.append(target_id)
        return visited

    @staticmethod
    def cached_result(dataset_id: str) -> Optional[Dict[str, Any]]:
        """Return the result persisted by a previous :meth:`verify` call.

        Reads ``result.json`` from the deterministic approvals directory
        for ``dataset_id`` (see :mod:`approval_tests_ir_datasets.paths`)
        *without* invoking any verifier. Returns ``None`` if ``verify`` has
        never been run for ``dataset_id`` yet, or if ``ir_datasets`` isn't
        installed.
        """
        try:
            from .paths import approvals_dir

            directory = approvals_dir(dataset_id)
        except ImportError:
            return None
        result_path = directory / "result.json"
        if not result_path.is_file():
            return None
        return json.loads(result_path.read_text())

    @staticmethod
    def _persist_results(dataset_id: str, results: Dict[str, Any]) -> None:
        """Best-effort write of ``results`` as JSON to the deterministic
        approvals directory for ``dataset_id``. Does nothing if
        ``ir_datasets`` isn't installed.
        """
        try:
            from .paths import approvals_dir

            directory = approvals_dir(dataset_id)
        except ImportError:
            return
        result_path = directory / "result.json"
        result_path.write_text(json.dumps(results, indent=2, sort_keys=True))


def verify(dataset_id: str) -> Dict[str, Any]:
    """Verify a dataset identifier.

    Delegates to :class:`IrDatasetsApprovalTest`, running every registered
    verifier plugin against ``dataset_id`` and returning their aggregated
    results (see :meth:`IrDatasetsApprovalTest.verify`). This always
    recomputes the result from scratch; use :func:`cached_result` to read
    back a previously persisted result without re-running the verifiers.

    Raises ``DatasetNotFoundError`` if ``dataset_id`` cannot be resolved --
    either because no such dataset exists, or because a verifier plugin's
    optional dependency (e.g. ``ir_datasets``) is not installed.
    """
    try:
        return IrDatasetsApprovalTest().verify(dataset_id)
    except (KeyError, ImportError) as exc:
        raise DatasetNotFoundError(f"Dataset '{dataset_id}' does not exist.") from exc


def cached_result(dataset_id: str) -> Optional[Dict[str, Any]]:
    """Return the result persisted by a previous :func:`verify` call.

    See :meth:`IrDatasetsApprovalTest.cached_result`. Returns ``None`` if
    ``verify`` has never been run for ``dataset_id`` yet, or if
    ``ir_datasets`` isn't installed.
    """
    return IrDatasetsApprovalTest.cached_result(dataset_id)


__all__ = [
    "DatasetNotFoundError",
    "IrDatasetsApprovalTest",
    "cached_result",
    "verify",
]
