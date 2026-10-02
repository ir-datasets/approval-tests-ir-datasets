"""Built-in verifier plugins for :class:`~approval_tests_ir_datasets.IrDatasetsApprovalTest`.

Each verifier here is registered under the
``approval_tests_ir_datasets.verifiers`` entry point group declared in
``pyproject.toml``.
"""
import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

#: Cached result of :func:`_tira_works` -- ``None`` until first checked,
#: then ``True``/``False`` for the remainder of the process.
_tira_installation_ok: Optional[bool] = None


def _tira_works() -> bool:
    """Checks, once per process, whether tira is correctly installed.

    Runs ``tira-cli verify-installation --local-only`` the first time this
    is called, caching whether it succeeded in a module-level variable; any
    later call (from this or another verifier) just returns that cached
    value instead of re-running the (slow, Docker-dependent) check again.

    If the check fails, a message pointing at the command above is printed
    to stdout, so a human running into a tira-backed verifier failing knows
    exactly what to run to diagnose it. Returns ``False`` in that case, so
    callers can fail fast with a clear error instead of letting tira-cli
    itself produce a more confusing one later.
    """
    global _tira_installation_ok
    if _tira_installation_ok is None:
        process = subprocess.run(
            ["tira-cli", "verify-installation", "--local-only"],
            capture_output=True,
            text=True,
        )
        _tira_installation_ok = process.returncode == 0
        if not _tira_installation_ok:
            print(
                "tira-cli verify-installation --local-only is failing -- please get "
                "it passing before using any tira-backed verifier.\n"
                f"--- tira-cli stdout ---\n{process.stdout}\n"
                f"--- tira-cli stderr ---\n{process.stderr}"
            )
    return _tira_installation_ok


class TableLineCountVerifier:
    """Counts the records of an ir_datasets v2 table resource.

    Loads ``dataset_id`` with ``ir_datasets.v2.load``. If the resolved node
    is a table (``irds:DocTable``, ``irds:QueryTable``, ``irds:QrelTable``,
    ...), a dict with the number of records it contains
    (``{"length": len(table)}``) is returned. For any other node type (e.g.
    a ``Benchmark`` or a raw ``Resource``), ``None`` is returned.
    """

    def verify(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        import ir_datasets.v2 as ir_datasets_v2
        from ir_datasets.v2.nodes import TABLE
        from ir_datasets.v2.vocabulary import is_subtype

        node = ir_datasets_v2.load(dataset_id)
        if not is_subtype(getattr(node, "type", None), TABLE):
            return None
        return {"length": len(node)}


class QrelTableStatsVerifier:
    """Computes basic statistics for an ir_datasets v2 qrels table.

    Loads ``dataset_id`` with ``ir_datasets.v2.load``. If the resolved node
    is not a ``QrelTable`` (``irds:QrelTable``), ``None`` is returned.
    Otherwise, returns a dict with:

    * ``"number_of_queries"`` -- the number of distinct query ids that have
      at least one qrel.
    * ``"relevance_counts"`` -- a dict mapping each relevance label to the
      absolute number of qrels records with that label.
    """

    def verify(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        import ir_datasets.v2 as ir_datasets_v2
        from ir_datasets.v2.nodes import TABLE_TYPES
        from ir_datasets.v2.vocabulary import is_subtype

        node = ir_datasets_v2.load(dataset_id)
        if not is_subtype(getattr(node, "type", None), TABLE_TYPES["qrels"]):
            return None

        query_ids = set()
        relevance_counts: Counter = Counter()
        for qrel in node:
            query_ids.add(qrel.query_id)
            # Stringified up front: an approved snapshot is round-tripped
            # through JSON, which only supports string object keys (an int
            # key like 1 comes back as "1") -- keeping relevance labels as
            # ints here would make every re-run spuriously "differ" from a
            # previously approved snapshot (a missing int key plus an
            # unexpected string key for the very same count).
            relevance_counts[str(qrel.relevance)] += 1

        return {
            "number_of_queries": len(query_ids),
            "relevance_counts": dict(relevance_counts),
        }


class PyTerrierIndexVerifier:
    """Builds a PyTerrier index for any ir_datasets v2 table whose records
    have text via TIRA.

    Loads ``dataset_id`` with ``ir_datasets.v2.load``. If the resolved
    node's record type doesn't expose a ``default_text()`` method -- i.e.
    it's not a table of texts (e.g. a document table, a query table, or any
    other table whose records have text), such as a qrels table or a
    non-table resource -- ``None`` is returned.

    Otherwise, the records are persisted to a ``documents.jsonl`` file in
    TIRA's "tirex" format (one JSON object per line with ``docno`` and
    ``text`` fields -- ``docno`` being each record's id, e.g. ``doc_id`` for
    a document table or ``query_id`` for a query table), and
    ``tira-cli run local --approach "ir-benchmarks/tira-ir-starter/Index
    (tira-ir-starter-pyterrier)"`` is invoked against them to build a
    PyTerrier index. Statistics parsed from the resulting index's
    ``data.properties`` file are returned as
    ``{"num_documents": ..., "num_terms": ..., "num_tokens": ...}``
    (``"num_documents"`` counting whatever kind of record was indexed, e.g.
    documents or queries).

    This requires the optional ``tira`` package, the ``tira-cli`` and
    ``docker`` commands, and access to a Docker daemon (as configured in
    this repository's dev container).

    All working directories (the input documents, the built index, and
    ``tira-cli``'s own scratch space) are created under the deterministic
    ``approvals_dir(dataset_id, "pyterrier_index")`` directory (see
    :mod:`approval_tests_ir_datasets.paths`), i.e. under ir_datasets' home
    directory, and are kept around after a successful run so the built
    index can be inspected/reused. This directory is cleared before each
    run to avoid stale state from a previous run leaking into the result.

    ``tira-cli run local`` requires this directory to be visible under the
    *same path* both inside this process and on the Docker host running
    the containers it starts. Point ``IR_DATASETS_HOME`` at a directory
    known to be host-visible (e.g. this repository's dev container
    bind-mounts ``/tmp`` 1:1 from the host and sets
    ``IR_DATASETS_HOME=/tmp/.ir_datasets``) if this doesn't hold by default.

    Use :meth:`cached_index_path` to look up a previously built index's
    directory without rebuilding it.

    ``verify`` accepts a ``recompute`` keyword (default ``False``): by
    default, an already-built index (found via :meth:`cached_index_path`)
    is reused as-is -- its stats are read from ``data.properties`` without
    invoking ``tira-cli`` again -- and the index is only (re)built if none
    exists yet. Pass ``recompute=True`` to always rebuild the index from
    scratch instead, as described above, regardless of what's already
    cached. Other verifiers that merely *depend on* an index (e.g.
    :class:`RetrievalVerifier`, which needs the *document* table's index
    to run retrieval against) call this with ``recompute=False`` (the
    default) explicitly, to make that dependency lookup clear at the call
    site.
    """

    APPROACH = "ir-benchmarks/tira-ir-starter/Index (tira-ir-starter-pyterrier)"

    def verify(self, dataset_id: str, recompute: bool = False) -> Optional[Dict[str, Any]]:
        import ir_datasets.v2 as ir_datasets_v2
        import tira  # noqa: F401 -- lazily required; propagates ImportError if missing.

        node = ir_datasets_v2.load(dataset_id)
        record_type = getattr(node, "record_type", None)
        if record_type is None or not hasattr(record_type, "default_text"):
            return None

        if not recompute:
            cached = self._cached_stats(dataset_id)
            if cached is not None:
                return cached

        return self._build_index(node, dataset_id)

    @classmethod
    def _cached_stats(cls, dataset_id: str) -> Optional[Dict[str, Any]]:
        """Read a previously built index's stats without rebuilding it.

        Returns ``None`` if no index has been built for ``dataset_id`` yet.
        """
        from .paths import approvals_dir

        properties_path = cls._find_data_properties(approvals_dir(dataset_id, "pyterrier_index"))
        if properties_path is None:
            return None
        return cls._stats_from_properties(cls._parse_properties(properties_path))

    @staticmethod
    def _stats_from_properties(properties: Dict[str, str]) -> Dict[str, Any]:
        return {
            "num_documents": int(properties["num.Documents"]),
            "num_terms": int(properties["num.Terms"]),
            "num_tokens": int(properties["num.Tokens"]),
        }

    @classmethod
    def cached_index_path(cls, dataset_id: str) -> Optional[Path]:
        """Return the directory of a previously built PyTerrier index.

        Looks up the deterministic ``approvals_dir(dataset_id,
        "pyterrier_index")`` directory (see
        :mod:`approval_tests_ir_datasets.paths`) for a ``data.properties``
        file, *without* invoking ``tira-cli``. Returns the directory
        containing it (the actual index), or ``None`` if no index has been
        built for ``dataset_id`` yet, or if ``ir_datasets`` isn't installed.
        """
        try:
            from .paths import approvals_dir

            scratch_root = approvals_dir(dataset_id, "pyterrier_index")
        except ImportError:
            return None
        properties_path = cls._find_data_properties(scratch_root)
        return properties_path.parent if properties_path is not None else None

    def _build_index(self, node: Any, dataset_id: str) -> Dict[str, Any]:
        import shutil

        from .paths import approvals_dir

        if not _tira_works():
            raise RuntimeError(
                "tira-cli verify-installation --local-only is failing -- "
                "see above for details."
            )

        scratch_root = approvals_dir(dataset_id, "pyterrier_index")
        # Rebuild from a clean slate every time, so a previous run (e.g.
        # against different documents) can't leak into this one.
        shutil.rmtree(scratch_root, ignore_errors=True)
        scratch_root.mkdir(parents=True, exist_ok=True)

        input_dir = scratch_root / "input"
        output_dir = scratch_root / "output"
        tmp_dir = scratch_root / "tmp"
        input_dir.mkdir()
        tmp_dir.mkdir()

        documents_path = input_dir / "documents.jsonl"
        id_field = node.record_type._fields[0]
        with documents_path.open("w") as documents_file:
            for record in node:
                documents_file.write(
                    json.dumps(
                        {"docno": getattr(record, id_field), "text": record.default_text()}
                    )
                    + "\n"
                )

        env = dict(os.environ)
        env["TMPDIR"] = str(tmp_dir)
        # "tira-cli run local" currently raises after the index is built
        # successfully, because it also tries to evaluate the run against
        # a *registered* TIRA dataset -- which a local documents
        # directory is not. The index itself is still produced, so the
        # non-zero exit code is intentionally ignored here. Its output is
        # captured (rather than left to print) and only surfaced below if
        # the index actually failed to materialize.
        process = subprocess.run(
            [
                "tira-cli",
                "run",
                "local",
                "--approach",
                self.APPROACH,
                "--input",
                str(input_dir),
                "--out",
                str(output_dir),
            ],
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

        properties_path = self._find_data_properties(scratch_root)
        if properties_path is None:
            raise RuntimeError(
                "tira-cli did not produce a PyTerrier index (no data.properties found).\n"
                f"--- tira-cli stdout ---\n{process.stdout}\n"
                f"--- tira-cli stderr ---\n{process.stderr}"
            )
        return self._stats_from_properties(self._parse_properties(properties_path))

    @staticmethod
    def _find_data_properties(root: Path) -> Optional[Path]:
        matches = sorted(root.rglob("data.properties"))
        return matches[0] if matches else None

    @staticmethod
    def _parse_properties(path: Path) -> Dict[str, str]:
        properties: Dict[str, str] = {}
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            properties[key] = value
        return properties


class DefaultTextVerifier:
    """Samples 2 deterministically chosen records' ``default_text()`` from
    any ir_datasets v2 table whose records have text.

    Loads ``dataset_id`` with ``ir_datasets.v2.load``. Like
    :class:`PyTerrierIndexVerifier`, if the resolved node's record type
    doesn't expose a ``default_text()`` method (e.g. it's a qrels table or
    a non-table resource), ``None`` is returned -- otherwise it applies to
    any table of texts (e.g. a document table or a query table).

    Which 2 records are picked is made independent of the table's
    iteration order (and therefore reproducible across runs/machines): each
    record's id (its record type's first field, e.g. ``doc_id`` or
    ``query_id``) is hashed with MD5, the records are sorted by that hash,
    and the first 2 (in that sorted order) are kept.

    Returns::

        {
            "samples": [
                {"id": ..., "text": ...},
                {"id": ..., "text": ...},
            ]
        }
    """

    #: Number of records sampled.
    SAMPLE_SIZE = 2

    def verify(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        import ir_datasets.v2 as ir_datasets_v2

        node = ir_datasets_v2.load(dataset_id)
        record_type = getattr(node, "record_type", None)
        if record_type is None or not hasattr(record_type, "default_text"):
            return None

        id_field = record_type._fields[0]
        sampled = self._sample(node, id_field)

        return {
            "samples": [
                {"id": getattr(record, id_field), "text": record.default_text()}
                for record in sampled
            ]
        }

    @classmethod
    def _sample(cls, node: Any, id_field: str) -> List[Any]:
        import hashlib

        def md5_of_id(record: Any) -> str:
            return hashlib.md5(str(getattr(record, id_field)).encode("utf-8")).hexdigest()

        return sorted(node, key=md5_of_id)[: cls.SAMPLE_SIZE]


class RetrievalVerifier:
    """Runs several retrieval pipelines for an ir_datasets v2 benchmark via TIRA.

    Loads ``dataset_id`` with ``ir_datasets.v2.load``. If the resolved node
    doesn't have both a document table and a query table (e.g. it's just a
    ``DocTable`` or ``QueryTable`` on its own, or a benchmark without
    queries), ``None`` is returned.

    Otherwise:

    1. The document table's PyTerrier index is (re)built via
       :class:`PyTerrierIndexVerifier` (see its docstring).
    2. The queries are persisted as ``queries.xml`` (TREC topics format, as
       expected by the retrieval software) under the deterministic
       ``approvals_dir(dataset_id, "retrieval")`` directory.
    3. Each of :attr:`APPROACHES` (5 ``tira-ir-starter-pyterrier`` retrieval
       approaches: BM25, DirichletLM, DPH, Hiemstra_LM and PL2) is run
       directly against the persisted queries, with the PyTerrier index
       from step 1 passed in as its input run (``$inputRun``), each
       producing its own TREC run file (``run.txt``).

    Returns::

        {
            "num_queries": ...,
            "runs": {
                "BM25": {"num_results": ...},
                "DirichletLM": {
                    "num_results": ...,
                    "jaccard_similarity_to_bm25": {"top_10": ..., "top_100": ...},
                },
                "DPH": {...},
                "Hiemstra_LM": {...},
                "PL2": {...},
            },
        }

    ``"num_results"`` is the total number of result lines in that
    approach's run file. ``"jaccard_similarity_to_bm25"`` (omitted for BM25
    itself, which is the reference) is the Jaccard similarity between that
    approach's and BM25's retrieved documents, per query, averaged over all
    queries -- computed separately over each query's top 10 and top 100
    results (see :meth:`_jaccard_similarity`).

    This requires the optional ``tira`` package, the ``docker`` command,
    and access to a Docker daemon (as configured in this repository's dev
    container). Like :class:`PyTerrierIndexVerifier`, all working
    directories are created under ir_datasets' home directory and must be
    host-visible (see that class' docstring for details), and are kept
    around after a successful run -- cleared before each rebuild. Use
    :meth:`cached_run_path` to look up a previously produced run file
    without rebuilding it.

    Each approach's TIRA execution (image pulling, container logs,
    PyTerrier's own startup output, ...) prints a lot of diagnostic noise
    directly to stdout/stderr; this is captured and suppressed on success,
    and only surfaced (as part of the raised error) if that approach fails
    to produce a run file.

    ``verify`` accepts a ``recompute`` keyword (default ``False``): by
    default, already-cached runs (found via :meth:`cached_run_path`) are
    reused as-is -- read back from their run files without rerunning
    anything -- and retrieval is only (re)run if at least one approach
    isn't cached yet. Pass ``recompute=True`` to always rerun every
    approach from scratch instead, as described above. Regardless of this
    verifier's own ``recompute``, its dependency on the document table's
    PyTerrier index (built via :class:`PyTerrierIndexVerifier`) always
    uses ``recompute=False`` -- reusing whatever index is already there
    rather than forcing yet another rebuild -- since that's just a
    dependency lookup, not this verifier's own freshness obligation. Other
    verifiers that merely *depend on* retrieval's runs (e.g. an evaluation
    verifier computing metrics against them) should likewise call this
    with ``recompute=False`` (the default).
    """

    #: The 5 retrieval approaches run by :meth:`verify`. The first entry is
    #: the reference approach that every other approach's results are
    #: compared against via Jaccard similarity.
    APPROACHES = (
        "ir-benchmarks/tira-ir-starter/BM25 (tira-ir-starter-pyterrier)",
        "ir-benchmarks/tira-ir-starter/DirichletLM (tira-ir-starter-pyterrier)",
        "ir-benchmarks/tira-ir-starter/DPH (tira-ir-starter-pyterrier)",
        "ir-benchmarks/tira-ir-starter/Hiemstra_LM (tira-ir-starter-pyterrier)",
        "ir-benchmarks/tira-ir-starter/PL2 (tira-ir-starter-pyterrier)",
    )
    #: Rank cutoffs the Jaccard similarity to the reference approach is
    #: computed at.
    SIMILARITY_CUTOFFS = (10, 100)

    #: Backwards-compatible alias for the reference approach (previously
    #: the only approach this verifier ran).
    APPROACH = APPROACHES[0]

    @classmethod
    def _approach_name(cls, approach: str) -> str:
        """The short, human-readable name of an approach (e.g. ``"BM25"``
        for ``"ir-benchmarks/tira-ir-starter/BM25
        (tira-ir-starter-pyterrier)"``), used as a dict key and as a path
        segment.
        """
        software = approach.split("/")[-1]
        return software.split(" (")[0]

    def verify(self, dataset_id: str, recompute: bool = False) -> Optional[Dict[str, Any]]:
        import ir_datasets.v2 as ir_datasets_v2
        import tira  # noqa: F401 -- lazily required; propagates ImportError if missing.

        node = ir_datasets_v2.load(dataset_id)
        has = getattr(node, "has", None)
        if not callable(has) or not (has("docs") and has("queries")):
            return None

        if not recompute:
            cached = self._cached_result(node, dataset_id)
            if cached is not None:
                return cached

        return self._run_retrieval(node, dataset_id)

    def _cached_result(self, node: Any, dataset_id: str) -> Optional[Dict[str, Any]]:
        """Read back already-cached runs without rerunning anything.

        Returns ``None`` (rather than a partial result) if even one
        approach isn't cached yet, so the caller falls back to running
        retrieval for all of them.
        """
        run_paths: Dict[str, Path] = {}
        for approach in self.APPROACHES:
            run_path = self.cached_run_path(dataset_id, approach)
            if run_path is None:
                return None
            run_paths[self._approach_name(approach)] = run_path

        num_queries = sum(1 for _ in node.queries)
        return self._build_result(run_paths, num_queries)

    def _run_retrieval(self, node: Any, dataset_id: str) -> Dict[str, Any]:
        import shutil

        from tira.rest_api_client import Client

        from .paths import approvals_dir, sanitize_path_component

        if not _tira_works():
            raise RuntimeError(
                "tira-cli verify-installation --local-only is failing -- "
                "see above for details."
            )

        docs_dataset_id = node.docs.qualified_name

        # The document index is just a dependency here, not this verifier's
        # own freshness obligation -- reuse it if already built (e.g. by a
        # direct top-level verify() of the document table itself), only
        # building it if it doesn't exist yet.
        PyTerrierIndexVerifier().verify(docs_dataset_id, recompute=False)
        index_dir = PyTerrierIndexVerifier().cached_index_path(docs_dataset_id)
        if index_dir is None:
            raise RuntimeError(
                f"PyTerrierIndexVerifier did not produce an index for '{docs_dataset_id}'."
            )
        # pyterrier_cli.py appends "/index" to the directory it is given, so
        # the directory *containing* the "index" directory must be passed.
        input_run_dir = index_dir.parent

        scratch_root = approvals_dir(dataset_id, "retrieval")
        # Rebuild from a clean slate every time, so a previous run can't
        # leak into this one.
        shutil.rmtree(scratch_root, ignore_errors=True)
        scratch_root.mkdir(parents=True, exist_ok=True)

        input_dir = scratch_root / "input"
        input_dir.mkdir()

        num_queries = self._write_queries(node.queries, dataset_id, input_dir / "queries.xml")

        client = Client()

        run_paths: Dict[str, Path] = {}
        for approach in self.APPROACHES:
            name = self._approach_name(approach)
            output_dir = scratch_root / sanitize_path_component(name) / "output"
            output_dir.mkdir(parents=True)

            run_path = self._run_approach(client, approach, name, input_dir, output_dir, input_run_dir)
            run_paths[name] = run_path

        return self._build_result(run_paths, num_queries)

    def _build_result(self, run_paths: Dict[str, Path], num_queries: int) -> Dict[str, Any]:
        reference_name = self._approach_name(self.APPROACHES[0])
        reference_run = self._read_run(run_paths[reference_name])

        runs: Dict[str, Any] = {}
        for approach in self.APPROACHES:
            name = self._approach_name(approach)
            run_path = run_paths[name]
            result: Dict[str, Any] = {
                "num_results": sum(1 for _ in run_path.open()),
            }
            if name != reference_name:
                run = self._read_run(run_path)
                result["jaccard_similarity_to_bm25"] = {
                    f"top_{k}": self._jaccard_similarity(reference_run, run, k)
                    for k in self.SIMILARITY_CUTOFFS
                }
            runs[name] = result

        return {
            "num_queries": num_queries,
            "runs": runs,
        }

    @staticmethod
    def _run_approach(
        client: Any,
        approach: str,
        name: str,
        input_dir: Path,
        output_dir: Path,
        input_run_dir: Path,
    ) -> Path:
        """Run a single retrieval approach via TIRA, returning its run file.

        The TIRA client (and the container it runs) prints a lot of
        diagnostic noise directly to stdout/stderr (docker image pulling,
        PyTerrier's own startup banter, streamed container logs, ...). This
        is captured rather than left to print, and only surfaced (appended
        to the raised error) if the approach actually fails to produce a
        run file -- a successful run stays silent.
        """
        import contextlib
        import io

        captured_stdout = io.StringIO()
        captured_stderr = io.StringIO()
        run_path = output_dir / "run.txt"
        try:
            with contextlib.redirect_stdout(captured_stdout), contextlib.redirect_stderr(
                captured_stderr
            ):
                team, software = approach.split("/")[1:]
                system_details = client.public_system_details(team, software)
                image = system_details.get("public_image_name") or system_details["tira_image_name"]

                client.local_execution.run(
                    image=image,
                    command=system_details["command"],
                    input_dir=input_dir,
                    output_dir=output_dir,
                    input_run=input_run_dir,
                    allow_network=False,
                    forward_environment_variables=system_details.get(
                        "forward_environment_variable"
                    ),
                )
        except Exception as exc:
            raise RuntimeError(
                f"Running the '{name}' retrieval software failed.\n"
                f"--- stdout ---\n{captured_stdout.getvalue()}\n"
                f"--- stderr ---\n{captured_stderr.getvalue()}"
            ) from exc

        if not run_path.is_file():
            raise RuntimeError(
                f"The '{name}' retrieval software did not produce a run file at {run_path}.\n"
                f"--- stdout ---\n{captured_stdout.getvalue()}\n"
                f"--- stderr ---\n{captured_stderr.getvalue()}"
            )
        return run_path

    @staticmethod
    def _read_run(path: Path) -> Dict[str, List[str]]:
        """Parse a TREC run file into ``{query_id: [doc_id, ...]}``, each
        query's doc ids ordered by increasing rank (i.e. best-first).
        """
        ranked: Dict[str, List[tuple]] = {}
        for line in path.open():
            fields = line.split()
            if len(fields) < 4:
                continue
            query_id, _, doc_id, rank = fields[:4]
            ranked.setdefault(query_id, []).append((int(rank), doc_id))
        return {
            query_id: [doc_id for _, doc_id in sorted(docs)]
            for query_id, docs in ranked.items()
        }

    @staticmethod
    def _jaccard_similarity(run_a: Dict[str, List[str]], run_b: Dict[str, List[str]], k: int) -> float:
        """The Jaccard similarity of ``run_a`` and ``run_b``'s top ``k``
        results, per query, averaged over every query present in either run.

        A query missing from one of the runs is treated as having no
        results for it. Queries with no results in *either* run (e.g. both
        top-k sets are empty) contribute a similarity of ``1.0`` (both
        agree on nothing).
        """
        query_ids = set(run_a) | set(run_b)
        if not query_ids:
            return 0.0

        similarities = []
        for query_id in query_ids:
            top_a = set(run_a.get(query_id, [])[:k])
            top_b = set(run_b.get(query_id, [])[:k])
            union = top_a | top_b
            similarities.append(1.0 if not union else len(top_a & top_b) / len(union))
        return sum(similarities) / len(similarities)

    @classmethod
    def cached_run_path(cls, dataset_id: str, approach: Optional[str] = None) -> Optional[Path]:
        """Return the run file of a previously executed retrieval.

        Looks up the deterministic ``approvals_dir(dataset_id, "retrieval",
        ...)`` directory (see :mod:`approval_tests_ir_datasets.paths`) for
        the given ``approach``'s (default: the reference approach, BM25)
        ``run.txt`` file, *without* invoking the retrieval software again.
        Returns ``None`` if no retrieval has been run for ``dataset_id`` (or
        for that specific ``approach``) yet, or if ``ir_datasets`` isn't
        installed.
        """
        if approach is None:
            approach = cls.APPROACHES[0]
        try:
            from .paths import approvals_dir, sanitize_path_component

            name = cls._approach_name(approach)
            scratch_root = approvals_dir(dataset_id, "retrieval", sanitize_path_component(name))
        except ImportError:
            return None
        run_path = scratch_root / "output" / "run.txt"
        return run_path if run_path.is_file() else None

    @staticmethod
    def _write_queries(queries: Any, dataset_id: str, path: Path) -> int:
        import xml.etree.ElementTree as ET

        root = ET.Element("topics", attrib={"ir-datasets-id": dataset_id})
        num_queries = 0
        for query in queries:
            topic = ET.SubElement(root, "topic", attrib={"number": str(query.query_id)})
            query_element = ET.SubElement(topic, "query")
            query_element.text = query.default_text()
            num_queries += 1
        ET.ElementTree(root).write(path, encoding="unicode")
        return num_queries


class EvaluationVerifier:
    """Evaluates :class:`RetrievalVerifier`'s cached runs against qrels.

    Loads ``dataset_id`` with ``ir_datasets.v2.load``. If the resolved node
    doesn't have a document table, a query table, *and* a qrels table (e.g.
    it's just a bare ``DocTable``/``QueryTable``, or a benchmark without
    qrels), ``None`` is returned.

    Otherwise, :class:`RetrievalVerifier` is queried for its cached runs
    (via ``RetrievalVerifier().verify(dataset_id, recompute=False)`` --
    reusing whatever's already cached rather than forcing a redundant
    rerun of all 5 approaches; only computed if nothing is cached yet),
    and each of its :attr:`~RetrievalVerifier.APPROACHES`' run files is
    then looked up via :meth:`RetrievalVerifier.cached_run_path`.

    Each cached run is evaluated against ``dataset_id``'s qrels using
    ``ir_measures`` for nDCG@10, recip_rank (mean reciprocal rank) and
    Recall@100. Returns::

        {
            "BM25": {"nDCG@10": ..., "recip_rank": ..., "Recall@100": ...},
            "DirichletLM": {...},
            "DPH": {...},
            "Hiemstra_LM": {...},
            "PL2": {...},
        }

    This requires the optional ``ir_measures`` package.

    ``verify`` accepts a ``recompute`` keyword (default ``False``) for
    interface consistency with the other verifiers, but this verifier has
    no cached artifact of its own (evaluating already-retrieved runs
    against qrels is cheap) -- it never forces :class:`RetrievalVerifier`
    to rerun, regardless of its own ``recompute`` value; use
    ``RetrievalVerifier().verify(dataset_id, recompute=True)`` directly to
    force a fresh retrieval before evaluating it.
    """

    #: The metrics reported for every run, keyed by their result dict key.
    MEASURES = {"nDCG@10": "nDCG@10", "recip_rank": "RR", "Recall@100": "Recall@100"}

    def verify(self, dataset_id: str, recompute: bool = False) -> Optional[Dict[str, Any]]:
        import ir_datasets.v2 as ir_datasets_v2

        node = ir_datasets_v2.load(dataset_id)
        has = getattr(node, "has", None)
        if not callable(has) or not (has("docs") and has("queries") and has("qrels")):
            return None

        return self._evaluate(node, dataset_id)

    def _evaluate(self, node: Any, dataset_id: str) -> Dict[str, Any]:
        import ir_measures

        # A dependency lookup, not this verifier's own freshness
        # obligation -- reuse whatever's cached, only computing it if
        # nothing is cached yet (see RetrievalVerifier.verify's docstring).
        RetrievalVerifier().verify(dataset_id, recompute=False)

        qrels = list(node.qrels)
        measures = [ir_measures.parse_measure(measure) for measure in self.MEASURES.values()]

        results: Dict[str, Any] = {}
        for approach in RetrievalVerifier.APPROACHES:
            name = RetrievalVerifier._approach_name(approach)
            run_path = RetrievalVerifier.cached_run_path(dataset_id, approach)
            if run_path is None:
                raise RuntimeError(
                    f"RetrievalVerifier did not produce a cached run for approach "
                    f"'{name}' on '{dataset_id}'."
                )
            run = ir_measures.read_trec_run(str(run_path))
            aggregate = ir_measures.calc_aggregate(measures, qrels, run)
            results[name] = {
                metric_name: aggregate[ir_measures.parse_measure(measure_str)]
                for metric_name, measure_str in self.MEASURES.items()
            }
        return results


__all__ = [
    "DefaultTextVerifier",
    "EvaluationVerifier",
    "PyTerrierIndexVerifier",
    "QrelTableStatsVerifier",
    "RetrievalVerifier",
    "TableLineCountVerifier",
]
