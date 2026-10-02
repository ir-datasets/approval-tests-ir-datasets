import subprocess
from types import SimpleNamespace

from approval_tests_ir_datasets import verifiers


def test_tira_works_runs_verify_installation_and_caches_success(monkeypatch, capsys) -> None:
    monkeypatch.setattr(verifiers, "_tira_installation_ok", None)
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert verifiers._tira_works() is True
    assert verifiers._tira_works() is True

    # Only run once -- the second call returns the cached result.
    assert calls == [["tira-cli", "verify-installation", "--local-only"]]
    assert "tira-cli verify-installation --local-only" not in capsys.readouterr().out


def test_tira_works_prints_hint_and_caches_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(verifiers, "_tira_installation_ok", None)
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1, stdout="out", stderr="err")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert verifiers._tira_works() is False
    assert verifiers._tira_works() is False

    # Only run once -- the second call returns the cached result.
    assert calls == [["tira-cli", "verify-installation", "--local-only"]]
    output = capsys.readouterr().out
    assert "tira-cli verify-installation --local-only" in output
    assert "out" in output
    assert "err" in output
