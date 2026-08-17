"""Fetch and cache crypto price data.

Downloads OHLCV candles (open, high, low, close, volume) from an exchange
via ccxt and saves them to a local CSV so we only download once.

Refreshes pin venue = Binance, drop any bar whose close is still in the
future, and append new closed timestamps only. Existing OHLC is never
rewritten.

Run directly to fetch the default dataset:
    python data.py
"""

import os
import time

import ccxt
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

VENUE = "binance"
FALLBACK_EXCHANGES = ["bybit", "okx", "kraken"]


def bar_width(timeframe):
    """Timedelta for a ccxt timeframe string (e.g. 12h, 1d)."""
    return pd.Timedelta(timeframe)


def _now_naive(now=None):
    ts = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts


def drop_unclosed(df, timeframe, now=None):
    """Drop bars whose close (open + bar width) is still in the future.

    ccxt timestamps are candle *open* times.
    """
    if df is None or len(df) == 0:
        return df
    now = _now_naive(now)
    closes = df.index + bar_width(timeframe)
    return df.loc[closes <= now].copy()


def append_only(existing, fresh):
    """Keep existing OHLC for known timestamps. Append new timestamps only."""
    if existing is None or len(existing) == 0:
        return fresh.copy() if fresh is not None else existing
    if fresh is None or len(fresh) == 0:
        return existing.copy()
    new = fresh.loc[~fresh.index.isin(existing.index)]
    return pd.concat([existing, new]).sort_index()


def cache_path(symbol, timeframe):
    safe = symbol.replace("/", "-")
    return os.path.join(DATA_DIR, f"{safe}_{timeframe}.csv")


def venues_to_try(allow_fallback):
    names = [VENUE]
    if allow_fallback:
        names.extend(n for n in FALLBACK_EXCHANGES if n != VENUE)
    return names


def _write_venue(path, name):
    with open(path + ".venue", "w", encoding="utf-8") as fh:
        fh.write(name + "\n")


def _read_cache(path):
    return pd.read_csv(path, index_col="time", parse_dates=True)


def _write_cache(path, df):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    df.to_csv(path)


def fetch_ohlcv(symbol="BTC/USDT", timeframe="12h", since="2017-09-01",
                allow_fallback=False, now=None, _get_exchange=None):
    """Download OHLCV history and return closed bars only.

    Refreshes try Binance only (`allow_fallback=False`) and fail if it
    fails. A first-time download of a missing symbol may walk the
    fallback list and records which venue succeeded.
    """
    get_exchange = _get_exchange or (
        lambda name: getattr(ccxt, name)({"enableRateLimit": True}))
    since_ms = int(pd.Timestamp(since).timestamp() * 1000)
    last_error = None
    names = venues_to_try(allow_fallback)
    for name in names:
        try:
            exchange = get_exchange(name)
            all_rows = []
            cursor = since_ms
            while True:
                rows = exchange.fetch_ohlcv(symbol, timeframe, since=cursor, limit=1000)
                if not rows:
                    break
                all_rows.extend(rows)
                next_cursor = rows[-1][0] + 1
                if next_cursor <= cursor:
                    break
                cursor = next_cursor
                if len(rows) < 1000:
                    break
                time.sleep(exchange.rateLimit / 1000)
            if all_rows:
                print(f"Fetched {len(all_rows)} candles from {name}")
                df = pd.DataFrame(
                    all_rows, columns=["time", "Open", "High", "Low", "Close", "Volume"]
                )
                df["time"] = pd.to_datetime(df["time"], unit="ms")
                df = df.drop_duplicates(subset="time").set_index("time").sort_index()
                df = drop_unclosed(df, timeframe, now=now)
                df.attrs["venue"] = name
                return df
        except Exception as e:
            last_error = e
            print(f"{name} failed: {e}")
            if not allow_fallback:
                raise RuntimeError(f"{name} failed: {e}") from e
    raise RuntimeError(f"All exchanges failed. Last error: {last_error}")


def load(symbol="BTC/USDT", timeframe="12h", since="2017-09-01", refresh=False,
         now=None):
    """Load candles from the local cache, downloading first if needed.

    `refresh=True` uses the same append-only path as `update()`.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    path = cache_path(symbol, timeframe)
    if os.path.exists(path) and refresh:
        return update(symbol, timeframe, since, now=now)
    if os.path.exists(path):
        return drop_unclosed(_read_cache(path), timeframe, now=now)
    df = fetch_ohlcv(symbol, timeframe, since, allow_fallback=True, now=now)
    _write_cache(path, df)
    venue = df.attrs.get("venue")
    if venue:
        _write_venue(path, venue)
    print(f"Saved {len(df)} candles to {path}")
    return df


def update(symbol="BTC/USDT", timeframe="12h", since="2017-09-01", now=None):
    """Append newly closed candles. Never rewrite existing closed OHLC.

    Pin venue = Binance. Unclosed bars are not written. A leftover
    unclosed last row from an older writer is dropped from the committed
    set so the closed version can be stored once.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    path = cache_path(symbol, timeframe)
    if not os.path.exists(path):
        return load(symbol, timeframe, since, now=now)
    closed = drop_unclosed(_read_cache(path), timeframe, now=now)
    start = closed.index[-1].isoformat() if len(closed) else since
    fresh = fetch_ohlcv(symbol, timeframe, since=start, allow_fallback=False,
                        now=now)
    out = append_only(closed, fresh)
    _write_cache(path, out)
    return out


def split_holdout(df, months=12):
    """Split a price frame into (working set, hold-out).

    The hold-out is the final `months` months of data. Nothing in the
    optimisation, walk-forward or verdict stages may see it.
    Returns (work, holdout). `holdout` may be empty if the data is short.
    """
    cutoff = df.index[-1] - pd.DateOffset(months=months)
    return df[df.index <= cutoff], df[df.index > cutoff]


def load_yahoo(symbol, since="2018-01-01", refresh=False):
    """Load daily candles for stocks/ETFs from Yahoo Finance's public
    chart API (free, no key, no extra library)."""
    import json
    import urllib.request

    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"yahoo_{symbol}_1d.csv")
    if os.path.exists(path) and not refresh:
        return pd.read_csv(path, index_col="time", parse_dates=True)
    p1 = int(pd.Timestamp(since).timestamp())
    p2 = int(time.time())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?interval=1d&period1={p1}&period2={p2}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    result = payload["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    df = pd.DataFrame({
        "time": pd.to_datetime(result["timestamp"], unit="s").normalize(),
        "Open": quote["open"], "High": quote["high"],
        "Low": quote["low"], "Close": quote["close"],
        "Volume": quote["volume"],
    }).dropna().set_index("time").sort_index()
    df.to_csv(path)
    print(f"Saved {len(df)} candles to {path}")
    return df


if __name__ == "__main__":
    df = load()
    print(df.tail())
