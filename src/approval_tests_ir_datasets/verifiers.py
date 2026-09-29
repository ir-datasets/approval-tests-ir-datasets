"""Built-in verifier plugins for :class:`~approval_tests_ir_datasets.IrDatasetsApprovalTest`.

Each verifier here is registered under the
``approval_tests_ir_datasets.verifiers`` entry point group declared in
``pyproject.toml``.
"""
from collections import Counter
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


__all__ = ["QrelTableStatsVerifier", "TableLineCountVerifier"]
