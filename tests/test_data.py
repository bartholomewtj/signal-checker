"""Data hygiene: pin Binance, drop unclosed bars, append-only writes.

No network.
"""

import pandas as pd
import pytest

import data


def _ohlcv_frame(times, close=100.0):
    idx = pd.to_datetime(times)
    n = len(idx)
    return pd.DataFrame({
        "Open": [close] * n,
        "High": [close + 1] * n,
        "Low": [close - 1] * n,
        "Close": [float(close)] * n,
        "Volume": [1.0] * n,
    }, index=idx)


def test_unclosed_bar_is_dropped():
    now = pd.Timestamp("2026-08-17 10:00:00")
    df = _ohlcv_frame([
        "2026-08-16 00:00:00",
        "2026-08-16 12:00:00",
        "2026-08-17 00:00:00",
    ])
    out = data.drop_unclosed(df, "12h", now=now)
    assert list(out.index) == [
        pd.Timestamp("2026-08-16 00:00:00"),
        pd.Timestamp("2026-08-16 12:00:00"),
    ]


def test_closed_bar_is_kept_at_exact_close():
    now = pd.Timestamp("2026-08-17 00:00:00")
    df = _ohlcv_frame(["2026-08-16 12:00:00"])
    out = data.drop_unclosed(df, "12h", now=now)
    assert len(out) == 1


def test_append_only_does_not_rewrite_existing_ohlc():
    existing = _ohlcv_frame(["2026-08-01", "2026-08-02"], close=10.0)
    fresh = _ohlcv_frame(["2026-08-02", "2026-08-03"], close=99.0)
    out = data.append_only(existing, fresh)
    assert out.loc[pd.Timestamp("2026-08-02"), "Close"] == 10.0
    assert out.loc[pd.Timestamp("2026-08-03"), "Close"] == 99.0
    assert len(out) == 3


def test_venues_refresh_is_binance_only():
    assert data.venues_to_try(allow_fallback=False) == ["binance"]


def test_venues_first_download_may_fallback():
    names = data.venues_to_try(allow_fallback=True)
    assert names[0] == "binance"
    assert "bybit" in names


class _FakeEx:
    def __init__(self, name, rows=None, fail=False):
        self.name = name
        self.rows = rows or []
        self.fail = fail
        self.rateLimit = 0

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=1000):
        if self.fail:
            raise RuntimeError(f"{self.name} down")
        return self.rows


def test_update_does_not_try_second_exchange_when_binance_fails():
    tried = []

    def get_exchange(name):
        tried.append(name)
        return _FakeEx(name, fail=True)

    with pytest.raises(RuntimeError, match="binance failed"):
        data.fetch_ohlcv(
            "BTC/USDT", "12h", since="2026-08-01",
            allow_fallback=False, now="2026-08-17",
            _get_exchange=get_exchange,
        )
    assert tried == ["binance"]


def test_load_refresh_uses_append_only(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "DATA_DIR", str(tmp_path))
    cache = tmp_path / "BTC-USDT_12h.csv"
    seed = _ohlcv_frame(["2026-08-01 00:00:00"], close=10.0)
    seed.index.name = "time"
    seed.to_csv(cache)

    t0 = int(pd.Timestamp("2026-08-01 00:00:00").timestamp() * 1000)
    t1 = int(pd.Timestamp("2026-08-01 12:00:00").timestamp() * 1000)
    t2 = int(pd.Timestamp("2026-08-17 00:00:00").timestamp() * 1000)
    rows = [
        [t0, 10, 11, 9, 99, 1],
        [t1, 20, 21, 19, 20, 1],
        [t2, 30, 31, 29, 30, 1],
    ]

    def get_exchange(name):
        assert name == "binance"
        return _FakeEx(name, rows=rows)

    real_fetch = data.fetch_ohlcv

    def fake_fetch(symbol="BTC/USDT", timeframe="12h", since="2017-09-01",
                   allow_fallback=False, now=None, _get_exchange=None):
        assert allow_fallback is False
        return real_fetch(
            symbol, timeframe, since,
            allow_fallback=False, now=now, _get_exchange=get_exchange,
        )

    monkeypatch.setattr(data, "fetch_ohlcv", fake_fetch)
    out = data.load(
        "BTC/USDT", "12h", refresh=True,
        now=pd.Timestamp("2026-08-17 10:00:00"),
    )
    assert out.loc[pd.Timestamp("2026-08-01 00:00:00"), "Close"] == 10.0
    assert pd.Timestamp("2026-08-01 12:00:00") in out.index
    assert pd.Timestamp("2026-08-17 00:00:00") not in out.index
    on_disk = pd.read_csv(cache, index_col="time", parse_dates=True)
    assert on_disk.loc[pd.Timestamp("2026-08-01 00:00:00"), "Close"] == 10.0
    assert pd.Timestamp("2026-08-17 00:00:00") not in on_disk.index
