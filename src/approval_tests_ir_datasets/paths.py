"""Deterministic filesystem locations for approval test results and artifacts.

Results (and any intermediate artifacts a verifier produces, e.g. a built
PyTerrier index) are stored under a fixed, predictable directory tree rooted
at ir_datasets' own home directory, so they live alongside the dataset
content they were computed from and persist across runs.
"""
import re
from pathlib import Path

#: Name of the subdirectory (under ir_datasets' home directory) that
#: approval test results and verifier-produced artifacts are stored in.
APPROVALS_DIR_NAME = "approvals"

#: Name of the subdirectory (under ir_datasets' home directory, a sibling of
#: ``APPROVALS_DIR_NAME``) that human-approved result snapshots are stored
#: in (see :func:`approved_dir` and
#: :meth:`~approval_tests_ir_datasets.IrDatasetsApprovalTest.verify`'s
#: ``wait_for_approval`` parameter) -- kept separate from
#: ``APPROVALS_DIR_NAME`` so an approved snapshot is never silently
#: overwritten by a later, unapproved ``verify()`` run's own ``result.json``.
APPROVED_DIR_NAME = "approved"

_UNSAFE_PATH_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def sanitize_path_component(value: str) -> str:
    """Turn an arbitrary string (e.g. a dataset id or approach name) into a
    safe path segment, replacing any character that isn't alphanumeric,
    ``_``, ``.`` or ``-`` with ``_``.
    """
    return _UNSAFE_PATH_CHARS.sub("_", value)


def sanitize_dataset_id(dataset_id: str) -> str:
    """Turn a dataset id (e.g. ``"irds:cranfield-docs"``) into a safe path segment."""
    return sanitize_path_component(dataset_id)


def approvals_home() -> Path:
    """The directory approval test results and artifacts are stored under.

    Defaults to ``<ir_datasets_home>/approvals`` -- i.e.
    ``$IR_DATASETS_HOME/approvals``, or ``~/.ir_datasets/approvals`` if that
    environment variable is unset (see ``ir_datasets.util.home_path``).
    Requires ``ir_datasets`` to be installed.
    """
    import ir_datasets

    return ir_datasets.util.home_path() / APPROVALS_DIR_NAME


def approvals_dir(dataset_id: str, *parts: str) -> Path:
    """The deterministic directory results/artifacts for ``dataset_id`` live in.

    Additional ``parts`` (e.g. a verifier's entry point name) are appended as
    subdirectories, e.g. ``approvals_dir("irds:cranfield-docs",
    "pyterrier_index")``. The directory (and any missing parents) is created
    if it doesn't already exist.
    """
    directory = approvals_home() / sanitize_dataset_id(dataset_id)
    for part in parts:
        directory = directory / part
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def clear_approvals(dataset_id: str) -> None:
    """Remove ``dataset_id``'s entire ``approvals_dir`` subtree, if any.

    This deletes every artifact a verifier has cached for ``dataset_id``
    (e.g. a built PyTerrier index, retrieval runs, ``result.json``) --
    everything :func:`approvals_dir` would otherwise let a verifier reuse
    via ``recompute=False`` (the default, see each verifier's ``verify``
    method). Primarily meant for tests that need a known-clean starting
    point despite that default (rather than silently reusing whatever a
    previous, possibly stale run already left behind).

    Deliberately does *not* touch :func:`approved_dir`'s human-approved
    snapshots -- those represent a deliberate approval decision, not a
    disposable cache, so they are never cleared implicitly. Does nothing
    (rather than raising) if nothing has been cached for ``dataset_id``
    yet, or if ``ir_datasets`` isn't installed.
    """
    import shutil

    try:
        directory = approvals_home() / sanitize_dataset_id(dataset_id)
    except ImportError:
        return
    shutil.rmtree(directory, ignore_errors=True)


def approved_dir(dataset_id: str, *parts: str, create: bool = True) -> Path:
    """The deterministic directory a human-approved result snapshot for
    ``dataset_id`` is stored in (see ``APPROVED_DIR_NAME``).

    Mirrors :func:`approvals_dir`, but rooted at
    ``<ir_datasets_home>/approved`` instead of ``.../approvals``. The
    directory (and any missing parents) is created if it doesn't already
    exist, unless ``create`` is ``False`` -- pass ``create=False`` when
    merely checking whether a snapshot was ever approved (e.g.
    :meth:`~approval_tests_ir_datasets.IrDatasetsApprovalTest.cached_approved_result`),
    so that check itself doesn't leave behind an empty directory.
    """
    directory = approvals_home().parent / APPROVED_DIR_NAME / sanitize_dataset_id(dataset_id)
    for part in parts:
        directory = directory / part
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    return directory


__all__ = [
    "approved_dir",
    "approvals_dir",
    "approvals_home",
    "clear_approvals",
    "sanitize_dataset_id",
    "sanitize_path_component",
]
