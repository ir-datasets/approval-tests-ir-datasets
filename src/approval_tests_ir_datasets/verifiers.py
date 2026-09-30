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
from typing import Any, Dict, Optional


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
    """Builds a PyTerrier index for an ir_datasets v2 document table via TIRA.

    Loads ``dataset_id`` with ``ir_datasets.v2.load``. If the resolved node
    is not a document table (``irds:DocTable``), ``None`` is returned.

    Otherwise, the documents are persisted to a ``documents.jsonl`` file in
    TIRA's "tirex" format (one JSON object per line with ``docno`` and
    ``text`` fields), and
    ``tira-cli run local --approach "ir-benchmarks/tira-ir-starter/Index
    (tira-ir-starter-pyterrier)"`` is invoked against them to build a
    PyTerrier index. Statistics parsed from the resulting index's
    ``data.properties`` file are returned as
    ``{"num_documents": ..., "num_terms": ..., "num_tokens": ...}``.

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
        from ir_datasets.v2.nodes import TABLE_TYPES
        from ir_datasets.v2.vocabulary import is_subtype

        node = ir_datasets_v2.load(dataset_id)
        if not is_subtype(getattr(node, "type", None), TABLE_TYPES["docs"]):
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
        with documents_path.open("w") as documents_file:
            for doc in node:
                documents_file.write(
                    json.dumps({"docno": doc.doc_id, "text": doc.default_text()}) + "\n"
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
    """Runs a full BM25 retrieval pipeline for an ir_datasets v2 benchmark via TIRA.

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
    3. ``tira-ir-starter-pyterrier``'s BM25 retrieval software is run
       directly against the persisted queries, with the PyTerrier index
       from step 1 passed in as its input run (``$inputRun``), producing a
       TREC run file (``run.txt``).

    Returns ``{"num_queries": ..., "num_results": ...}``, counting the
    queries retrieved for and the total number of result lines across all
    of them.

    This requires the optional ``tira`` package, the ``docker`` command,
    and access to a Docker daemon (as configured in this repository's dev
    container). Like :class:`PyTerrierIndexVerifier`, all working
    directories are created under ir_datasets' home directory and must be
    host-visible (see that class' docstring for details), and are kept
    around after a successful run -- cleared before each rebuild. Use
    :meth:`cached_run_path` to look up a previously produced run file
    without rebuilding it.
    """

    APPROACH = "ir-benchmarks/tira-ir-starter/BM25 (tira-ir-starter-pyterrier)"

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

        from .paths import approvals_dir

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
        output_dir = scratch_root / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        num_queries = self._write_queries(node.queries, dataset_id, input_dir / "queries.xml")

        client = Client()
        team, software = self.APPROACH.split("/")[1:]
        system_details = client.public_system_details(team, software)
        image = system_details.get("public_image_name") or system_details["tira_image_name"]

        client.local_execution.run(
            image=image,
            command=system_details["command"],
            input_dir=input_dir,
            output_dir=output_dir,
            input_run=input_run_dir,
            allow_network=False,
            forward_environment_variables=system_details.get("forward_environment_variable"),
        )

        run_path = output_dir / "run.txt"
        if not run_path.is_file():
            raise RuntimeError(f"The retrieval software did not produce a run file at {run_path}.")

        return {
            "num_queries": num_queries,
            "num_results": sum(1 for _ in run_path.open()),
        }

    @classmethod
    def cached_run_path(cls, dataset_id: str) -> Optional[Path]:
        """Return the run file of a previously executed retrieval.

        Looks up the deterministic ``approvals_dir(dataset_id, "retrieval")``
        directory (see :mod:`approval_tests_ir_datasets.paths`) for a
        ``run.txt`` file, *without* invoking the retrieval software again.
        Returns ``None`` if no retrieval has been run for ``dataset_id`` yet,
        or if ``ir_datasets`` isn't installed.
        """
        try:
            from .paths import approvals_dir

            scratch_root = approvals_dir(dataset_id, "retrieval")
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
