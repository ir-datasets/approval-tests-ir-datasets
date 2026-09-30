"""Renders :class:`~approval_tests_ir_datasets.IrDatasetsApprovalTest` results
as a single, self-contained HTML report.

The report deliberately reuses the look and feel of
`ir-datasets.com <https://ir-datasets.com>`_ (see
https://demo-v2.ir-datasets.com/) rather than shipping a bespoke stylesheet:
it links the same `Tabler <https://tabler.io/>`_ CSS/JS build (via jsDelivr,
the CDN ir-datasets.com itself uses) plus ir-datasets.com's own small
``style.css`` (for its category badge colors/icons), and borrows its card,
table and badge markup conventions. This keeps a locally generated report
visually consistent with the hosted site a dataset id can be looked up on,
without vendoring any of its template files.
"""
import json
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional

from .comparison import MISSING, diff_details, values_match

#: Base URL ir-datasets.com's own static assets are fetched from, so the
#: report visually matches https://demo-v2.ir-datasets.com/ without
#: vendoring any of its files.
_IR_DATASETS_COM_BASE_URL = "https://demo-v2.ir-datasets.com"

_TABLER_CSS_URL = "https://cdn.jsdelivr.net/npm/@tabler/core@1/dist/css/tabler.min.css"
_TABLER_JS_URL = "https://cdn.jsdelivr.net/npm/@tabler/core@1/dist/js/tabler.min.js"
_IR_DATASETS_COM_CSS_URL = f"{_IR_DATASETS_COM_BASE_URL}/static/style.css"

#: Human-readable titles for the built-in verifiers' entry point names (see
#: ``pyproject.toml``'s ``[project.entry-points."approval_tests_ir_datasets.verifiers"]``
#: table), used as each result section's card header. A verifier not listed
#: here (e.g. a third-party plugin) falls back to its raw entry point name.
_VERIFIER_TITLES = {
    "table_line_count": "Record count",
    "qrel_stats": "Qrels statistics",
    "pyterrier_index": "PyTerrier index",
    "default_text": "Sampled records",
    "retrieval": "Retrieval",
    "evaluation": "Evaluation",
}


def _card(title: str, body_html: str) -> str:
    return (
        '<div class="card mt-3">'
        f'<div class="card-header"><h3 class="card-title">{escape(title)}</h3></div>'
        f'<div class="card-body">{body_html}</div>'
        "</div>"
    )


def _key_value_table(rows: List[tuple]) -> str:
    body = "".join(
        f"<tr><td class=\"text-secondary w-1\">{escape(str(key))}</td><td>{value}</td></tr>"
        for key, value in rows
    )
    return (
        '<div class="table-responsive"><table class="table table-vcenter card-table">'
        f"<tbody>{body}</tbody></table></div>"
    )


def _render_table_line_count(result: Dict[str, Any]) -> str:
    return _key_value_table([("Records", result.get("length"))])


def _render_qrel_stats(result: Dict[str, Any]) -> str:
    relevance_rows = "".join(
        f"<tr><td class=\"text-secondary w-1\">{escape(str(label))}</td><td>{count}</td></tr>"
        for label, count in sorted(result.get("relevance_counts", {}).items())
    )
    return (
        _key_value_table([("Queries with qrels", result.get("number_of_queries"))])
        + '<div class="table-responsive mt-2"><table class="table table-vcenter card-table">'
        "<thead><tr><th>Relevance label</th><th>Count</th></tr></thead>"
        f"<tbody>{relevance_rows}</tbody></table></div>"
    )


def _render_pyterrier_index(result: Dict[str, Any]) -> str:
    return _key_value_table(
        [
            ("Documents", result.get("num_documents")),
            ("Terms", result.get("num_terms")),
            ("Tokens", result.get("num_tokens")),
        ]
    )


def _render_default_text(result: Dict[str, Any]) -> str:
    samples_html = "".join(
        '<div class="mb-2"><div class="text-secondary">'
        f'<code>{escape(str(sample.get("id")))}</code></div>'
        f'<pre class="bg-dark-lt rounded p-2 mb-0 overflow-auto">{escape(str(sample.get("text")))}</pre>'
        "</div>"
        for sample in result.get("samples", [])
    )
    return samples_html or '<span class="text-secondary">No samples.</span>'


def _render_retrieval(result: Dict[str, Any]) -> str:
    runs = result.get("runs", {})
    header = "<tr><th>Approach</th><th>Results</th><th>Jaccard@10 to BM25</th><th>Jaccard@100 to BM25</th></tr>"
    rows = []
    for name, run in runs.items():
        similarity = run.get("jaccard_similarity_to_bm25", {})
        rows.append(
            "<tr>"
            f"<td><code>{escape(str(name))}</code></td>"
            f"<td>{run.get('num_results')}</td>"
            f"<td>{similarity.get('top_10', '&mdash;')}</td>"
            f"<td>{similarity.get('top_100', '&mdash;')}</td>"
            "</tr>"
        )
    return (
        _key_value_table([("Queries", result.get("num_queries"))])
        + '<div class="table-responsive mt-2"><table class="table table-vcenter card-table">'
        f"<thead>{header}</thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _render_evaluation(result: Dict[str, Any]) -> str:
    metric_names: List[str] = []
    for metrics in result.values():
        for metric_name in metrics:
            if metric_name not in metric_names:
                metric_names.append(metric_name)

    header = "<tr><th>Approach</th>" + "".join(f"<th>{escape(name)}</th>" for name in metric_names) + "</tr>"
    rows = []
    for approach, metrics in result.items():
        cells = "".join(f"<td>{metrics.get(name, '&mdash;')}</td>" for name in metric_names)
        rows.append(f"<tr><td><code>{escape(str(approach))}</code></td>{cells}</tr>")
    return (
        '<div class="table-responsive"><table class="table table-vcenter card-table">'
        f"<thead>{header}</thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _render_fallback(result: Any) -> str:
    return f'<pre class="bg-dark-lt rounded p-2 mb-0 overflow-auto">{escape(json.dumps(result, indent=2, sort_keys=True))}</pre>'


def _format_diff_value(value: Any) -> str:
    if value is MISSING:
        return '<span class="text-white-50">(absent)</span>'
    if isinstance(value, (dict, list)):
        return f'<pre class="bg-dark-lt rounded p-2 mb-0 overflow-auto">{escape(json.dumps(value, indent=2, sort_keys=True))}</pre>'
    return escape(str(value))


def _render_diff_table(differences: List[Dict[str, Any]]) -> str:
    """A small table with one *pair* of rows per entry in ``differences``
    (as returned by :func:`~approval_tests_ir_datasets.comparison.diff_details`)
    -- a "re-execution" row and an "approved" row, both styled red -- so a
    reviewer can see exactly which value changed, and from/to what.
    """
    rows = []
    for detail in differences:
        label = escape(detail["path"])
        for side, value in (("re-execution", detail["actual"]), ("approved", detail["approved"])):
            rows.append(
                '<tr class="table-danger">'
                f'<td class="text-danger w-1">{label} '
                f'<span class="badge bg-red text-white ms-1">{side}</span></td>'
                f'<td class="text-danger">{_format_diff_value(value)}</td>'
                "</tr>"
            )
    return (
        '<div class="table-responsive mt-2"><table class="table table-vcenter card-table">'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


#: Dispatch table from a verifier's entry point name (see
#: ``_VERIFIER_TITLES``) to a function rendering its result as an HTML
#: fragment. Verifiers without a dedicated renderer here fall back to
#: :func:`_render_fallback` (pretty-printed JSON).
_VERIFIER_RENDERERS = {
    "table_line_count": _render_table_line_count,
    "qrel_stats": _render_qrel_stats,
    "pyterrier_index": _render_pyterrier_index,
    "default_text": _render_default_text,
    "retrieval": _render_retrieval,
    "evaluation": _render_evaluation,
}


def _render_dataset_section(
    dataset_id: str, flat_result: Dict[str, Any], approved_flat: Optional[Dict[str, Any]] = None
) -> str:
    cards = []
    for verifier_name, result in flat_result.items():
        renderer = _VERIFIER_RENDERERS.get(verifier_name, _render_fallback)
        try:
            body_html = renderer(result)
        except Exception:  # pragma: no cover - defensive, falls back to raw JSON
            body_html = _render_fallback(result)

        if approved_flat is not None and verifier_name in approved_flat:
            approved_value = approved_flat[verifier_name]
            if not values_match(approved_value, result):
                differences = diff_details(approved_value, result)
                if differences:
                    body_html += (
                        '<div class="mt-3">'
                        '<div class="text-danger fw-bold mb-1">'
                        "&#9888; Differs from the approved snapshot"
                        "</div>" + _render_diff_table(differences) + "</div>"
                    )

        title = _VERIFIER_TITLES.get(verifier_name, verifier_name)
        cards.append(_card(title, body_html))

    return (
        '<h2 class="mb-3 mt-4">'
        f'<code class="select">{escape(dataset_id)}</code>'
        "</h2>" + "".join(cards)
    )


def render_html_report(
    root_dataset_id: str,
    dataset_ids: List[str],
    results: Dict[str, Any],
    approved_results: Optional[Dict[str, Any]] = None,
) -> str:
    """Render ``results`` (as produced by
    :meth:`~approval_tests_ir_datasets.IrDatasetsApprovalTest.verify`) as a
    single, self-contained HTML page.

    ``dataset_ids`` is the full list of dataset ids ``results`` covers --
    just ``[root_dataset_id]`` for a single-resource result, or
    ``root_dataset_id`` plus every sub resource's qualified name for a
    benchmark's aggregated result (see ``verify``'s docstring for the
    corresponding two result shapes) -- so this doesn't need to guess which
    shape ``results`` is in.

    ``approved_results``, if given, is the previously approved snapshot in
    the same shape as ``results`` (see ``verify``'s ``wait_for_approval``):
    when a verifier's freshly computed value differs from its approved
    counterpart, the report highlights that difference inline (a red
    "re-execution" vs. "approved" row pair per differing value) instead of
    silently rendering only the new value.
    """
    if len(dataset_ids) == 1:
        sections = "".join(
            _render_dataset_section(dataset_id, results, approved_results)
            for dataset_id in dataset_ids
        )
    else:
        sections = "".join(
            _render_dataset_section(
                dataset_id,
                results.get(dataset_id, {}),
                (approved_results or {}).get(dataset_id) if approved_results is not None else None,
            )
            for dataset_id in dataset_ids
        )

    banner = ""
    if approved_results is not None and not values_match(approved_results, results):
        banner = (
            '<div class="alert alert-danger mt-3" role="alert">'
            "&#9888; These results differ from the previously approved snapshot &mdash; "
            "the differing values are highlighted below."
            "</div>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{escape(root_dataset_id)} &mdash; approval-tests-ir-datasets</title>
<link rel="stylesheet" href="{_TABLER_CSS_URL}" />
<link rel="stylesheet" href="{_IR_DATASETS_COM_CSS_URL}" />
</head>
<body>
<div class="page">
  <header class="navbar navbar-expand-md navbar-dark bg-dark d-print-none sticky-top">
    <div class="container-xl">
      <h1 class="navbar-brand pe-0 pe-md-3">
        <a href="{_IR_DATASETS_COM_BASE_URL}" class="text-white text-decoration-none">ir-datasets<span style="color: #999;">.com</span></a>
      </h1>
      <div class="navbar-nav flex-row order-md-last flex-fill">
        <div class="nav-item flex-fill text-white">Approval test report</div>
      </div>
    </div>
  </header>
  <div class="page-wrapper">
    <div class="page-body">
      <div class="container-xl">
        <div class="row row-cards">
          <div class="col-12">
            <h1>Approval test report: <code>{escape(root_dataset_id)}</code></h1>
            {banner}
            {sections}
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
<script src="{_TABLER_JS_URL}"></script>
</body>
</html>
"""


def write_html_report(
    root_dataset_id: str,
    dataset_ids: List[str],
    results: Dict[str, Any],
    approved_results: Optional[Dict[str, Any]] = None,
) -> Path:
    """Render ``results`` via :func:`render_html_report` and write it as
    ``report.html`` to a freshly created temporary directory, returning
    that file's path (e.g. to be opened directly in a browser).
    """
    import tempfile

    from .paths import sanitize_dataset_id

    directory = Path(tempfile.mkdtemp(prefix="approval_tests_ir_datasets_"))
    report_path = directory / f"{sanitize_dataset_id(root_dataset_id)}.html"
    report_path.write_text(render_html_report(root_dataset_id, dataset_ids, results, approved_results))
    return report_path


__all__ = ["render_html_report", "write_html_report"]
