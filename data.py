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


if __name__ == "__main__":
    df = load()
    print(df.tail())
