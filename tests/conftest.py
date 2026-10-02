"""Shared pytest fixtures for the test suite.

Most verifiers now default to ``recompute=False`` (see
:mod:`approval_tests_ir_datasets.verifiers`) -- they reuse whatever is
already cached under ir_datasets' home directory rather than recomputing it.
Tests that exercise these verifiers against real ir-datasets (e.g. the
``irds:cranfield`` family) rely on actually seeing fresh computations run at
least once, so a developer's (or a previous test run's) stale local cache
must not silently be reused across runs.
"""
import pytest

#: Dataset ids whose cached approval test artifacts (built indices, runs,
#: result.json, ...) are cleared once per test session, before anything
#: else runs -- the real ir-datasets used throughout the test suite, as
#: opposed to the fake/monkeypatched dataset ids other tests use (which are
#: already isolated via a temporary ir_datasets home).
_DATASET_IDS_TO_CLEAR = (
    "irds:cranfield",
    "irds:cranfield-docs",
    "irds:cranfield-queries",
    "irds:cranfield-qrels",
)


@pytest.fixture(scope="session", autouse=True)
def _clear_cranfield_approvals_cache() -> None:
    try:
        from approval_tests_ir_datasets.paths import clear_approvals
    except ImportError:
        # ir_datasets isn't installed -- nothing could have been cached.
        return
    for dataset_id in _DATASET_IDS_TO_CLEAR:
        clear_approvals(dataset_id)
