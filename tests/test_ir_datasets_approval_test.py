import importlib.metadata
import json
from pathlib import Path
from typing import Any, Dict

import approval_tests_ir_datasets as atid
from approval_tests_ir_datasets import IrDatasetsApprovalTest

try:
    import ir_datasets  # noqa: F401

    IR_DATASETS_AVAILABLE = True
except ImportError:
    IR_DATASETS_AVAILABLE = False


class _FakeEntryPoint:
    def __init__(self, name, cls, group=atid.ENTRY_POINT_GROUP):
        self.name = name
        self.group = group
        self._cls = cls

    def load(self):
        return self._cls


class _FakeEntryPoints(list):
    def select(self, group):
        return _FakeEntryPoints(ep for ep in self if ep.group == group)

    def get(self, group, default=None):
        matches = [ep for ep in self if ep.group == group]
        return matches if matches else (default if default is not None else [])


class _UppercaseVerifier:
    def verify(self, dataset_id: str) -> str:
        return dataset_id.upper()


class _LengthVerifier:
    def verify(self, dataset_id: str) -> int:
        return len(dataset_id)


class _NoneVerifier:
    def verify(self, dataset_id: str):
        return None


class _RecomputeAwareVerifier:
    """Records the ``recompute`` value it was called with, mimicking
    verifiers like ``PyTerrierIndexVerifier``/``RetrievalVerifier`` that
    accept a ``recompute`` keyword.
    """

    calls: list = []

    def verify(self, dataset_id: str, recompute: bool = True) -> Dict[str, Any]:
        type(self).calls.append(recompute)
        return {"dataset_id": dataset_id, "recompute": recompute}


def test_verify_does_not_render_html_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        lambda: _FakeEntryPoints([_FakeEntryPoint("uppercase", _UppercaseVerifier)]),
    )

    result = IrDatasetsApprovalTest().verify("dataset-id")

    assert "__html_report__" not in result


def test_verify_writes_an_html_report_when_requested(monkeypatch) -> None:
    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        lambda: _FakeEntryPoints([_FakeEntryPoint("uppercase", _UppercaseVerifier)]),
    )

    result = IrDatasetsApprovalTest().verify("dataset-id", render_as_html=True)

    report_path = Path(result["__html_report__"])
    assert report_path.is_file()
    content = report_path.read_text()
    assert "dataset-id" in content
    assert "DATASET-ID" in content


def test_verify_defaults_to_recompute_true_for_verifiers_that_accept_it(monkeypatch) -> None:
    _RecomputeAwareVerifier.calls = []
    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        lambda: _FakeEntryPoints([_FakeEntryPoint("recompute_aware", _RecomputeAwareVerifier)]),
    )

    result = IrDatasetsApprovalTest().verify("dataset-id")

    assert _RecomputeAwareVerifier.calls == [True]
    assert result == {"recompute_aware": {"dataset_id": "dataset-id", "recompute": True}}


def test_verify_forwards_recompute_false_to_verifiers_that_accept_it(monkeypatch) -> None:
    _RecomputeAwareVerifier.calls = []
    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        lambda: _FakeEntryPoints([_FakeEntryPoint("recompute_aware", _RecomputeAwareVerifier)]),
    )

    result = IrDatasetsApprovalTest().verify("dataset-id", recompute=False)

    assert _RecomputeAwareVerifier.calls == [False]
    assert result == {"recompute_aware": {"dataset_id": "dataset-id", "recompute": False}}


def test_verify_ignores_recompute_for_verifiers_that_do_not_accept_it(monkeypatch) -> None:
    # _UppercaseVerifier.verify only takes dataset_id -- passing recompute
    # to it would raise a TypeError; verify() must not do that.
    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        lambda: _FakeEntryPoints([_FakeEntryPoint("uppercase", _UppercaseVerifier)]),
    )

    result = IrDatasetsApprovalTest().verify("dataset-id", recompute=False)

    assert result == {"uppercase": "DATASET-ID"}


def test_verify_returns_empty_dict_when_no_verifiers_registered(monkeypatch) -> None:
    monkeypatch.setattr(
        importlib.metadata, "entry_points", lambda: _FakeEntryPoints()
    )

    result = IrDatasetsApprovalTest().verify("dataset-id")

    assert result == {}


def test_verify_applies_all_registered_verifiers(monkeypatch) -> None:
    fake_entry_points = _FakeEntryPoints(
        [
            _FakeEntryPoint("uppercase", _UppercaseVerifier),
            _FakeEntryPoint("length", _LengthVerifier),
        ]
    )
    monkeypatch.setattr(
        importlib.metadata, "entry_points", lambda: fake_entry_points
    )

    result = IrDatasetsApprovalTest().verify("dataset-id")

    assert result == {"uppercase": "DATASET-ID", "length": len("dataset-id")}


def test_verify_ignores_entry_points_from_other_groups(monkeypatch) -> None:
    fake_entry_points = _FakeEntryPoints(
        [
            _FakeEntryPoint("uppercase", _UppercaseVerifier),
            _FakeEntryPoint("other", _LengthVerifier, group="unrelated.group"),
        ]
    )
    monkeypatch.setattr(
        importlib.metadata, "entry_points", lambda: fake_entry_points
    )

    result = IrDatasetsApprovalTest().verify("dataset-id")

    assert result == {"uppercase": "DATASET-ID"}


def test_verify_omits_verifiers_that_return_none(monkeypatch) -> None:
    fake_entry_points = _FakeEntryPoints(
        [
            _FakeEntryPoint("uppercase", _UppercaseVerifier),
            _FakeEntryPoint("none", _NoneVerifier),
        ]
    )
    monkeypatch.setattr(
        importlib.metadata, "entry_points", lambda: fake_entry_points
    )

    result = IrDatasetsApprovalTest().verify("dataset-id")

    assert result == {"uppercase": "DATASET-ID"}


def test_verify_persists_results_as_json_without_ir_datasets(monkeypatch) -> None:
    # Persistence requires the .paths module (in turn requiring ir_datasets)
    # to know where to write to; if it's unavailable, verify() should still
    # succeed and simply skip persisting.
    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        lambda: _FakeEntryPoints([_FakeEntryPoint("uppercase", _UppercaseVerifier)]),
    )
    monkeypatch.setitem(
        __import__("sys").modules, "approval_tests_ir_datasets.paths", None
    )

    result = IrDatasetsApprovalTest().verify("dataset-id")

    assert result == {"uppercase": "DATASET-ID"}


if IR_DATASETS_AVAILABLE:

    def test_verify_persists_results_under_ir_datasets_home(tmp_path, monkeypatch) -> None:
        import ir_datasets

        monkeypatch.setattr(ir_datasets.util, "home_path", lambda: tmp_path)
        monkeypatch.setattr(
            importlib.metadata,
            "entry_points",
            lambda: _FakeEntryPoints(
                [
                    _FakeEntryPoint("uppercase", _UppercaseVerifier),
                    _FakeEntryPoint("none", _NoneVerifier),
                ]
            ),
        )

        result = IrDatasetsApprovalTest().verify("irds:cranfield-docs")

        result_path = (
            tmp_path / "approvals" / "irds_cranfield-docs" / "result.json"
        )
        assert result_path.is_file()
        assert json.loads(result_path.read_text()) == result
        assert result == {"uppercase": "IRDS:CRANFIELD-DOCS"}

    def test_verify_traverses_sub_resources_of_a_benchmark(
        tmp_path, monkeypatch
    ) -> None:
        # "irds:cranfield" is a benchmark with docs, queries and qrels
        # sub-tables (each a distinct qualified name) -- verify() should run
        # every verifier against each of them, not just the benchmark itself.
        import ir_datasets

        monkeypatch.setattr(ir_datasets.util, "home_path", lambda: tmp_path)
        monkeypatch.setattr(
            importlib.metadata,
            "entry_points",
            lambda: _FakeEntryPoints([_FakeEntryPoint("uppercase", _UppercaseVerifier)]),
        )

        result = IrDatasetsApprovalTest().verify("irds:cranfield")

        assert set(result.keys()) == {
            "irds:cranfield",
            "irds:cranfield-docs",
            "irds:cranfield-queries",
            "irds:cranfield-qrels",
        }
        for dataset_id, sub_result in result.items():
            assert sub_result == {"uppercase": dataset_id.upper()}

        # The aggregated result is persisted for the root id, and each sub
        # resource's own flat result is persisted independently too.
        root_result_path = tmp_path / "approvals" / "irds_cranfield" / "result.json"
        assert json.loads(root_result_path.read_text()) == result

        docs_result_path = (
            tmp_path / "approvals" / "irds_cranfield-docs" / "result.json"
        )
        assert json.loads(docs_result_path.read_text()) == {
            "uppercase": "IRDS:CRANFIELD-DOCS"
        }

    def test_verify_keeps_flat_shape_for_a_leaf_table(tmp_path, monkeypatch) -> None:
        # A leaf table (no docs/queries/qrels/... sub resources) keeps the
        # original flat result shape, unaffected by traversal.
        import ir_datasets

        monkeypatch.setattr(ir_datasets.util, "home_path", lambda: tmp_path)
        monkeypatch.setattr(
            importlib.metadata,
            "entry_points",
            lambda: _FakeEntryPoints([_FakeEntryPoint("uppercase", _UppercaseVerifier)]),
        )

        result = IrDatasetsApprovalTest().verify("irds:cranfield-docs")

        assert result == {"uppercase": "IRDS:CRANFIELD-DOCS"}


def test_verify_does_not_wait_for_approval_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        lambda: _FakeEntryPoints([_FakeEntryPoint("uppercase", _UppercaseVerifier)]),
    )

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("the approval server should not be started")

    monkeypatch.setattr(
        IrDatasetsApprovalTest, "_run_approval_server", staticmethod(_fail_if_called)
    )

    result = IrDatasetsApprovalTest().verify("dataset-id")

    assert "__html_report__" not in result


if IR_DATASETS_AVAILABLE:

    def test_verify_stores_an_approved_snapshot_when_approved(tmp_path, monkeypatch) -> None:
        import ir_datasets

        monkeypatch.setattr(ir_datasets.util, "home_path", lambda: tmp_path)
        monkeypatch.setattr(
            importlib.metadata,
            "entry_points",
            lambda: _FakeEntryPoints([_FakeEntryPoint("uppercase", _UppercaseVerifier)]),
        )
        monkeypatch.setattr(
            IrDatasetsApprovalTest, "_run_approval_server", staticmethod(lambda report_path: True)
        )

        result = IrDatasetsApprovalTest().verify("dataset-id", wait_for_approval=True)

        assert "__html_report__" in result
        approved_result_path = tmp_path / "approved" / "dataset-id" / "result.json"
        assert approved_result_path.is_file()
        assert json.loads(approved_result_path.read_text()) == result

    def test_verify_discards_nothing_extra_when_denied(tmp_path, monkeypatch) -> None:
        import ir_datasets

        monkeypatch.setattr(ir_datasets.util, "home_path", lambda: tmp_path)
        monkeypatch.setattr(
            importlib.metadata,
            "entry_points",
            lambda: _FakeEntryPoints([_FakeEntryPoint("uppercase", _UppercaseVerifier)]),
        )
        monkeypatch.setattr(
            IrDatasetsApprovalTest, "_run_approval_server", staticmethod(lambda report_path: False)
        )

        IrDatasetsApprovalTest().verify("dataset-id", wait_for_approval=True)

        assert not (tmp_path / "approved").exists()
        # The regular (unapproved) result is still persisted, as always.
        assert (tmp_path / "approvals" / "dataset-id" / "result.json").is_file()
