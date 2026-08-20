"""Tests for the liquidation proxy.

No network. Every test builds its own 5-minute open interest frame or its
own hourly cache, so nothing here downloads from Binance.
"""

import numpy as np
import pandas as pd
import pytest

import liqproxy


def oi_frame(rows, start="2024-03-05 00:00"):
    """Build a 5-minute open interest frame from (contracts, price) pairs.

    Binance publishes contracts and notional value, so the price is folded
    back into the value column the way the real files carry it.
    """
    idx = pd.date_range(start, periods=len(rows), freq="5min")
    oi = np.array([r[0] for r in rows], dtype=float)
    price = np.array([r[1] for r in rows], dtype=float)
    return pd.DataFrame({
        "create_time": idx,
        "sum_open_interest": oi,
        "sum_open_interest_value": oi * price,
    })


def hourly(values, start="2024-03-05 00:00", periods=None):
    """An hourly proxy cache where both columns hold the same values."""
    n = periods or len(values)
    idx = pd.date_range(start, periods=n, freq="h", name="time")
    return pd.DataFrame({"LongLiq": values, "ShortLiq": values}, index=idx)


# ---------------------------------------------------------------------------
# symbol and path handling

@pytest.mark.parametrize("symbol,expected", [
    ("BTC/USDT", "BTCUSDT"),
    ("ETH/USDT", "ETHUSDT"),
    ("BTC-USDT", "BTCUSDT"),
    ("btc/usdt", "BTCUSDT"),
])
def test_venue_symbol(symbol, expected):
    assert liqproxy.venue_symbol(symbol) == expected


def test_cache_path_is_per_symbol():
    btc = liqproxy.cache_path("BTC/USDT")
    eth = liqproxy.cache_path("ETH/USDT")
    assert btc != eth
    assert btc.endswith("BTC-USDT_liqproxy_1h.csv")


# ---------------------------------------------------------------------------
# the proxy itself

def test_falling_oi_with_falling_price_is_a_long_flush():
    # 100 contracts closed while price drops, at $50,000 = $5,000,000
    df = oi_frame([(1000, 50_000), (900, 49_000)])
    out = liqproxy.hour_totals(df)
    assert out["LongLiq"].sum() == pytest.approx(100 * 49_000)
    assert out["ShortLiq"].sum() == 0


def test_falling_oi_with_rising_price_is_a_short_flush():
    df = oi_frame([(1000, 50_000), (900, 51_000)])
    out = liqproxy.hour_totals(df)
    assert out["ShortLiq"].sum() == pytest.approx(100 * 51_000)
    assert out["LongLiq"].sum() == 0


def test_rising_oi_is_not_a_flush():
    """Positions being opened, however fast, is not forced closing."""
    df = oi_frame([(1000, 50_000), (1200, 49_000), (1400, 51_000)])
    out = liqproxy.hour_totals(df)
    assert out["LongLiq"].sum() == 0
    assert out["ShortLiq"].sum() == 0


def test_flat_price_is_counted_on_neither_side():
    df = oi_frame([(1000, 50_000), (900, 50_000)])
    out = liqproxy.hour_totals(df)
    assert out["LongLiq"].sum() == 0
    assert out["ShortLiq"].sum() == 0


def test_zero_open_interest_rows_are_dropped_not_divided_by():
    """A zero-contract row would make price infinite. It must be skipped."""
    df = oi_frame([(1000, 50_000), (0, 1), (900, 49_000)])
    out = liqproxy.hour_totals(df)
    assert np.isfinite(out.to_numpy()).all()
    assert out["LongLiq"].sum() == pytest.approx(100 * 49_000)


def test_totals_land_in_the_right_hour():
    rows = [(1000, 50_000)] + [(1000, 50_000)] * 11   # 00:00-00:55 quiet
    rows += [(900, 49_000)]                           # 01:00 long flush
    out = liqproxy.hour_totals(oi_frame(rows))
    assert out.loc["2024-03-05 00:00", "LongLiq"] == 0
    assert out.loc["2024-03-05 01:00", "LongLiq"] == pytest.approx(100 * 49_000)


def test_too_few_rows_gives_an_empty_frame_not_a_crash():
    assert liqproxy.hour_totals(oi_frame([(1000, 50_000)])).empty


# ---------------------------------------------------------------------------
# resampling to a timeframe

def test_to_timeframe_sums_hours_into_bars():
    liq = hourly([1.0] * 48)
    daily = liqproxy.to_timeframe(liq, "1d")
    assert len(daily) == 2
    assert (daily["LongLiq"] == 24.0).all()


def test_to_timeframe_bars_line_up_with_binance_candles():
    """12h bars must start at 00:00 and 12:00, not at the data's first hour."""
    liq = hourly([1.0] * 24, start="2024-03-05 07:00")
    bars = liqproxy.to_timeframe(liq, "12h")
    assert list(bars.index.hour.unique()) == [12]  # only 12:00-23:59 is complete


def test_to_timeframe_drops_partly_covered_bars():
    """A day with only 20 of 24 hours cached must not report a part total."""
    liq = hourly([1.0] * 20)          # 00:00-19:00 only
    assert liqproxy.to_timeframe(liq, "1d").empty


def test_to_timeframe_refuses_a_timeframe_finer_than_the_cache():
    with pytest.raises(ValueError, match="finer than the hourly proxy"):
        liqproxy.to_timeframe(hourly([1.0] * 24), "5min")


# ---------------------------------------------------------------------------
# attaching to a price frame

def price_frame(periods, freq, start="2024-03-05"):
    idx = pd.date_range(start, periods=periods, freq=freq)
    return pd.DataFrame({
        "Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 10.0,
    }, index=idx)


@pytest.mark.parametrize("freq,periods,bars_per_day", [
    ("1d", 3, 1), ("12h", 6, 2), ("4h", 18, 6),
])
def test_attach_keeps_every_price_bar_it_covers(tmp_path, freq, periods,
                                                bars_per_day):
    """The bug this guards: joining daily liquidations onto a 12h price
    frame silently kept only the 00:00 bars and threw the rest away."""
    cache = tmp_path / "liq.csv"
    hourly([1.0] * 72).to_csv(cache)          # 3 full days
    out = liqproxy.attach(price_frame(periods, freq), timeframe=freq,
                          cache=str(cache))
    assert len(out) == periods
    assert out["LongLiq"].sum() == pytest.approx(72.0)


def test_attach_adds_both_columns(tmp_path):
    cache = tmp_path / "liq.csv"
    hourly([2.0] * 24).to_csv(cache)
    out = liqproxy.attach(price_frame(1, "1d"), timeframe="1d", cache=str(cache))
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume",
                                 "LongLiq", "ShortLiq"]


def test_attach_raises_when_nothing_overlaps(tmp_path):
    """Better a clear error than an empty frame that looks like a bug in
    whichever strategy asked for the data."""
    cache = tmp_path / "liq.csv"
    hourly([1.0] * 24, start="2021-01-01").to_csv(cache)
    with pytest.raises(RuntimeError, match="no liquidation proxy overlaps"):
        liqproxy.attach(price_frame(3, "1d"), timeframe="1d", cache=str(cache))


def test_build_is_append_only(tmp_path, monkeypatch):
    """A refresh must never rewrite hours it already has."""
    cache = tmp_path / "liq.csv"
    existing = hourly([7.0] * 24, start="2024-03-05")
    existing.to_csv(cache)

    monkeypatch.setattr(liqproxy, "first_available_day",
                        lambda symbol: pd.Timestamp("2024-03-05"))
    monkeypatch.setattr(liqproxy, "fetch_day",
                        lambda symbol, day: oi_frame(
                            [(1000, 50_000), (900, 49_000)],
                            start=f"{day:%Y-%m-%d} 00:00"))

    out = liqproxy.build("BTC/USDT", end="2024-03-07", cache=str(cache))

    # the cached day kept its old values, the new day was added
    assert (out.loc["2024-03-05", "LongLiq"] == 7.0).all()
    assert "2024-03-06" in out.index.normalize().astype(str).tolist()


def test_build_skips_days_binance_has_no_file_for(tmp_path, monkeypatch):
    cache = tmp_path / "liq.csv"
    monkeypatch.setattr(liqproxy, "first_available_day",
                        lambda symbol: pd.Timestamp("2024-03-05"))
    monkeypatch.setattr(liqproxy, "fetch_day", lambda symbol, day: None)
    out = liqproxy.build("BTC/USDT", end="2024-03-08", cache=str(cache))
    assert out.empty
