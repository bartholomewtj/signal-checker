"""Liquidation readings for crypto symbols, estimated from open interest.

Real liquidation history is not free any more: Binance pulled its
`liquidationSnapshot` dumps, and Coinglass/Coinalyze both need a paid key.
So we estimate forced deleveraging instead.

The idea: a liquidation cascade shows up as open interest collapsing while
price moves hard. Positions are being closed, not opened.

    open interest falls + price falls  ->  longs are being flushed
    open interest falls + price rises  ->  shorts are being flushed

Binance publishes open interest every 5 minutes at data.binance.vision.
We walk those 5-minute steps, tag each drop as long-side or short-side by
the direction of the price move, size it in US dollars, and total it per
hour. Hourly is the stored resolution because it divides evenly into every
timeframe the pipeline runs (4h, 12h, 1d), so `attach` can add the columns
to any price frame without misaligning them.

This is a proxy, not a liquidation print. Open interest also falls when
traders close voluntarily, so quiet hours carry some noise. On the big
days the idea is about, forced closing dominates.

Coverage starts when Binance starts publishing for a symbol: 2020-09 for
BTC, 2021-12 for the rest.

Build or refresh a symbol's cache:
    python liqproxy.py                  # BTC/USDT
    python liqproxy.py ETH/USDT
"""

import io
import os
import sys
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

BASE = "https://data.binance.vision/data/futures/um/daily/metrics"
LISTING = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
COLUMNS = ["LongLiq", "ShortLiq"]

# Binance is missing scattered days. A failed download is retried this many
# times before we accept that the day is genuinely absent.
RETRIES = 3


def venue_symbol(symbol):
    """ccxt style (BTC/USDT) to Binance file style (BTCUSDT)."""
    return symbol.replace("/", "").replace("-", "").upper()


def cache_path(symbol):
    safe = symbol.replace("/", "-")
    return os.path.join(DATA_DIR, f"{safe}_liqproxy_1h.csv")


def _url(symbol, day):
    v = venue_symbol(symbol)
    return f"{BASE}/{v}/{v}-metrics-{day:%Y-%m-%d}.zip"


def _empty():
    return pd.DataFrame(columns=COLUMNS, index=pd.DatetimeIndex([], name="time"))


def first_available_day(symbol):
    """The earliest day Binance publishes open interest for this symbol.

    One bucket listing, rather than hundreds of 404s from guessing a start.
    """
    v = venue_symbol(symbol)
    url = f"{LISTING}?prefix=data/futures/um/daily/metrics/{v}/&max-keys=2"
    with urllib.request.urlopen(url, timeout=60) as resp:
        body = resp.read().decode()
    marker = f"{v}-metrics-"
    at = body.find(marker)
    if at < 0:
        raise RuntimeError(f"Binance publishes no open interest for {symbol}")
    start = at + len(marker)
    return pd.Timestamp(body[start:start + 10])


def fetch_day(symbol, day):
    """One day of 5-minute open interest. None if Binance has no file."""
    blob = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(_url(symbol, day), timeout=60) as resp:
                blob = resp.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == RETRIES - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == RETRIES - 1:
                raise
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        raw = z.read(z.namelist()[0])
    df = pd.read_csv(io.BytesIO(raw), usecols=[
        "create_time", "sum_open_interest", "sum_open_interest_value"])
    df["create_time"] = pd.to_datetime(df["create_time"])
    return df.sort_values("create_time")


def hour_totals(df):
    """Long/short liquidation proxy in USD, totalled per hour.

    Price comes from the open interest itself: notional value divided by
    contracts is the mark price, so we need no second download.
    """
    df = df[df["sum_open_interest"] > 0]
    if len(df) < 2:
        return _empty()

    oi = df["sum_open_interest"].to_numpy(float)
    val = df["sum_open_interest_value"].to_numpy(float)
    price = val / oi                       # notional / contracts = mark price

    d_oi = pd.Series(oi).diff().to_numpy()
    d_price = pd.Series(price).diff().to_numpy()

    closed = -d_oi                         # contracts closed (>0 = OI fell)
    usd = closed.clip(min=0) * price       # size the closing in dollars

    step = pd.DataFrame({
        "time": df["create_time"].to_numpy(),
        "LongLiq": usd * ((closed > 0) & (d_price < 0)),
        "ShortLiq": usd * ((closed > 0) & (d_price > 0)),
    }).fillna(0.0)
    out = step.set_index("time").resample("1h").sum()
    out.index.name = "time"
    return out


def build(symbol="BTC/USDT", end=None, workers=16, cache=None):
    """Download every missing day for `symbol` and append it to the cache.

    Append-only: days already cached are never re-fetched or rewritten,
    matching how data.py treats closed price bars.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    cache = cache or cache_path(symbol)
    have = (pd.read_csv(cache, index_col="time", parse_dates=True)
            if os.path.exists(cache) else _empty())

    if end is None:
        end = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    end = pd.Timestamp(end)

    covered = set(have.index.normalize().unique())
    wanted = pd.date_range(first_available_day(symbol),
                           end - pd.Timedelta(days=1), freq="D")
    todo = [d for d in wanted if d not in covered]
    if not todo:
        print(f"{os.path.basename(cache)}: up to date "
              f"({len(have)} hours, to {have.index[-1]:%Y-%m-%d})")
        return have

    print(f"{symbol}: fetching {len(todo)} days of open interest...")
    parts, missing = [], 0
    with ThreadPoolExecutor(workers) as pool:
        for raw in pool.map(lambda d: fetch_day(symbol, d), todo):
            if raw is None or len(raw) < 2:
                missing += 1
                continue
            parts.append(hour_totals(raw))

    out = pd.concat([have] + parts).sort_index() if parts else have
    out = out[~out.index.duplicated(keep="first")]
    out.index.name = "time"
    out.to_csv(cache)
    note = f", {missing} days Binance had no file for" if missing else ""
    span = (f" ({out.index[0]:%Y-%m-%d} to {out.index[-1]:%Y-%m-%d})"
            if len(out) else "")
    print(f"{os.path.basename(cache)}: {len(out)} hours{span}{note}")
    return out


def load(symbol="BTC/USDT", cache=None):
    """Read a symbol's cached hourly proxy, building it first if missing."""
    cache = cache or cache_path(symbol)
    if not os.path.exists(cache):
        return build(symbol, cache=cache)
    return pd.read_csv(cache, index_col="time", parse_dates=True)


def to_timeframe(liq, timeframe):
    """Total the hourly readings into `timeframe` bars.

    Bins are anchored to the epoch, which is how Binance cuts its candles,
    so a bar here lines up with the price bar of the same timestamp.

    Bars not fully covered by cached hours are dropped rather than returned
    as a partial total: a half-counted flush would read as a quiet bar and
    quietly weaken the signal.
    """
    # pandas 3 wants "1D", not the "1d" the rest of the project uses
    width = pd.Timedelta(timeframe.replace("d", "D"))
    hour = pd.Timedelta("1h")
    if width < hour:
        raise ValueError(f"timeframe {timeframe} is finer than the hourly proxy")
    grouped = liq.resample(width, origin="epoch")
    out = grouped.sum(min_count=1)
    complete = grouped.size() == int(width / hour)
    return out[complete].dropna()


def attach(price_df, symbol="BTC/USDT", timeframe="1d", cache=None):
    """Add LongLiq/ShortLiq columns to a price frame.

    Trims to the bars the proxy covers, so a strategy never sees a bar with
    no liquidation reading. Raises if nothing overlaps, rather than handing
    back an empty frame that would look like a strategy bug.
    """
    liq = to_timeframe(load(symbol, cache), timeframe)
    out = price_df.join(liq, how="inner").dropna(subset=COLUMNS)
    if out.empty:
        raise RuntimeError(
            f"no liquidation proxy overlaps the {symbol} {timeframe} price "
            f"data. Build it with:  python liqproxy.py {symbol}")
    return out


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "BTC/USDT")
