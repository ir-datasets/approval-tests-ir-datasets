"""A permanent, multi-repo-aware stand-in for ``huggingface_hub``, letting
one or more local directories be resolved by ``ir_datasets.v2``'s ``hf:``
provider (see :mod:`ir_datasets.v2.hf_provider`) exactly as if they were real
Hugging Face Hub dataset repos -- no network access, no real repo required.

This is used two ways:

* :func:`local_hf_repo`, a context manager that temporarily redirects one
  exact ``hf:<repo>`` id to a local directory for its duration (see its own
  docstring) -- handy for pointing an *existing* repo id at a local fixture
  for one call.
* :mod:`approval_tests_ir_datasets.hf_local_provider`'s ``hf-local:``
  provider, which registers local directories permanently (for the life of
  the process) under synthetic repo ids, so plain paths can be addressed
  directly (``hf-local:some/local/dir``) with no repo id of their own.

Both share the same underlying proxy (:func:`_ensure_installed`,
``_local_dirs``): it is installed once, lazily, the first time either is
used, and -- critically -- falls through to the *real* ``huggingface_hub``
for any repo id it doesn't know about, so genuine ``hf:`` datasets keep
working unaffected.

TODO: this whole module is a workaround for ``ir_datasets`` having no
first-class "local hf: repo" feature of its own (see ``README.md``'s TODOs
section); rewrite/remove it once it does.
"""
import contextlib
from pathlib import Path
from typing import Dict, Iterator, Union

#: repo id -> local directory it should resolve against. Shared (and
#: mutated) by both `local_hf_repo` and the `hf-local:` provider.
_local_dirs: Dict[str, Path] = {}

#: A commit sha good enough for `HfApi().dataset_info(...).sha`'s callers --
#: never compared against anything real, since local directories have no
#: git history of their own.
_FAKE_COMMIT = "0" * 40


class _FakeDatasetInfo:
    def __init__(self, sha: str) -> None:
        self.sha = sha


class _LocalAwareHub:
    """A ``huggingface_hub``-module-shaped object: resolves repo ids
    registered in ``_local_dirs`` straight off disk, and delegates any other
    repo id to the real ``huggingface_hub`` module -- imported lazily, only
    when actually needed -- so real ``hf:`` datasets keep working
    unaffected."""

    def __init__(self, real_hf_lib):
        self._real_hf_lib = real_hf_lib

    def HfApi(self):
        return _LocalAwareHfApi(self)

    def hf_hub_download(self, repo_id, repo_type, filename, revision=None):
        if repo_id in _local_dirs:
            return str(_local_dirs[repo_id] / filename)
        return self._real_hf_lib().hf_hub_download(
            repo_id=repo_id, repo_type=repo_type, filename=filename, revision=revision
        )

    def snapshot_download(self, repo_id, repo_type, revision=None):
        if repo_id in _local_dirs:
            return str(_local_dirs[repo_id])
        return self._real_hf_lib().snapshot_download(
            repo_id=repo_id, repo_type=repo_type, revision=revision
        )


class _LocalAwareHfApi:
    def __init__(self, hub: _LocalAwareHub) -> None:
        self._hub = hub

    def dataset_info(self, repo_id, revision=None):
        if repo_id in _local_dirs:
            return _FakeDatasetInfo(_FAKE_COMMIT)
        return self._hub._real_hf_lib().HfApi().dataset_info(repo_id, revision=revision)


_installed = False


def _ensure_installed() -> None:
    """Install the local-aware hub proxy over ``hf_provider._hf_lib``, once
    per process. Idempotent -- safe to call from multiple call sites."""
    global _installed
    if _installed:
        return
    from ir_datasets.v2 import hf_provider as hfm

    proxy_hub = _LocalAwareHub(hfm._hf_lib)
    hfm._hf_lib = lambda: proxy_hub
    _installed = True


def _clear_repo_caches(repo: str) -> None:
    """Purge every cache entry ``hf_provider`` keeps for ``repo``, so a later
    lookup of the same repo id (e.g. a real one reusing this id, however
    unlikely) starts fresh rather than reusing stale, locally-resolved
    data."""
    from ir_datasets.v2 import hf_provider as hfm

    for cache in (hfm._card_cache, hfm._repo_cache, hfm._table_cache, hfm._benchmark_cache):
        for key in [key for key in cache if key[0] == repo]:
            del cache[key]


@contextlib.contextmanager
def local_hf_repo(repo: str, local_dir: Union[str, Path]) -> Iterator[None]:
    """Temporarily make ``hf:<repo>`` (and nothing else) resolve against
    ``local_dir`` on disk instead of the real Hugging Face Hub, for the
    duration of this ``with`` block.

    ``local_dir`` must be laid out exactly like a real ``hf:`` dataset repo
    (a ``README.md`` with an ``ir_datasets:``/``ir-datasets:`` card, plus
    whatever ``file:`` paths it declares). On exit, ``repo`` is forgotten
    again and every cache entry ``hf_provider`` keeps for it is cleared --
    even if the block raises -- so a later, unrelated use of the same repo
    id resolves fresh rather than reusing stale local data.
    """
    _ensure_installed()
    _local_dirs[repo] = Path(local_dir)
    try:
        yield
    finally:
        del _local_dirs[repo]
        _clear_repo_caches(repo)
