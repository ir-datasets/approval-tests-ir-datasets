"""Comparing a freshly computed :func:`~approval_tests_ir_datasets.verify`
result against a previously *approved* one (see
:func:`approval_tests_ir_datasets.paths.approved_dir` and ``verify``'s
``wait_for_approval`` parameter), so "does this new result differ from what
a human already signed off on" can be decided by data *type*, not naive
equality:

* integers and strings must match *exactly*;
* floats match if they're within :data:`FLOAT_ABS_TOLERANCE` (``0.0001``) of
  each other -- verifiers routinely produce numbers with meaningless
  binary-floating-point/library-version noise past the fourth decimal (e.g.
  an nDCG@10 score), which exact equality would flag as a spurious
  difference;
* dicts/lists are compared recursively, key/index-wise -- a missing/extra
  key or a length mismatch is itself reported as a difference;
* anything else (``None``, ``bool``, ...) falls back to plain ``==``, with
  one wrinkle: ``bool`` is deliberately *not* treated as interchangeable
  with ``int`` (unlike Python's own ``==``, where ``True == 1``), since an
  approval test comparing e.g. ``{"is_pinned": True}`` against
  ``{"is_pinned": 1}`` should not silently call that a match.

This module is purely about comparing two already-selected values -- it has
no opinion on *which* keys of a larger result dict (e.g. bookkeeping ones
like ``"__html_report__"``) should even be compared; that's the caller's.
"""
import math
from typing import Any, Dict, List

#: Floats within this absolute tolerance of each other are considered equal
#: -- see the module docstring.
FLOAT_ABS_TOLERANCE = 0.0001


def values_match(approved: Any, actual: Any) -> bool:
    """Whether ``actual`` matches ``approved``, per this module's own,
    type-dependent equality (see the module docstring).

    This is the single source of truth :func:`diff` itself ultimately
    bottoms out at for every leaf value it compares.
    """
    if isinstance(approved, bool) or isinstance(actual, bool):
        return approved is actual
    if isinstance(approved, (int, float)) and isinstance(actual, (int, float)):
        if isinstance(approved, int) and isinstance(actual, int):
            return approved == actual
        return math.isclose(float(approved), float(actual), abs_tol=FLOAT_ABS_TOLERANCE)
    if isinstance(approved, dict) and isinstance(actual, dict):
        return not diff(approved, actual)
    if isinstance(approved, list) and isinstance(actual, list):
        return not diff(approved, actual)
    return approved == actual


def diff(approved: Any, actual: Any, path: str = "") -> List[str]:
    """Every difference between ``approved`` and ``actual``, as human-
    readable, ``path``-prefixed messages (e.g.
    ``"qrel_stats.number_of_queries: expected 3, got 4"``) -- empty if they
    match (per :func:`values_match`). Recurses into matching dict/list
    structure; anything else is compared as one leaf value.
    """
    label = path or "<root>"
    if isinstance(approved, dict) and isinstance(actual, dict):
        differences = []
        for key in sorted(set(approved) | set(actual), key=str):
            child_path = f"{path}.{key}" if path else str(key)
            if key not in approved:
                differences.append(f"{child_path}: unexpected key (got {actual[key]!r})")
            elif key not in actual:
                differences.append(f"{child_path}: missing key (expected {approved[key]!r})")
            else:
                differences.extend(diff(approved[key], actual[key], child_path))
        return differences
    if isinstance(approved, list) and isinstance(actual, list):
        differences = []
        if len(approved) != len(actual):
            differences.append(
                f"{label}: length differs (expected {len(approved)}, got {len(actual)})"
            )
        for index, (approved_item, actual_item) in enumerate(zip(approved, actual)):
            differences.extend(diff(approved_item, actual_item, f"{path}[{index}]"))
        return differences
    if values_match(approved, actual):
        return []
    return [f"{label}: expected {approved!r}, got {actual!r}"]


def compare_results(approved: Any, actual: Any) -> Dict[str, Any]:
    """Compare ``actual`` (a freshly computed result) against ``approved``
    (a previously approved one), returning
    ``{"matches": bool, "differences": [...]}`` (see :func:`diff` for the
    message shape; empty when ``matches`` is ``True``).
    """
    differences = diff(approved, actual)
    return {"matches": not differences, "differences": differences}


__all__ = ["FLOAT_ABS_TOLERANCE", "compare_results", "diff", "values_match"]
