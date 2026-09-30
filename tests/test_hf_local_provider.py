"""Unit tests for the ``hf-local:`` provider (see
:mod:`approval_tests_ir_datasets.hf_local_provider`): resolving a local
directory laid out like an ``hf:`` dataset repo directly, by path, with no
mocking or explicit context manager required.
"""

import unittest
from pathlib import Path

try:
    import ir_datasets.v2  # noqa: F401

    IR_DATASETS_V2_AVAILABLE = True
except ImportError:
    IR_DATASETS_V2_AVAILABLE = False

from approval_tests_ir_datasets import verify
from approval_tests_ir_datasets.hf_local_provider import _split_path_and_fragment

DATASET_DIR = Path(__file__).parent / "resources" / "example-hf-dataset"


class SplitPathAndFragmentTest(unittest.TestCase):
    def test_bare_directory_has_no_fragment(self) -> None:
        directory, fragment = _split_path_and_fragment(str(DATASET_DIR))
        self.assertEqual(directory, DATASET_DIR.resolve())
        self.assertIsNone(fragment)

    def test_trailing_segment_is_split_off_as_fragment(self) -> None:
        directory, fragment = _split_path_and_fragment(f"{DATASET_DIR}/docs")
        self.assertEqual(directory, DATASET_DIR.resolve())
        self.assertEqual(fragment, "docs")

    def test_neither_a_directory_nor_a_fragment_split_raises(self) -> None:
        # Neither the whole path nor its parent (after peeling off a
        # fragment) is a directory containing a README.md.
        with self.assertRaises(KeyError):
            _split_path_and_fragment(str(DATASET_DIR.parent / "does-not-exist" / "docs"))


@unittest.skipUnless(
    IR_DATASETS_V2_AVAILABLE, "ir_datasets.v2 is required (available in the dev container)"
)
class HfLocalProviderTest(unittest.TestCase):
    """See ``tests/test_hf_integration.py`` for the full end-to-end
    integration test (loading + verifying every table); this only checks the
    provider's own name-resolution behavior (bare directory vs. fragment,
    and repeated resolutions of the same path sharing one underlying node)."""

    def test_load_bare_directory_resolves_to_the_default_benchmark(self) -> None:
        benchmark = ir_datasets.v2.load(f"hf-local:{DATASET_DIR}")
        self.assertEqual(len(list(benchmark.docs)), 10)

    def test_repeated_resolution_of_the_same_path_shares_one_table(self) -> None:
        first = ir_datasets.v2.load(f"hf-local:{DATASET_DIR}/docs")
        second = ir_datasets.v2.load(f"hf-local:{DATASET_DIR}/docs")
        self.assertIs(first, second)

    def test_verify_works_directly_on_a_path_based_id(self) -> None:
        docs_result = verify(f"hf-local:{DATASET_DIR}/docs", return_result=True)
        self.assertEqual(docs_result.get("table_line_count"), {"length": 10})
