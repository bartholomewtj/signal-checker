"""Fetch and cache crypto price data.

Downloads OHLCV candles (open, high, low, close, volume) from an exchange
via ccxt and saves them to a local CSV so we only download once.

Run directly to fetch the default dataset:
    python data.py
"""

import os
import time

import ccxt
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Exchanges to try, in order. All are accessed without an API key.
EXCHANGES = ["binance", "bybit", "okx", "kraken"]


def fetch_ohlcv(symbol="BTC/USDT", timeframe="12h", since="2017-09-01"):
    """Download full OHLCV history and return it as a DataFrame.

    Pages through the exchange API 1000 candles at a time until we reach now.
    """
    since_ms = int(pd.Timestamp(since).timestamp() * 1000)
    last_error = None
    for name in EXCHANGES:
        try:
            exchange = getattr(ccxt, name)({"enableRateLimit": True})
            all_rows = []
            cursor = since_ms
            while True:
                rows = exchange.fetch_ohlcv(symbol, timeframe, since=cursor, limit=1000)
                if not rows:
                    break
                all_rows.extend(rows)
                # next page starts after the last candle we received
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
                return df
        except Exception as e:  # try the next exchange
            last_error = e
            print(f"{name} failed: {e}")
    raise RuntimeError(f"All exchanges failed. Last error: {last_error}")


def load(symbol="BTC/USDT", timeframe="12h", since="2017-09-01", refresh=False):
    """Load candles from the local cache, downloading first if needed."""
    os.makedirs(DATA_DIR, exist_ok=True)
    safe = symbol.replace("/", "-")
    path = os.path.join(DATA_DIR, f"{safe}_{timeframe}.csv")
    if os.path.exists(path) and not refresh:
        return pd.read_csv(path, index_col="time", parse_dates=True)
    df = fetch_ohlcv(symbol, timeframe, since)
    df.to_csv(path)
    print(f"Saved {len(df)} candles to {path}")
    return df


def update(symbol="BTC/USDT", timeframe="12h", since="2017-09-01"):
    """Bring a cached dataset up to now by fetching only the new candles."""
    df = load(symbol, timeframe, since)
    fresh = fetch_ohlcv(symbol, timeframe, since=df.index[-1].isoformat())
    out = pd.concat([df, fresh])
    out = out[~out.index.duplicated(keep="last")].sort_index()
    safe = symbol.replace("/", "-")
    out.to_csv(os.path.join(DATA_DIR, f"{safe}_{timeframe}.csv"))
    return out


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
