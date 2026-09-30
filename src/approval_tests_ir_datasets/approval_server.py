"""A minimal, dependency-free HTTP server that serves a rendered HTML
approval-test report with "Approve"/"Deny" buttons appended to it, and
blocks until one of them is clicked -- see :func:`run_approval_server`.

Deliberately built on the standard library's own :mod:`http.server` rather
than a web framework: this only ever needs to answer two kinds of request
(serve the report once, then accept exactly one decision), so pulling in a
real HTTP framework would be more machinery than the job needs.
"""
import http.server
from typing import Optional

#: Appended to the report's own HTML, just before ``</body>``: two buttons
#: that POST to ``/approve``/``/deny`` and show the server's plain-text
#: response in place, so the person clicking sees confirmation without the
#: page navigating away (the server stops right after, so a navigation
#: would just hang).
_APPROVAL_WIDGET_HTML = """
<div class="card mt-3">
  <div class="card-body text-center">
    <button id="approve-btn" type="button" class="btn btn-success btn-lg mx-2">Approve</button>
    <button id="deny-btn" type="button" class="btn btn-danger btn-lg mx-2">Deny</button>
    <div id="approval-result" class="mt-3 fw-bold"></div>
  </div>
</div>
<script>
function decide(path) {
  document.getElementById('approve-btn').disabled = true;
  document.getElementById('deny-btn').disabled = true;
  fetch(path, {method: 'POST'})
    .then(function (response) { return response.text(); })
    .then(function (text) { document.getElementById('approval-result').innerText = text; });
}
document.getElementById('approve-btn').addEventListener('click', function () { decide('/approve'); });
document.getElementById('deny-btn').addEventListener('click', function () { decide('/deny'); });
</script>
"""


def _inject_approval_widget(html: str) -> str:
    if "</body>" in html:
        return html.replace("</body>", _APPROVAL_WIDGET_HTML + "</body>", 1)
    return html + _APPROVAL_WIDGET_HTML  # pragma: no cover - defensive fallback


class _Decision:
    """Shared mutable box a request handler instance (one per request) sets
    ``approved`` on, so :func:`run_approval_server`'s request loop (running
    in the same thread, between requests) can observe it."""

    def __init__(self) -> None:
        self.approved: Optional[bool] = None


def _make_handler_class(html_bytes: bytes, decision: _Decision):
    class _ApprovalHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            pass  # Quiet: verify() prints its own, higher-level messages.

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_bytes)))
            self.end_headers()
            self.wfile.write(html_bytes)

        def do_POST(self) -> None:
            if self.path == "/approve":
                decision.approved = True
                message = "Approved."
            elif self.path == "/deny":
                decision.approved = False
                message = "Denied."
            else:
                self.send_response(404)
                self.end_headers()
                return
            body = message.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return _ApprovalHandler


def run_approval_server(html: str, host: str = "localhost", port: int = 0) -> bool:
    """Serve ``html`` (with an "Approve"/"Deny" widget appended) over plain
    HTTP, print the URL to open it at, and block until one of the two
    buttons is clicked.

    Returns ``True`` if "Approve" was clicked, ``False`` if "Deny" was. The
    server only ever answers ``GET /`` (the report itself, reloadable any
    number of times before a decision) and ``POST /approve``/``POST
    /deny``; it stops -- and this function returns -- as soon as either of
    those is received, so exactly one decision is ever recorded.

    ``port`` defaults to ``0``, letting the OS pick a free port (printed as
    part of the URL) -- pass an explicit one to pin it.
    """
    decision = _Decision()
    html_bytes = _inject_approval_widget(html).encode("utf-8")
    handler_cls = _make_handler_class(html_bytes, decision)
    httpd = http.server.HTTPServer((host, port), handler_cls)
    try:
        print(f"Approve or Deny at http://{host}:{httpd.server_port}")
        while decision.approved is None:
            httpd.handle_request()
    finally:
        httpd.server_close()
    return decision.approved


__all__ = ["run_approval_server"]
