"""Tests for :mod:`approval_tests_ir_datasets.approval_server`: a real HTTP
server is started on an ephemeral port, driven by a background thread
playing the role of a person clicking "Approve"/"Deny" in a browser -- no
mocking of ``http.server`` itself, since the whole point is to exercise the
real request/response cycle.
"""
import threading
import time
import urllib.request

from approval_tests_ir_datasets.approval_server import run_approval_server


def _click(port: int, path: str, delay: float = 0.05) -> None:
    """Simulate a browser POSTing to ``path`` shortly after the server
    starts -- long enough that :func:`run_approval_server` is already
    blocked in its request loop by the time this fires."""
    time.sleep(delay)
    urllib.request.urlopen(
        urllib.request.Request(f"http://localhost:{port}/{path}", method="POST")
    ).read()


class _PortCapturingThread(threading.Thread):
    """Runs :func:`run_approval_server`, capturing its return value and the
    port it printed (parsed from stdout) so the clicking thread can target
    it -- ``run_approval_server`` itself picks the port (``port=0``) and
    only reveals it via the "Approve or Deny at ..." message it prints.
    """

    def __init__(self, html: str) -> None:
        super().__init__()
        self.html = html
        self.result = None
        self.port = None
        self._port_ready = threading.Event()

    def run(self) -> None:
        import builtins

        original_print = builtins.print

        def capturing_print(*args, **kwargs):
            message = " ".join(str(arg) for arg in args)
            if "localhost:" in message and self.port is None:
                self.port = int(message.rsplit(":", 1)[1])
                self._port_ready.set()
            original_print(*args, **kwargs)

        builtins.print = capturing_print
        try:
            self.result = run_approval_server(self.html, port=0)
        finally:
            builtins.print = original_print

    def wait_for_port(self, timeout: float = 5) -> int:
        assert self._port_ready.wait(timeout), "server never printed its port"
        return self.port


def test_serves_the_given_html_over_get() -> None:
    server_thread = _PortCapturingThread("<html><body>hello</body></html>")
    server_thread.start()
    port = server_thread.wait_for_port()

    response = urllib.request.urlopen(f"http://localhost:{port}/").read().decode("utf-8")
    assert "hello" in response
    assert "Approve" in response
    assert "Deny" in response

    urllib.request.urlopen(
        urllib.request.Request(f"http://localhost:{port}/deny", method="POST")
    ).read()
    server_thread.join(timeout=5)
    assert server_thread.result is False


def test_approve_stops_the_server_and_returns_true() -> None:
    server_thread = _PortCapturingThread("<html><body>hello</body></html>")
    server_thread.start()
    port = server_thread.wait_for_port()

    click_thread = threading.Thread(target=_click, args=(port, "approve"))
    click_thread.start()
    server_thread.join(timeout=5)
    click_thread.join(timeout=5)

    assert server_thread.result is True


def test_deny_stops_the_server_and_returns_false() -> None:
    server_thread = _PortCapturingThread("<html><body>hello</body></html>")
    server_thread.start()
    port = server_thread.wait_for_port()

    click_thread = threading.Thread(target=_click, args=(port, "deny"))
    click_thread.start()
    server_thread.join(timeout=5)
    click_thread.join(timeout=5)

    assert server_thread.result is False
