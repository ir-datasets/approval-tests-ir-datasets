"""Built-in verifier plugins for :class:`~approval_tests_ir_datasets.IrDatasetsApprovalTest`.

Each verifier here is registered under the
``approval_tests_ir_datasets.verifiers`` entry point group declared in
``pyproject.toml``.
"""
import json
import os
import subprocess
import tempfile
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
    this repository's dev container). ``tira-cli run local`` also requires
    a scratch directory that is visible under the *same path* both inside
    this process and on the Docker host running the containers it starts.
    By default this uses the system temp directory (``/tmp``), which the
    dev container bind-mounts 1:1 from the host for exactly this reason;
    set the ``APPROVAL_TESTS_IR_DATASETS_SCRATCH_DIR`` environment variable
    to override this with a different directory known to be host-visible.
    """

    APPROACH = "ir-benchmarks/tira-ir-starter/Index (tira-ir-starter-pyterrier)"
    SCRATCH_DIR_ENV_VAR = "APPROVAL_TESTS_IR_DATASETS_SCRATCH_DIR"

    def verify(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        import ir_datasets.v2 as ir_datasets_v2
        import tira  # noqa: F401 -- lazily required; propagates ImportError if missing.
        from ir_datasets.v2.nodes import TABLE_TYPES
        from ir_datasets.v2.vocabulary import is_subtype

        node = ir_datasets_v2.load(dataset_id)
        if not is_subtype(getattr(node, "type", None), TABLE_TYPES["docs"]):
            return None

        return self._build_index(node)

    def _build_index(self, node: Any) -> Dict[str, Any]:
        import shutil

        scratch_parent = os.environ.get(self.SCRATCH_DIR_ENV_VAR, tempfile.gettempdir())
        scratch_root = Path(tempfile.mkdtemp(prefix="tirex-", dir=scratch_parent))
        try:
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
            # non-zero exit code is intentionally ignored here.
            subprocess.run(
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
            )

            properties_path = self._find_data_properties(scratch_root)
            if properties_path is None:
                raise RuntimeError(
                    "tira-cli did not produce a PyTerrier index (no data.properties found)."
                )
            properties = self._parse_properties(properties_path)

            return {
                "num_documents": int(properties["num.Documents"]),
                "num_terms": int(properties["num.Terms"]),
                "num_tokens": int(properties["num.Tokens"]),
            }
        finally:
            shutil.rmtree(scratch_root, ignore_errors=True)

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


__all__ = ["PyTerrierIndexVerifier", "QrelTableStatsVerifier", "TableLineCountVerifier"]
