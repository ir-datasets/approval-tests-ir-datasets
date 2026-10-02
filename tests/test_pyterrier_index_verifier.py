import shutil
import unittest
from unittest import mock

try:
    import ir_datasets.v2  # noqa: F401

    IR_DATASETS_V2_AVAILABLE = True
except ImportError:
    IR_DATASETS_V2_AVAILABLE = False

try:
    import tira  # noqa: F401

    TIRA_AVAILABLE = True
except ImportError:
    TIRA_AVAILABLE = False

TIRA_CLI_AVAILABLE = shutil.which("tira-cli") is not None

from approval_tests_ir_datasets import verifiers
from approval_tests_ir_datasets.verifiers import PyTerrierIndexVerifier

REQUIREMENTS_AVAILABLE = (
    IR_DATASETS_V2_AVAILABLE and TIRA_AVAILABLE and TIRA_CLI_AVAILABLE
)


@unittest.skipUnless(
    REQUIREMENTS_AVAILABLE,
    "ir_datasets.v2, tira, tira-cli and docker are required (available in the dev container)",
)
class PyTerrierIndexVerifierTest(unittest.TestCase):
    def test_verify_builds_index_for_cranfield_docs(self) -> None:
        result = PyTerrierIndexVerifier().verify("irds:cranfield-docs")

        self.assertEqual(
            result,
            {"num_documents": 1400, "num_terms": 4560, "num_tokens": 136913},
        )

    def test_verify_returns_none_for_qrels_table(self) -> None:
        result = PyTerrierIndexVerifier().verify("irds:cranfield-qrels")

        self.assertIsNone(result)

    def test_verify_builds_index_for_cranfield_queries(self) -> None:
        # PyTerrierIndexVerifier applies to any table whose records expose
        # default_text() -- not just document tables -- so query tables are
        # indexed too.
        result = PyTerrierIndexVerifier().verify("irds:cranfield-queries")

        self.assertEqual(
            result,
            {"num_documents": 225, "num_terms": 659, "num_tokens": 2239},
        )

    def test_verify_returns_none_for_non_table_resources(self) -> None:
        result = PyTerrierIndexVerifier().verify("irds:cranfield")

        self.assertIsNone(result)

    def test_cached_index_path_finds_the_index_built_by_verify(self) -> None:
        import approval_tests_ir_datasets as atid

        atid.verify("irds:cranfield-docs")

        index_path = PyTerrierIndexVerifier().cached_index_path("irds:cranfield-docs")

        self.assertIsNotNone(index_path)
        self.assertTrue((index_path / "data.properties").is_file())

    def test_cached_index_path_returns_none_without_a_prior_verify_call(self) -> None:
        index_path = PyTerrierIndexVerifier().cached_index_path(
            "irds:a-dataset-that-was-never-verified"
        )

        self.assertIsNone(index_path)


@unittest.skipUnless(
    IR_DATASETS_V2_AVAILABLE and TIRA_AVAILABLE,
    "ir_datasets.v2 and tira are required (available in the dev container)",
)
class PyTerrierIndexVerifierTiraInstallationCheckTest(unittest.TestCase):
    def test_verify_raises_without_invoking_tira_cli_when_installation_check_fails(
        self,
    ) -> None:
        with mock.patch.object(verifiers, "_tira_installation_ok", False), mock.patch(
            "subprocess.run"
        ) as run:
            with self.assertRaisesRegex(RuntimeError, "tira-cli verify-installation"):
                PyTerrierIndexVerifier().verify("irds:cranfield-docs", recompute=True)

        run.assert_not_called()
