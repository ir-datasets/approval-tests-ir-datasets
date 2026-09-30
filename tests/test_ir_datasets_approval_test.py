import importlib.metadata
import json

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
