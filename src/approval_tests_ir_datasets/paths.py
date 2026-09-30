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


__all__ = [
    "approvals_dir",
    "approvals_home",
    "sanitize_dataset_id",
    "sanitize_path_component",
]
