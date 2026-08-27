"""Dashboard overview + DEVMA forward log. No live backtest, no holdout."""

import pandas as pd

import dashboard
import log_devma
from strategies import REGISTRY


def _trades(*rows):
    return pd.DataFrame(rows)


def test_open_long_reads_as_long():
    last = pd.Timestamp("2026-08-27")
    trades = _trades({
        "Size": 1, "EntryTime": pd.Timestamp("2026-08-20"),
        "ExitTime": pd.Timestamp("2026-08-28"),
    })
    position, signal = dashboard._position_from_trades(trades, last)
    assert position == "LONG"
    assert signal.startswith("2026-08-20")


def test_closed_trade_reads_as_flat():
    last = pd.Timestamp("2026-08-27")
    trades = _trades({
        "Size": 1, "EntryTime": pd.Timestamp("2026-08-01"),
        "ExitTime": pd.Timestamp("2026-08-10"),
    })
    position, signal = dashboard._position_from_trades(trades, last)
    assert position == "FLAT"
    assert signal.startswith("2026-08-01")


def test_devma_lo_is_long_only():
    assert "devma_lo" in REGISTRY
    assert REGISTRY["devma_lo"].direction == "long"


def test_overview_one_row_per_strategy(monkeypatch):
    monkeypatch.setattr(
        dashboard, "position_snapshot",
        lambda name, symbol, timeframe: {
            "strategy": name, "symbol": symbol, "timeframe": timeframe,
            "position": "FLAT", "last_signal": None, "last_candle": "2026-08-27",
        },
    )
    monkeypatch.setattr(dashboard, "verdicts", lambda: [])
    out = dashboard.overview("BTC/USDT", "1d")
    names = [r["strategy"] for r in out["rows"]]
    assert names == sorted(REGISTRY)
    assert all(r["error"] is None for r in out["rows"])


def test_log_skips_duplicate_candle(tmp_path, monkeypatch):
    monkeypatch.setattr(log_devma, "LOG", str(tmp_path / "devma_lo_1d.csv"))
    snap = {
        "last_candle": "2026-08-27 00:00:00",
        "position": "LONG",
        "strategy": "devma_lo",
        "symbol": "BTC/USDT",
        "timeframe": "1d",
    }
    first = log_devma.append_if_new(snap)
    second = log_devma.append_if_new(snap)
    assert first is not None
    assert first["position"] == "LONG"
    assert second is None
    text = (tmp_path / "devma_lo_1d.csv").read_text(encoding="utf-8")
    assert text.count("2026-08-27 00:00:00") == 1
