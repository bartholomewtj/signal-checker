"""Daily liquidation proxy for BTC, built from Binance open interest.

Real liquidation history is no longer free: Binance pulled its
`liquidationSnapshot` dumps, and Coinglass/Coinalyze both need a paid key.
So we estimate forced deleveraging instead.

The idea: a liquidation cascade shows up as open interest collapsing while
price moves hard. Positions are being closed, not opened.

    open interest falls + price falls  ->  longs are being flushed
    open interest falls + price rises  ->  shorts are being flushed

Binance publishes open interest every 5 minutes at data.binance.vision
(2020-09 onward). We walk those 5-minute steps, tag each drop as long-side
or short-side by the direction of the price move, size it in US dollars,
and sum per UTC day.

This is a proxy, not a liquidation print. Open interest also falls when
traders close voluntarily, so quiet days carry some noise. On the big days
the idea is about, forced closing dominates.

Run directly to build/refresh the cache:
    python liqproxy.py
"""

import io
import os
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CACHE = os.path.join(DATA_DIR, "BTC-USDT_liqproxy_1d.csv")

BASE = "https://data.binance.vision/data/futures/um/daily/metrics"
SYMBOL = "BTCUSDT"
FIRST_DAY = "2020-09-01"          # earliest metrics file Binance publishes
COLUMNS = ["LongLiq", "ShortLiq"]


def _url(day):
    return f"{BASE}/{SYMBOL}/{SYMBOL}-metrics-{day:%Y-%m-%d}.zip"


def fetch_day(day):
    """One day of 5-minute open interest. Returns None if Binance has no file."""
    try:
        with urllib.request.urlopen(_url(day), timeout=60) as resp:
            blob = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        raw = z.read(z.namelist()[0])
    df = pd.read_csv(io.BytesIO(raw), usecols=[
        "create_time", "sum_open_interest", "sum_open_interest_value"])
    df["create_time"] = pd.to_datetime(df["create_time"])
    return df.sort_values("create_time")


def day_totals(df):
    """Long/short liquidation proxy in USD for one day's 5-minute rows.

    Price comes from the open interest itself: notional value divided by
    contracts is the mark price, so we need no second download.
    """
    df = df[df["sum_open_interest"] > 0]
    if len(df) < 2:
        return 0.0, 0.0
    oi = df["sum_open_interest"].to_numpy(float)
    val = df["sum_open_interest_value"].to_numpy(float)
    price = val / oi          # notional / contracts = mark price

    d_oi = pd.Series(oi).diff().to_numpy()
    d_price = pd.Series(price).diff().to_numpy()

    closed = -d_oi                      # contracts closed this step (>0 = OI fell)
    usd = closed.clip(min=0) * price    # size the closing in dollars

    longs = usd[(closed > 0) & (d_price < 0)].sum()
    shorts = usd[(closed > 0) & (d_price > 0)].sum()
    return float(longs), float(shorts)


def build(start=FIRST_DAY, end=None, workers=16, cache=CACHE):
    """Download every missing day and append it to the cache.

    Append-only: days already in the cache are never re-fetched or
    rewritten, matching how data.py treats closed price bars.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    have = pd.DataFrame(columns=COLUMNS,
                        index=pd.DatetimeIndex([], name="time"))
    if os.path.exists(cache):
        have = pd.read_csv(cache, index_col="time", parse_dates=True)

    if end is None:
        end = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    end = pd.Timestamp(end)
    wanted = pd.date_range(start, end - pd.Timedelta(days=1), freq="D")
    todo = [d for d in wanted if d not in have.index]
    if not todo:
        print(f"{cache}: up to date ({len(have)} days)")
        return have

    print(f"fetching {len(todo)} days of open interest...")
    rows, missing = {}, 0
    with ThreadPoolExecutor(workers) as pool:
        for day, df in zip(todo, pool.map(fetch_day, todo)):
            if df is None or len(df) < 2:
                missing += 1
                continue
            rows[day] = day_totals(df)

    fresh = pd.DataFrame.from_dict(rows, orient="index", columns=COLUMNS)
    fresh.index.name = "time"
    out = pd.concat([have, fresh]).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    out.index.name = "time"
    out.to_csv(cache)
    print(f"{cache}: {len(out)} days ({missing} days Binance had no file for)")
    return out


def load(cache=CACHE):
    """Read the cached daily proxy. Build it first if it is missing."""
    if not os.path.exists(cache):
        return build(cache=cache)
    return pd.read_csv(cache, index_col="time", parse_dates=True)


def attach(price_df, cache=CACHE):
    """Add LongLiq/ShortLiq columns to a daily price frame.

    Trims the price frame to the days the proxy covers, so a strategy
    never sees a bar with no liquidation reading.
    """
    liq = load(cache)
    out = price_df.join(liq, how="inner")
    return out.dropna(subset=COLUMNS)


if __name__ == "__main__":
    df = build()
    print(df.tail())
