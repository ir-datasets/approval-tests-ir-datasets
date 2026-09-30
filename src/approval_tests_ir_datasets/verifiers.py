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
            relevance_counts[qrel.relevance] += 1

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
    """

    APPROACH = "ir-benchmarks/tira-ir-starter/Index (tira-ir-starter-pyterrier)"

    def verify(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        import ir_datasets.v2 as ir_datasets_v2
        import tira  # noqa: F401 -- lazily required; propagates ImportError if missing.

        node = ir_datasets_v2.load(dataset_id)
        record_type = getattr(node, "record_type", None)
        if record_type is None or not hasattr(record_type, "default_text"):
            return None

        return self._build_index(node, dataset_id)

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
        properties = self._parse_properties(properties_path)

        return {
            "num_documents": int(properties["num.Documents"]),
            "num_terms": int(properties["num.Terms"]),
            "num_tokens": int(properties["num.Tokens"]),
        }

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

    def verify(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        import ir_datasets.v2 as ir_datasets_v2
        import tira  # noqa: F401 -- lazily required; propagates ImportError if missing.

        node = ir_datasets_v2.load(dataset_id)
        has = getattr(node, "has", None)
        if not callable(has) or not (has("docs") and has("queries")):
            return None

        return self._run_retrieval(node, dataset_id)

    def _run_retrieval(self, node: Any, dataset_id: str) -> Dict[str, Any]:
        import shutil

        from tira.rest_api_client import Client

        from .paths import approvals_dir, sanitize_path_component

        docs_dataset_id = node.docs.qualified_name

        # Always (re)build the index from scratch, consistent with the
        # top-level contract that every verify() call recomputes its result.
        PyTerrierIndexVerifier().verify(docs_dataset_id)
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

            run_path = output_dir / "run.txt"
            if not run_path.is_file():
                raise RuntimeError(
                    f"The '{name}' retrieval software did not produce a run file at {run_path}."
                )
            run_paths[name] = run_path

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


__all__ = [
    "PyTerrierIndexVerifier",
    "QrelTableStatsVerifier",
    "RetrievalVerifier",
    "TableLineCountVerifier",
]
