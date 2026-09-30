import contextlib
import importlib.metadata
import inspect
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from . import hf_local_provider as _hf_local_provider
from .hf_local import local_hf_repo

#: Registering "hf-local:" only needs importing this module -- see its own
#: docstring. Calling this here (rather than relying solely on the module's
#: own import-time call) makes the dependency explicit and keeps it
#: idempotent/no-op if ir_datasets isn't installed.
_hf_local_provider.register()

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
    silently skipped if ``ir_datasets`` isn't installed. By default, every
    call to :meth:`verify` re-runs all verifiers from scratch and overwrites
    this persisted result (see ``recompute``); use :meth:`cached_result` to
    read it back without triggering a re-run.
    """

    def verify(
        self,
        dataset_id: str,
        recompute: bool = True,
        render_as_html: bool = False,
        hf_local_dir: Optional[Union[str, Path]] = None,
    ) -> Dict[str, Any]:
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
        being persisted for ``dataset_id`` itself.

        ``recompute`` (default ``True``) is forwarded as a ``recompute``
        keyword to every verifier whose own ``verify(dataset_id, ...)``
        method accepts one (e.g. :class:`~approval_tests_ir_datasets.verifiers.PyTerrierIndexVerifier`,
        :class:`~approval_tests_ir_datasets.verifiers.RetrievalVerifier` and
        :class:`~approval_tests_ir_datasets.verifiers.EvaluationVerifier`,
        which cache expensive artifacts such as a built index or a
        retrieval run) -- verifiers without a ``recompute`` parameter (e.g.
        :class:`~approval_tests_ir_datasets.verifiers.TableLineCountVerifier`)
        are simply called as before, since they have nothing to cache.
        With ``recompute=True`` (the default), every verifier always
        recomputes its result from scratch, e.g. rebuilding
        ``PyTerrierIndexVerifier``'s index, exactly as before this
        parameter existed. Pass ``recompute=False`` to instead reuse
        whatever each verifier already has cached (see each verifier's own
        docstring for what "cached" means to it), only computing it if
        nothing is cached yet -- this can turn a slow, Docker/TIRA-backed
        re-verification into a cheap read of previously produced results
        (e.g. when only regenerating the HTML report via
        ``render_as_html`` for an already-verified dataset).

        If ``render_as_html`` is ``True``, the aggregated result is also
        rendered as a single, self-contained HTML report (see
        :mod:`approval_tests_ir_datasets.report`) and written to a freshly
        created temporary directory, ready to be opened directly in a
        browser. The report reuses `ir-datasets.com
        <https://ir-datasets.com>`_'s own look and feel (its Tabler-based
        CSS/JS, fetched from the same CDN/site it uses, rather than a
        vendored copy) so it looks at home next to it. The written file's
        path is returned as the result dict's ``"__html_report__"`` key (in
        addition to being printed to stdout for convenience) -- this key is
        only ever present when ``render_as_html`` is ``True``.

        If ``hf_local_dir`` is given, ``dataset_id`` must be an ``hf:``
        (Hugging Face Hub) id, and it is resolved against this local
        directory instead of the real Hub for the duration of this call
        (see :func:`approval_tests_ir_datasets.hf_local.local_hf_repo`) --
        useful for verifying a dataset card and data files persisted on
        disk (e.g. a test fixture) without any network access.
        """
        with self._hf_local_context(dataset_id, hf_local_dir):
            dataset_ids = self._collect_dataset_ids(dataset_id)

            if len(dataset_ids) == 1:
                results = self._run_verifiers(dataset_id, recompute=recompute)
            else:
                results = {}
                for sub_dataset_id in dataset_ids:
                    sub_results = self._run_verifiers(sub_dataset_id, recompute=recompute)
                    results[sub_dataset_id] = sub_results
                    if sub_dataset_id != dataset_id:
                        self._persist_results(sub_dataset_id, sub_results)

            self._persist_results(dataset_id, results)

        if render_as_html:
            report_path = self._render_html_report(dataset_id, dataset_ids, results)
            print(f"approval_tests_ir_datasets: wrote HTML report to {report_path}")
            results["__html_report__"] = str(report_path)

        return results

    @staticmethod
    def _render_html_report(dataset_id: str, dataset_ids: List[str], results: Dict[str, Any]):
        from .report import write_html_report

        return write_html_report(dataset_id, dataset_ids, results)

    @staticmethod
    def _hf_local_context(dataset_id: str, hf_local_dir: Optional[Union[str, Path]]):
        """A context manager resolving ``dataset_id`` against
        ``hf_local_dir`` on disk for its duration, or a no-op context if
        ``hf_local_dir`` is ``None``. Raises ``ValueError`` if
        ``hf_local_dir`` is given but ``dataset_id`` isn't an ``hf:`` id.
        """
        if hf_local_dir is None:
            return contextlib.nullcontext()
        if not dataset_id.startswith("hf:"):
            raise ValueError(
                f"hf_local_dir was given, but {dataset_id!r} is not an 'hf:' dataset id"
            )
        from ir_datasets.v2 import hf_provider as hfm

        repo, _revision, _fragment = hfm._parse_spec(dataset_id[len("hf:") :])
        return local_hf_repo(repo, hf_local_dir)

    @staticmethod
    def _run_verifiers(dataset_id: str, recompute: bool = True) -> Dict[str, Any]:
        """Run every registered verifier against a single ``dataset_id``.

        Returns a dict mapping each verifier's entry point name to the
        result of its ``verify(dataset_id)`` call. Verifiers that return
        ``None`` (e.g. because the dataset isn't the kind of resource they
        apply to) are omitted from the result. ``recompute`` is forwarded
        to each verifier's ``verify`` call as a ``recompute`` keyword, but
        only if that verifier's ``verify`` method actually declares one
        (see :meth:`verify`'s docstring); verifiers without one are called
        with just ``dataset_id``, unaffected by ``recompute``.
        """
        results: Dict[str, Any] = {}
        for entry_point in _discover_verifiers():
            verifier_cls = entry_point.load()
            verifier = verifier_cls()
            result = IrDatasetsApprovalTest._call_verifier(verifier, dataset_id, recompute)
            if result is not None:
                results[entry_point.name] = result
        return results

    @staticmethod
    def _call_verifier(verifier: Any, dataset_id: str, recompute: bool) -> Any:
        """Call ``verifier.verify(dataset_id)``, additionally passing
        ``recompute`` as a keyword if (and only if) ``verifier.verify``
        declares a ``recompute`` parameter.
        """
        try:
            parameters = inspect.signature(verifier.verify).parameters
        except (TypeError, ValueError):
            parameters = {}
        if "recompute" in parameters:
            return verifier.verify(dataset_id, recompute=recompute)
        return verifier.verify(dataset_id)

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


def verify(
    dataset_id: str,
    recompute: bool = True,
    render_as_html: bool = False,
    hf_local_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Verify a dataset identifier.

    Delegates to :class:`IrDatasetsApprovalTest`, running every registered
    verifier plugin against ``dataset_id`` and returning their aggregated
    results (see :meth:`IrDatasetsApprovalTest.verify`).

    ``recompute`` (default ``True``) is forwarded to every verifier that
    accepts it, e.g. ``False`` reuses an already-built PyTerrier index or
    already-computed retrieval runs instead of rebuilding them from
    scratch; see :meth:`IrDatasetsApprovalTest.verify`'s docstring for
    details. Use :func:`cached_result` to read back a previously persisted
    *aggregated* result without re-running any verifier at all.

    If ``render_as_html`` is ``True``, the result is additionally rendered
    as a self-contained HTML report and written to a temporary directory
    (see :meth:`IrDatasetsApprovalTest.verify`'s docstring); the written
    file's path is both printed and available as the result dict's
    ``"__html_report__"`` key.

    If ``hf_local_dir`` is given, ``dataset_id`` must be an ``hf:`` id, and
    it is resolved against this local directory instead of the real
    Hugging Face Hub (see :func:`approval_tests_ir_datasets.hf_local.local_hf_repo`).

    Raises ``DatasetNotFoundError`` if ``dataset_id`` cannot be resolved --
    either because no such dataset exists, or because a verifier plugin's
    optional dependency (e.g. ``ir_datasets``) is not installed.
    """
    try:
        return IrDatasetsApprovalTest().verify(
            dataset_id,
            recompute=recompute,
            render_as_html=render_as_html,
            hf_local_dir=hf_local_dir,
        )
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
    "local_hf_repo",
    "verify",
]
