import pytest

pytest.importorskip("ir_datasets.v2.attest")

from approval_tests_ir_datasets import IrDatasetsApprovalTest, attest_submit  # noqa: E402

HASH = {"hash_version": 1, "hashes": ["sha256:" + "0" * 64]}

BENCHMARK_RESULT = {
    "irds:cranfield": {"evaluation": {"BM25": {"nDCG@10": 0.5, "note": None}}},
    "irds:cranfield-docs": {"table_line_count": {"length": 10}},
    "irds:cranfield.tar.gz": {"default_text": None},
}


def test_build_attestations_for_a_benchmark_result() -> None:
    planned = attest_submit.build_attestations(
        "irds:cranfield", BENCHMARK_RESULT, hash_content=lambda node: HASH
    )

    assert [(p.kind, p.node) for p in planned] == [
        ("evaluation", "irds:cranfield"),
        ("hash", "irds:cranfield-docs"),
        ("visual", "irds:cranfield-docs"),
    ]
    assert planned[0].content == {"system": "BM25", "measures": {"nDCG@10": 0.5}}
    assert planned[1].content == HASH


def test_build_attestations_for_a_flat_leaf_result() -> None:
    planned = attest_submit.build_attestations(
        "irds:cranfield-docs", {"table_line_count": {"length": 10}}, hash_content=lambda node: HASH
    )

    assert [(p.kind, p.node) for p in planned] == [
        ("hash", "irds:cranfield-docs"),
        ("visual", "irds:cranfield-docs"),
    ]


class _FakeClient:
    url = "http://attest.test"
    submitted: list = []

    def __init__(self, url=None) -> None:
        pass

    def submit(self, kind, node, content, identity=None):
        self.submitted.append((kind, node, identity))
        return f"id-{len(self.submitted)}"


@pytest.fixture
def fake_attest(monkeypatch):
    from ir_datasets.v2.attest import crypto

    _FakeClient.submitted = []
    monkeypatch.setattr("ir_datasets.v2.attest.Client", _FakeClient)
    monkeypatch.setattr(crypto.Identity, "load", classmethod(lambda cls: None))
    monkeypatch.setattr(
        attest_submit, "_default_hash_content", lambda node: HASH
    )
    monkeypatch.setattr(
        IrDatasetsApprovalTest,
        "cached_approved_result",
        staticmethod(lambda dataset_id: {"table_line_count": {"length": 10}}),
    )
    return _FakeClient


def test_main_without_approved_snapshot_fails(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        IrDatasetsApprovalTest, "cached_approved_result", staticmethod(lambda dataset_id: None)
    )

    assert attest_submit.main(["irds:cranfield-docs"]) == 1
    assert "No approved snapshot" in capsys.readouterr().err


def test_main_dry_run_submits_nothing(fake_attest, capsys) -> None:
    assert attest_submit.main(["irds:cranfield-docs", "--dry-run", "--anonymous"]) == 0

    assert fake_attest.submitted == []
    assert '"kind": "hash"' in capsys.readouterr().out


def test_main_anonymous_submits_hash_but_skips_unsignable_visual(fake_attest, capsys) -> None:
    assert attest_submit.main(["irds:cranfield-docs", "--anonymous", "--yes"]) == 0

    assert fake_attest.submitted == [("hash", "irds:cranfield-docs", None)]
    assert "Skipping 1 visual" in capsys.readouterr().err
