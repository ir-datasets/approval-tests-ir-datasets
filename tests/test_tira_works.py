from tira.check_format import _fmt

from approval_tests_ir_datasets import verifiers


def test_tira_works_runs_verify_installation_and_caches_success(monkeypatch, capsys) -> None:
    monkeypatch.setattr(verifiers, "_tira_installation_ok", None)
    calls = []

    def fake_verify_tira_installation(**kwargs):
        calls.append(kwargs)
        return _fmt.OK

    monkeypatch.setattr(
        "tira.io_utils.verify_tira_installation", fake_verify_tira_installation
    )

    assert verifiers._tira_works() is True
    assert verifiers._tira_works() is True

    # Only run once -- the second call returns the cached result.
    assert calls == [{"local_only": True}]
    assert "tira-cli verify-installation --local-only" not in capsys.readouterr().out


def test_tira_works_prints_hint_and_caches_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(verifiers, "_tira_installation_ok", None)
    calls = []

    def fake_verify_tira_installation(**kwargs):
        calls.append(kwargs)
        print("some diagnostic output")
        return _fmt.ERROR

    monkeypatch.setattr(
        "tira.io_utils.verify_tira_installation", fake_verify_tira_installation
    )

    assert verifiers._tira_works() is False
    assert verifiers._tira_works() is False

    # Only run once -- the second call returns the cached result.
    assert calls == [{"local_only": True}]
    output = capsys.readouterr().out
    assert "tira-cli verify-installation --local-only" in output
    assert "some diagnostic output" in output


def test_tira_works_treats_warn_status_as_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(verifiers, "_tira_installation_ok", None)

    monkeypatch.setattr(
        "tira.io_utils.verify_tira_installation", lambda **kwargs: _fmt.WARN
    )

    assert verifiers._tira_works() is False
    assert "tira-cli verify-installation --local-only" in capsys.readouterr().out
