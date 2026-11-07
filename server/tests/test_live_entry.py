"""The billable backend MiMo check requires two explicit opt-in controls."""

import sys

import pytest

from app.agents.errors import ConfigurationError
from scripts.verify_backend_mimo import main


def test_live_backend_entry_refuses_implicit_run(monkeypatch, capsys) -> None:
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    monkeypatch.setenv("LEDGERCREW_ENABLE_LIVE_MIMO", "0")
    monkeypatch.setattr(sys, "argv", ["verify_backend_mimo", "--run-live"])
    with pytest.raises(SystemExit):
        main()
    assert "LEDGERCREW_ENABLE_LIVE_MIMO=1" in capsys.readouterr().err


def test_live_backend_entry_requires_real_key(monkeypatch) -> None:
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    monkeypatch.setenv("LEDGERCREW_ENABLE_LIVE_MIMO", "1")
    monkeypatch.setattr(sys, "argv", ["verify_backend_mimo", "--run-live"])
    with pytest.raises(ConfigurationError):
        main()
