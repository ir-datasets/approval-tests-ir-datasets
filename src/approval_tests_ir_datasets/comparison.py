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

#: Sentinel used by :func:`diff_details` to mark a side of a difference as
#: absent (e.g. a key that only exists on the approved -- or only on the
#: actual -- side), since ``None`` is itself a valid, distinct value a
#: verifier result could legitimately hold.
MISSING = object()


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


def diff_details(approved: Any, actual: Any, path: str = "") -> List[Dict[str, Any]]:
    """The same differences as :func:`diff`, but structured rather than
    pre-formatted: each entry is ``{"path": str, "kind": str, "approved":
    ..., "actual": ...}``, where ``kind`` is one of ``"leaf"``,
    ``"missing_key"``, ``"unexpected_key"`` or ``"length_mismatch"``, and
    the absent side of a ``"missing_key"``/``"unexpected_key"`` entry is
    :data:`MISSING`. :func:`diff` is itself just this function's entries
    rendered as human-readable strings -- use this one instead when you
    need the actual values (e.g. to render a rich HTML diff) rather than a
    message.
    """
    if isinstance(approved, dict) and isinstance(actual, dict):
        details = []
        for key in sorted(set(approved) | set(actual), key=str):
            child_path = f"{path}.{key}" if path else str(key)
            if key not in approved:
                details.append(
                    {"path": child_path, "kind": "unexpected_key", "approved": MISSING, "actual": actual[key]}
                )
            elif key not in actual:
                details.append(
                    {"path": child_path, "kind": "missing_key", "approved": approved[key], "actual": MISSING}
                )
            else:
                details.extend(diff_details(approved[key], actual[key], child_path))
        return details
    if isinstance(approved, list) and isinstance(actual, list):
        details = []
        if len(approved) != len(actual):
            details.append(
                {
                    "path": path or "<root>",
                    "kind": "length_mismatch",
                    "approved": len(approved),
                    "actual": len(actual),
                }
            )
        for index, (approved_item, actual_item) in enumerate(zip(approved, actual)):
            details.extend(diff_details(approved_item, actual_item, f"{path}[{index}]"))
        return details
    if values_match(approved, actual):
        return []
    return [{"path": path or "<root>", "kind": "leaf", "approved": approved, "actual": actual}]


def diff(approved: Any, actual: Any, path: str = "") -> List[str]:
    """Every difference between ``approved`` and ``actual``, as human-
    readable, ``path``-prefixed messages (e.g.
    ``"qrel_stats.number_of_queries: expected 3, got 4"``) -- empty if they
    match (per :func:`values_match`). Recurses into matching dict/list
    structure; anything else is compared as one leaf value.
    """
    messages = []
    for detail in diff_details(approved, actual, path):
        if detail["kind"] == "unexpected_key":
            messages.append(f"{detail['path']}: unexpected key (got {detail['actual']!r})")
        elif detail["kind"] == "missing_key":
            messages.append(f"{detail['path']}: missing key (expected {detail['approved']!r})")
        elif detail["kind"] == "length_mismatch":
            messages.append(
                f"{detail['path']}: length differs (expected {detail['approved']!r}, got {detail['actual']!r})"
            )
        else:
            messages.append(f"{detail['path']}: expected {detail['approved']!r}, got {detail['actual']!r}")
    return messages


def compare_results(approved: Any, actual: Any) -> Dict[str, Any]:
    """Compare ``actual`` (a freshly computed result) against ``approved``
    (a previously approved one), returning
    ``{"matches": bool, "differences": [...]}`` (see :func:`diff` for the
    message shape; empty when ``matches`` is ``True``).
    """
    differences = diff(approved, actual)
    return {"matches": not differences, "differences": differences}


__all__ = ["FLOAT_ABS_TOLERANCE", "MISSING", "compare_results", "diff", "diff_details", "values_match"]
