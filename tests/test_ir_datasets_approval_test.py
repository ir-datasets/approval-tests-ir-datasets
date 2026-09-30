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
        # The stored snapshot excludes bookkeeping keys (e.g. the HTML
        # report's path, which is a fresh temp-directory path on every run
        # and thus would never match a previous approval) -- only the
        # actual verifier output is approved.
        stored = json.loads(approved_result_path.read_text())
        assert "__html_report__" not in stored
        assert stored == {"uppercase": "DATASET-ID"}

        # Approving also records *when* it happened, so a later verify()
        # can tell the user an approved snapshot exists and since when.
        metadata_path = tmp_path / "approved" / "dataset-id" / "metadata.json"
        assert metadata_path.is_file()
        assert "approved_at" in json.loads(metadata_path.read_text())

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


if IR_DATASETS_AVAILABLE:

    def _seed_approved_result(
        tmp_path: Path,
        dataset_id: str,
        result: Dict[str, Any],
        approved_at: str = "2024-01-02T03:04:05+00:00",
    ) -> None:
        directory = tmp_path / "approved" / dataset_id
        directory.mkdir(parents=True)
        (directory / "result.json").write_text(json.dumps(result))
        (directory / "metadata.json").write_text(json.dumps({"approved_at": approved_at}))

    def test_verify_does_not_add_a_comparison_key_when_no_approved_snapshot_exists(
        tmp_path, monkeypatch
    ) -> None:
        import ir_datasets

        monkeypatch.setattr(ir_datasets.util, "home_path", lambda: tmp_path)
        monkeypatch.setattr(
            importlib.metadata,
            "entry_points",
            lambda: _FakeEntryPoints([_FakeEntryPoint("uppercase", _UppercaseVerifier)]),
        )

        result = IrDatasetsApprovalTest().verify("dataset-id")

        assert result == {"uppercase": "DATASET-ID"}
        assert "__approval_comparison__" not in result

    def test_verify_reports_a_match_against_an_identical_approved_snapshot(
        tmp_path, monkeypatch, capsys
    ) -> None:
        import ir_datasets

        monkeypatch.setattr(ir_datasets.util, "home_path", lambda: tmp_path)
        monkeypatch.setattr(
            importlib.metadata,
            "entry_points",
            lambda: _FakeEntryPoints([_FakeEntryPoint("uppercase", _UppercaseVerifier)]),
        )
        _seed_approved_result(tmp_path, "dataset-id", {"uppercase": "DATASET-ID"})

        result = IrDatasetsApprovalTest().verify("dataset-id")

        assert result["__approval_comparison__"] == {"matches": True, "differences": []}
        assert "match the previously approved results" in capsys.readouterr().out

    def test_verify_summary_mentions_when_an_approved_snapshot_exists(
        tmp_path, monkeypatch, capsys
    ) -> None:
        import ir_datasets

        monkeypatch.setattr(ir_datasets.util, "home_path", lambda: tmp_path)
        monkeypatch.setattr(
            importlib.metadata,
            "entry_points",
            lambda: _FakeEntryPoints([_FakeEntryPoint("uppercase", _UppercaseVerifier)]),
        )
        _seed_approved_result(
            tmp_path,
            "dataset-id",
            {"uppercase": "DATASET-ID"},
            approved_at="2024-01-02T03:04:05+00:00",
        )

        IrDatasetsApprovalTest().verify("dataset-id")

        printed = capsys.readouterr().out
        assert "Approved results for 'dataset-id' exist" in printed
        assert "2024-01-02" in printed

    def test_verify_summary_reports_test_count_and_duration(
        tmp_path, monkeypatch, capsys
    ) -> None:
        import ir_datasets

        monkeypatch.setattr(ir_datasets.util, "home_path", lambda: tmp_path)
        monkeypatch.setattr(
            importlib.metadata,
            "entry_points",
            lambda: _FakeEntryPoints(
                [
                    _FakeEntryPoint("uppercase", _UppercaseVerifier),
                    _FakeEntryPoint("length", _LengthVerifier),
                ]
            ),
        )

        IrDatasetsApprovalTest().verify("dataset-id")

        printed = capsys.readouterr().out
        assert "Running 2 tests took" in printed

    def test_verify_summary_does_not_mention_an_approved_snapshot_when_none_exists(
        tmp_path, monkeypatch, capsys
    ) -> None:
        import ir_datasets

        monkeypatch.setattr(ir_datasets.util, "home_path", lambda: tmp_path)
        monkeypatch.setattr(
            importlib.metadata,
            "entry_points",
            lambda: _FakeEntryPoints([_FakeEntryPoint("uppercase", _UppercaseVerifier)]),
        )

        IrDatasetsApprovalTest().verify("dataset-id")

        printed = capsys.readouterr().out
        assert "Approved results for" not in printed
        assert "No approved results exist yet for 'dataset-id'" in printed

    def test_verify_excludes_html_report_path_from_the_comparison(
        tmp_path, monkeypatch
    ) -> None:
        # The HTML report is written to a fresh temp directory on every
        # run, so its path would never match a previously approved one --
        # it must not be treated as a verifier result to compare/approve.
        import ir_datasets

        monkeypatch.setattr(ir_datasets.util, "home_path", lambda: tmp_path)
        monkeypatch.setattr(
            importlib.metadata,
            "entry_points",
            lambda: _FakeEntryPoints([_FakeEntryPoint("uppercase", _UppercaseVerifier)]),
        )
        # Simulate a stale approved snapshot from before bookkeeping keys
        # were excluded, which still has its own (now stale) report path.
        _seed_approved_result(
            tmp_path,
            "dataset-id",
            {"uppercase": "DATASET-ID", "__html_report__": "/tmp/old-report.html"},
        )

        result = IrDatasetsApprovalTest().verify("dataset-id", render_as_html=True)

        assert result["__approval_comparison__"] == {"matches": True, "differences": []}

    def test_verify_reports_differences_against_a_differing_approved_snapshot(
        tmp_path, monkeypatch, capsys
    ) -> None:
        import ir_datasets

        monkeypatch.setattr(ir_datasets.util, "home_path", lambda: tmp_path)
        monkeypatch.setattr(
            importlib.metadata,
            "entry_points",
            lambda: _FakeEntryPoints([_FakeEntryPoint("uppercase", _UppercaseVerifier)]),
        )
        _seed_approved_result(tmp_path, "dataset-id", {"uppercase": "SOMETHING-ELSE"})

        result = IrDatasetsApprovalTest().verify("dataset-id")

        comparison = result["__approval_comparison__"]
        assert comparison["matches"] is False
        assert len(comparison["differences"]) == 1
        assert "uppercase" in comparison["differences"][0]
        printed = capsys.readouterr().out
        # The summary reports only that (and how many) differences were
        # found, not their full text -- the detail stays on the returned
        # dict for anyone who wants it.
        assert "differ from the previously approved results" in printed
        assert "1 difference" in printed
        assert comparison["differences"][0] not in printed

    def test_verify_tolerates_small_float_differences_against_an_approved_snapshot(
        tmp_path, monkeypatch
    ) -> None:
        import ir_datasets

        class _FloatVerifier:
            def verify(self, dataset_id: str) -> float:
                return 0.34331269929286764

        monkeypatch.setattr(ir_datasets.util, "home_path", lambda: tmp_path)
        monkeypatch.setattr(
            importlib.metadata,
            "entry_points",
            lambda: _FakeEntryPoints([_FakeEntryPoint("score", _FloatVerifier)]),
        )
        _seed_approved_result(tmp_path, "dataset-id", {"score": 0.34331265929286764})

        result = IrDatasetsApprovalTest().verify("dataset-id")

        assert result["__approval_comparison__"] == {"matches": True, "differences": []}

    def test_verify_html_report_highlights_differences_when_waiting_for_approval(
        tmp_path, monkeypatch
    ) -> None:
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
        _seed_approved_result(tmp_path, "dataset-id", {"uppercase": "SOMETHING-ELSE"})

        result = IrDatasetsApprovalTest().verify("dataset-id", wait_for_approval=True)

        report_html = Path(result["__html_report__"]).read_text()
        assert "table-danger" in report_html
        assert "re-execution" in report_html
        assert "approved" in report_html
        assert "SOMETHING-ELSE" in report_html
        assert "DATASET-ID" in report_html

    def test_verify_html_report_has_no_diff_highlighting_when_results_match(
        tmp_path, monkeypatch
    ) -> None:
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
        _seed_approved_result(tmp_path, "dataset-id", {"uppercase": "DATASET-ID"})

        result = IrDatasetsApprovalTest().verify("dataset-id", wait_for_approval=True)

        report_html = Path(result["__html_report__"]).read_text()
        assert "table-danger" not in report_html

    def test_verify_html_report_has_no_diff_highlighting_without_wait_for_approval(
        tmp_path, monkeypatch
    ) -> None:
        import ir_datasets

        monkeypatch.setattr(ir_datasets.util, "home_path", lambda: tmp_path)
        monkeypatch.setattr(
            importlib.metadata,
            "entry_points",
            lambda: _FakeEntryPoints([_FakeEntryPoint("uppercase", _UppercaseVerifier)]),
        )
        _seed_approved_result(tmp_path, "dataset-id", {"uppercase": "SOMETHING-ELSE"})

        result = IrDatasetsApprovalTest().verify("dataset-id", render_as_html=True)

        report_html = Path(result["__html_report__"]).read_text()
        assert "table-danger" not in report_html

    def test_cached_approved_result_returns_none_when_nothing_was_approved(
        tmp_path, monkeypatch
    ) -> None:
        import ir_datasets

        monkeypatch.setattr(ir_datasets.util, "home_path", lambda: tmp_path)

        assert IrDatasetsApprovalTest.cached_approved_result("dataset-id") is None

    def test_cached_approved_result_returns_a_previously_approved_snapshot(
        tmp_path, monkeypatch
    ) -> None:
        import ir_datasets

        monkeypatch.setattr(ir_datasets.util, "home_path", lambda: tmp_path)
        _seed_approved_result(tmp_path, "dataset-id", {"uppercase": "DATASET-ID"})

        assert IrDatasetsApprovalTest.cached_approved_result("dataset-id") == {
            "uppercase": "DATASET-ID"
        }
