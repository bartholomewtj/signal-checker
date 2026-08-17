"""Ledger discipline: --quick does not write; second hold-out is refused."""

from types import SimpleNamespace

import pandas as pd
import pytest

import check
import ledger


HEADER = (
    "timestamp,mode,strategy,timeframe,direction,train_bars,test_bars,"
    "p_insample,p_walkforward,wf_pf,wf_sharpe,wf_trades,verdict\n"
)

FULL = (
    "2026-08-07T12:36:29,full,devma,12h,both,1460,365,"
    "0.0399,0.0159,1.0609,0.4391,169,LOOKS REAL\n"
)

HOLDOUT = (
    "2026-08-07T13:32:34,holdout,devma,12h,both,1460,365,,,,,30,HOLDOUT\n"
)


def test_quick_and_preview_are_display_only():
    assert check.is_preview(SimpleNamespace(quick=True, preview=False))
    assert check.is_preview(SimpleNamespace(quick=False, preview=True))
    assert not check.is_preview(SimpleNamespace(quick=False, preview=False))


def test_quick_does_not_write_ledger(tmp_path, monkeypatch):
    path = tmp_path / "trials.csv"
    path.write_text(HEADER + FULL, encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    monkeypatch.setattr(check, "LEDGER", str(path))
    assert check.is_preview(SimpleNamespace(quick=True, preview=False))
    # The write path is append_trial; preview mode must not call it.
    assert path.read_text(encoding="utf-8") == before
    check.append_trial({
        "timestamp": "x", "mode": "full", "strategy": "new", "timeframe": "1d",
        "direction": "both", "train_bars": 1, "test_bars": 1,
        "p_insample": "", "p_walkforward": "", "wf_pf": "",
        "wf_sharpe": "", "wf_trades": 0, "verdict": "NO EDGE",
    }, path=str(path))
    assert path.read_text(encoding="utf-8") != before


def test_second_holdout_refused(tmp_path, monkeypatch):
    path = tmp_path / "trials.csv"
    path.write_text(HEADER + FULL + HOLDOUT, encoding="utf-8")
    monkeypatch.setattr(check, "LEDGER", str(path))
    assert check.has_holdout("devma", "12h")
    args = SimpleNamespace(
        strategy="devma", timeframe="12h", burn_holdout=False,
        train_bars=1460, test_bars=365, direction="both",
    )
    empty = pd.DataFrame(
        {"Open": [1], "High": [1], "Low": [1], "Close": [1], "Volume": [1]},
        index=pd.to_datetime(["2020-01-01"]),
    )
    with pytest.raises(SystemExit) as exc:
        check.run_holdout(args, None, empty, empty, empty, "both")
    assert exc.value.code == 2
    assert path.read_text(encoding="utf-8") == HEADER + FULL + HOLDOUT


def test_holdout_allowed_when_none_taken(tmp_path, monkeypatch):
    path = tmp_path / "trials.csv"
    path.write_text(HEADER + FULL, encoding="utf-8")
    monkeypatch.setattr(check, "LEDGER", str(path))
    assert not check.has_holdout("trend_step", "1d")


def test_trial_announcement_new_pair(tmp_path):
    path = tmp_path / "trials.csv"
    path.write_text(HEADER + FULL, encoding="utf-8")
    n_now, n_after, bar, is_new = check.trial_announcement(
        "new_idea", "12h", path=str(path))
    assert n_now == 1
    assert n_after == 2
    assert is_new
    assert bar == pytest.approx(0.025)


def test_ledger_status_prints_n_and_bar(tmp_path):
    path = tmp_path / "trials.csv"
    path.write_text(HEADER + FULL + HOLDOUT, encoding="utf-8")
    rows = ledger._rows(str(path))
    text = ledger.format_status(rows, path=str(path))
    assert "N = 1" in text
    assert "0.0500" in text
    assert "devma 12h  LOOKS REAL" in text


def test_ledger_cli_status(tmp_path, capsys):
    path = tmp_path / "trials.csv"
    path.write_text(HEADER + FULL, encoding="utf-8")
    assert ledger.main(["status", "--ledger", str(path)]) == 0
    out = capsys.readouterr().out
    assert "N = 1" in out
    assert "LOOKS REAL" in out
