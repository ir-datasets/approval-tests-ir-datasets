import importlib.metadata

import approval_tests_ir_datasets as atid
from approval_tests_ir_datasets import IrDatasetsApprovalTest


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
