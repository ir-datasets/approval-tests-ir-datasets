import shutil
import unittest

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
DOCKER_AVAILABLE = shutil.which("docker") is not None

from approval_tests_ir_datasets.verifiers import PyTerrierIndexVerifier

REQUIREMENTS_AVAILABLE = (
    IR_DATASETS_V2_AVAILABLE and TIRA_AVAILABLE and TIRA_CLI_AVAILABLE and DOCKER_AVAILABLE
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

    def test_verify_returns_none_for_queries_table(self) -> None:
        result = PyTerrierIndexVerifier().verify("irds:cranfield-queries")

        self.assertIsNone(result)

    def test_verify_returns_none_for_non_table_resources(self) -> None:
        result = PyTerrierIndexVerifier().verify("irds:cranfield")

        self.assertIsNone(result)
