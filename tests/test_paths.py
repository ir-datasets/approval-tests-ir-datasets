import unittest

try:
    import ir_datasets  # noqa: F401

    IR_DATASETS_AVAILABLE = True
except ImportError:
    IR_DATASETS_AVAILABLE = False


def test_sanitize_dataset_id_replaces_unsafe_characters() -> None:
    from approval_tests_ir_datasets.paths import sanitize_dataset_id

    assert sanitize_dataset_id("irds:cranfield-docs") == "irds_cranfield-docs"
    assert sanitize_dataset_id("a/b c") == "a_b_c"


@unittest.skipUnless(IR_DATASETS_AVAILABLE, "ir_datasets is not installed")
def test_approvals_dir_is_created_under_ir_datasets_home(tmp_path, monkeypatch) -> None:
    import ir_datasets

    from approval_tests_ir_datasets.paths import approvals_dir

    monkeypatch.setattr(ir_datasets.util, "home_path", lambda: tmp_path)

    directory = approvals_dir("irds:cranfield-docs", "pyterrier_index")

    assert directory.is_dir()
    assert directory == tmp_path / "approvals" / "irds_cranfield-docs" / "pyterrier_index"
