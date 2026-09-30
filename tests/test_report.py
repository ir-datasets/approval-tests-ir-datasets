from pathlib import Path

from approval_tests_ir_datasets.report import render_html_report, write_html_report


def test_render_html_report_links_ir_datasets_com_assets() -> None:
    html = render_html_report("dataset-id", ["dataset-id"], {"table_line_count": {"length": 3}})

    assert "https://cdn.jsdelivr.net/npm/@tabler/core@1/dist/css/tabler.min.css" in html
    assert "https://demo-v2.ir-datasets.com/static/style.css" in html
    assert "dataset-id" in html


def test_render_html_report_renders_known_verifiers() -> None:
    results = {
        "table_line_count": {"length": 1400},
        "qrel_stats": {
            "number_of_queries": 2,
            "relevance_counts": {"0": 3, "1": 5},
        },
        "default_text": {
            "samples": [{"id": "doc1", "text": "hello world"}],
        },
        "pyterrier_index": {
            "num_documents": 1400,
            "num_terms": 100,
            "num_tokens": 5000,
        },
        "retrieval": {
            "num_queries": 10,
            "runs": {
                "BM25": {"num_results": 1000},
                "DirichletLM": {
                    "num_results": 1000,
                    "jaccard_similarity_to_bm25": {"top_10": 0.5, "top_100": 0.6},
                },
            },
        },
        "evaluation": {
            "BM25": {"nDCG@10": 0.4, "recip_rank": 0.7, "Recall@100": 0.9},
        },
    }

    html = render_html_report("irds:cranfield", ["irds:cranfield"], results)

    assert "1400" in html
    assert "hello world" in html
    assert "DirichletLM" in html
    assert "0.4" in html


def test_render_html_report_falls_back_to_json_for_unknown_verifiers() -> None:
    html = render_html_report("dataset-id", ["dataset-id"], {"custom_verifier": {"foo": "bar"}})

    assert "custom_verifier" in html
    assert "&quot;foo&quot;: &quot;bar&quot;" in html


def test_render_html_report_renders_a_section_per_sub_dataset() -> None:
    results = {
        "irds:cranfield": {},
        "irds:cranfield-docs": {"table_line_count": {"length": 1400}},
    }

    html = render_html_report(
        "irds:cranfield", ["irds:cranfield", "irds:cranfield-docs"], results
    )

    assert "irds:cranfield-docs" in html
    assert "1400" in html


def test_write_html_report_writes_an_openable_file(tmp_path) -> None:
    report_path = write_html_report("dataset-id", ["dataset-id"], {"table_line_count": {"length": 3}})

    assert isinstance(report_path, Path)
    assert report_path.is_file()
    assert report_path.suffix == ".html"
    content = report_path.read_text()
    assert "dataset-id" in content
    assert "3" in content


def test_render_html_report_without_approved_results_shows_no_diff_markup() -> None:
    html = render_html_report("dataset-id", ["dataset-id"], {"table_line_count": {"length": 3}})

    assert "table-danger" not in html
    assert "differs from the approved snapshot" not in html.lower()
    assert "alert-danger" not in html


def test_render_html_report_shows_no_diff_markup_when_approved_results_match() -> None:
    html = render_html_report(
        "dataset-id",
        ["dataset-id"],
        {"table_line_count": {"length": 3}},
        approved_results={"table_line_count": {"length": 3}},
    )

    assert "table-danger" not in html
    assert "alert-danger" not in html


def test_render_html_report_highlights_differing_values_in_red() -> None:
    html = render_html_report(
        "dataset-id",
        ["dataset-id"],
        {"table_line_count": {"length": 3}},
        approved_results={"table_line_count": {"length": 1400}},
    )

    assert "table-danger" in html
    assert "alert-danger" in html
    assert "re-execution" in html
    assert "approved" in html
    assert "length" in html
    # both the re-executed and the previously approved value are shown.
    assert ">3<" in html
    assert ">1400<" in html


def test_render_html_report_highlights_missing_and_unexpected_keys() -> None:
    html = render_html_report(
        "dataset-id",
        ["dataset-id"],
        {"qrel_stats": {"number_of_queries": 2}},
        approved_results={"qrel_stats": {"number_of_queries": 2, "relevance_counts": {"0": 1}}},
    )

    assert "table-danger" in html
    assert "absent" in html


def test_render_html_report_diff_highlighting_covers_each_sub_dataset_section() -> None:
    results = {
        "irds:cranfield": {},
        "irds:cranfield-docs": {"table_line_count": {"length": 1300}},
    }
    approved_results = {
        "irds:cranfield": {},
        "irds:cranfield-docs": {"table_line_count": {"length": 1400}},
    }

    html = render_html_report(
        "irds:cranfield", ["irds:cranfield", "irds:cranfield-docs"], results, approved_results
    )

    assert "table-danger" in html
    assert "irds:cranfield-docs" in html
