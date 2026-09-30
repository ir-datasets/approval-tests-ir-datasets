"""``hf-local:`` -- a Generator-based ``ir_datasets.v2`` provider mirroring
``hf:``'s own addressing scheme, but resolving its "repo" against a local
directory on disk instead of a real Hugging Face Hub repo.

Lets a persisted, ir_datasets-annotated dataset card (e.g.
``tests/resources/example-hf-dataset``) be loaded directly, with no test
setup at all::

    ir_datasets.v2.load("hf-local:tests/resources/example-hf-dataset")
    ir_datasets.v2.load("hf-local:tests/resources/example-hf-dataset/docs")
    verify("hf-local:tests/resources/example-hf-dataset/docs")

Addressing: ``hf-local:<path>[/fragment]``, where ``<path>`` is a filesystem
path (relative to the current working directory, or absolute) to a directory
laid out exactly like a real ``hf:`` dataset repo (a ``README.md`` with an
``ir_datasets:``/``ir-datasets:`` YAML frontmatter card, plus whatever
``file:`` paths it declares), and the optional ``/fragment`` is a raw
``tables:`` key, a ``benchmarks:`` key, or (with exactly one benchmark) a
facet name -- exactly like ``hf:``'s own fragment. Since ``<path>`` may
itself contain ``/``, it is *not* found by splitting on the first/last ``/``
alone: the whole spec is first tried as a directory outright, and only if
that isn't one is its last path segment peeled off and tried as a fragment
instead (see :func:`_split_path_and_fragment`).

Each local directory is mapped to a synthetic, ``owner/name``-shaped repo id
(see :func:`_repo_id_for`) registered with
:mod:`approval_tests_ir_datasets.hf_local`'s shared hub proxy, then resolved
via ``hf_provider``'s own ``_HfResolver`` -- the real card-parsing/table-
building logic runs unmodified; only where it fetches its files (a local
directory instead of a Hub download) differs.

TODO: like :mod:`approval_tests_ir_datasets.hf_local` (whose hub proxy this
module reuses and permanently installs), this is a workaround for
``ir_datasets`` having no first-class "local hf: repo" feature of its own;
rewrite/remove this once it does (see ``README.md``'s TODOs section).
"""
import hashlib
from pathlib import Path
from typing import Optional, Tuple

from . import hf_local


def _repo_id_for(local_dir: Path) -> str:
    """A stable, ``owner/name``-shaped (one slash, no ``@``) synthetic repo
    id for a resolved local directory -- the same directory always maps to
    the same id, so repeated resolutions of the same path share
    ``hf_provider``'s own internal caches instead of rebuilding independent
    objects."""
    digest = hashlib.sha256(str(local_dir).encode("utf-8")).hexdigest()[:24]
    return f"local/{digest}"


def _split_path_and_fragment(spec: str) -> Tuple[Path, Optional[str]]:
    """``<path>[/fragment]`` -> ``(resolved directory, fragment or None)``.

    Tries the whole ``spec`` as a directory (containing a ``README.md``)
    first; only if that fails is its last ``/``-segment peeled off and tried
    as a fragment, with the remainder re-checked the same way. Raises
    ``KeyError`` if neither works -- becomes "no such node" at
    ``ManifestProvider.__getitem__``, exactly like an unannotated ``hf:``
    repo does.
    """
    candidate = Path(spec)
    if (candidate / "README.md").is_file():
        return candidate.resolve(), None
    if "/" in spec:
        parent, _, fragment = spec.rpartition("/")
        parent_path = Path(parent)
        if (parent_path / "README.md").is_file():
            return parent_path.resolve(), fragment
    raise KeyError(
        f"hf-local:{spec}: neither {candidate} nor a fragment split off its last "
        f"path segment is a directory containing a README.md"
    )


def _resolve(spec: str):
    from ir_datasets.v2 import hf_provider as hfm

    local_dir, fragment = _split_path_and_fragment(spec)
    hf_local._ensure_installed()
    repo = _repo_id_for(local_dir)
    hf_local._local_dirs[repo] = local_dir
    hf_spec = f"{repo}/{fragment}" if fragment else repo
    return hfm._HfResolver(hf_spec)


_registered = False


def register() -> None:
    """Register the ``hf-local`` provider with ``ir_datasets.v2``'s default
    graph, once per process. Safe to call repeatedly. Does nothing if
    ``ir_datasets`` isn't installed, matching this project's usual
    "silently skipped" convention for the optional dependency."""
    global _registered
    if _registered:
        return
    try:
        from ir_datasets.v2.base import Generator, Param
        from ir_datasets.v2.graph import default_graph
        from ir_datasets.v2.nodes import TABLE
        from ir_datasets.v2.registry import ManifestProvider
    except ImportError:
        return

    provider = ManifestProvider("hf-local")
    provider.register_generator(
        Generator(
            "{spec}",
            params={"spec": Param(pattern=r".+")},
            # Descriptive only (see hf_provider's own identical generator):
            # the actual produced type varies between a per-entity table and
            # a Benchmark, depending on what's requested.
            type=TABLE,
            resolver=_resolve,
            enumerable=False,
        ),
        module=__name__,
    )
    default_graph().add(provider)
    _registered = True


register()
