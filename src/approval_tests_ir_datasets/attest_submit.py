"""Contribute locally approved snapshots to the ir_datasets attestation server.

Nothing here runs as part of :func:`approval_tests_ir_datasets.verify`: results
only leave the machine when :func:`main` (the ``approval-tests-ir-datasets-attest``
command) is called explicitly, and only for a snapshot a human
approved. The client, record schemas and signing live in core
``ir_datasets.v2.attest``; this module only maps approval results onto them.

What is attested, per node in the approved result:

* a table (it has a ``table_line_count`` result): a ``hash`` attestation of its
  content and a ``visual`` attestation (verdict ``ok``, i.e. a human approved it).
  ``visual`` records must be signed, so they need a registered identity.
* any node with an ``evaluation`` result: one ``evaluation`` attestation per
  approach (``system``) with its measures.
"""
import argparse
import json
import sys
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence

VISUAL_NOTE = "approved with approval-tests-ir-datasets"


class PlannedAttestation(NamedTuple):
    kind: str
    node: str
    content: Dict[str, Any]


def _per_node_results(dataset_id: str, result: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """``{node id: {verifier name: result}}``. A benchmark's result is already
    keyed by node id; a leaf's is flat."""
    if result and all(isinstance(key, str) and ":" in key for key in result):
        return result
    return {dataset_id: result}


def _default_hash_content(node: str) -> Dict[str, Any]:
    from ir_datasets.v2 import attest

    return attest.hash_record(node)


def build_attestations(
    dataset_id: str,
    result: Dict[str, Any],
    hash_content: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> List[PlannedAttestation]:
    """The attestations an approved ``result`` for ``dataset_id`` supports.
    ``hash_content`` computes a hash record's content for a node name (it loads
    the node, so it is injectable for tests)."""
    hash_content = hash_content or _default_hash_content
    planned: List[PlannedAttestation] = []
    for node, verifiers in _per_node_results(dataset_id, result).items():
        if not isinstance(verifiers, dict):
            continue
        if verifiers.get("table_line_count") is not None:
            planned.append(PlannedAttestation("hash", node, hash_content(node)))
            planned.append(
                PlannedAttestation("visual", node, {"verdict": "ok", "notes": VISUAL_NOTE, "sample": []})
            )
        evaluation = verifiers.get("evaluation")
        if isinstance(evaluation, dict):
            for system, measures in sorted(evaluation.items()):
                numeric = {
                    name: value
                    for name, value in (measures or {}).items()
                    if isinstance(value, (int, float)) and not isinstance(value, bool)
                }
                if numeric:
                    planned.append(PlannedAttestation("evaluation", node, {"system": system, "measures": numeric}))
    return planned


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="approval-tests-ir-datasets-attest",
        description="Submit a locally approved snapshot to the attestation server.",
    )
    parser.add_argument("dataset_id", help="qualified node name, e.g. irds:cranfield")
    parser.add_argument("--server", help="attestation server (default: $IR_DATASETS_ATTEST_URL or the public one)")
    parser.add_argument("--anonymous", action="store_true", help="do not sign (visual attestations are then skipped)")
    parser.add_argument("--dry-run", action="store_true", help="print the records instead of submitting them")
    parser.add_argument("-y", "--yes", action="store_true", help="submit without asking for confirmation")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)

    from . import IrDatasetsApprovalTest

    result = IrDatasetsApprovalTest.cached_approved_result(args.dataset_id)
    if result is None:
        print(f"No approved snapshot for {args.dataset_id}: approve one with verify(..., wait_for_approval=True).", file=sys.stderr)
        return 1

    from ir_datasets.v2 import attest
    from ir_datasets.v2.attest import crypto

    client = attest.Client(args.server)
    identity = None if args.anonymous else crypto.Identity.load()
    signed = identity is not None
    planned = build_attestations(args.dataset_id, result)
    if not signed:
        skipped = [p for p in planned if p.kind == "visual"]
        if skipped:
            print(
                f"Skipping {len(skipped)} visual attestation(s): they must be signed "
                "(run 'ir_datasets attest register <username>' and omit --anonymous).",
                file=sys.stderr,
            )
        planned = [p for p in planned if p.kind != "visual"]
    if not planned:
        print("Nothing to attest.", file=sys.stderr)
        return 1

    for p in planned:
        print(json.dumps(attest.build_record(p.kind, p.node, p.content), indent=2, sort_keys=True))
    if args.dry_run:
        return 0
    target = client.url
    who = identity.username if signed else "anonymous"
    if not args.yes and input(f"Submit {len(planned)} attestation(s) to {target} as {who}? [y/N] ").strip().lower() != "y":
        print("Aborted.")
        return 1
    for p in planned:
        attestation_id = client.submit(p.kind, p.node, p.content, identity=identity)
        print(f"{p.kind} {p.node}: attest:{attestation_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
