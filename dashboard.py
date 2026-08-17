"""signal-check dashboard: a local, live, interactive view of the
strategies.

Run:  python dashboard.py
Then open http://localhost:8787 in a browser.

Pick a strategy, asset and timeframe; the server runs the backtest on
the spot (a fraction of a second on cached data) and the page shows the
price chart with every trade marked, the equity curve, headline stats,
the strategy's position right now, and the honesty-test verdicts from
the reports. "Update data" pulls only the newest candles from the
exchange, so refreshing is quick.

No new dependencies: Python's built-in web server plus the vendored
TradingView Lightweight Charts file in vendor/.
"""

import json
import math
import os
import re
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("TQDM_DISABLE", "1")

import warnings

import numpy as np

warnings.filterwarnings(
    "ignore", message=".*insufficient margin.*", category=UserWarning)

import check
import data
from strategies import REGISTRY

PORT = 8787
HERE = os.path.dirname(os.path.abspath(__file__))
SYMBOLS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT",
           "LTC/USDT", "DOGE/USDT", "SOL/USDT"]
TIMEFRAMES = ["4h", "12h", "1d"]
MAX_CANDLES = 12_000

_lock = threading.Lock()  # ccxt fetch + csv writes shouldn't overlap


def _num(x):
    """JSON-safe number (NaN/inf become None)."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def verdicts():
    """Verdict per strategy/timeframe, parsed from the report files."""
    out = []
    for fn in sorted(os.listdir(HERE)):
        m = re.match(r"report_(\w+?)(?:_(\w+))?\.txt$", fn)
        if not m:
            continue
        text = open(os.path.join(HERE, fn)).read()
        verdict = ("LOOKS REAL" if "LOOKS REAL" in text
                   else "NOT PROVEN" if "NOT PROVEN" in text
                   else "NO EDGE" if "NO EDGE" in text else "?")
        out.append({"strategy": m.group(1), "timeframe": m.group(2) or "12h",
                    "verdict": verdict})
    return out


def run_backtest(strategy, symbol, timeframe, fresh=False):
    strat = REGISTRY[strategy]
    since = "2021-01-01" if timeframe == "1h" else "2017-09-01"
    with _lock:
        if fresh:
            df = data.update(symbol, timeframe, since)
        else:
            df = data.load(symbol=symbol, timeframe=timeframe, since=since)
    params = {k: getattr(strat, k) for k in strat.GRID}
    rets, stats = check.run(df, strat, params)

    df = df.iloc[-MAX_CANDLES:]
    t0 = df.index[0]
    candles = [
        {"time": int(ts.timestamp()), "open": _num(o), "high": _num(h),
         "low": _num(l), "close": _num(c)}
        for ts, o, h, l, c in zip(df.index, df.Open, df.High, df.Low, df.Close)
    ]

    equity = stats["_equity_curve"]["Equity"]
    equity = equity[equity.index >= t0]
    step = max(1, len(equity) // 4000)
    eq_points = [{"time": int(ts.timestamp()), "value": _num(v)}
                 for ts, v in equity.iloc[::step].items()]

    trades = stats["_trades"]
    # FractionalBacktest reports prices in scaled units; recover the
    # scale by comparing magnitudes with the raw candle data.
    scale = 1.0
    if len(trades):
        ratio = float(df.Close.median()) / float(trades["EntryPrice"].median())
        scale = 10 ** round(math.log10(abs(ratio))) if ratio > 0 else 1.0
    last_bar = df.index[-1]
    trade_rows, markers = [], []
    for _, tr in trades.iterrows():
        is_long = tr["Size"] > 0
        open_now = tr["ExitTime"] >= last_bar
        if tr["EntryTime"] >= t0:
            markers.append({
                "time": int(tr["EntryTime"].timestamp()),
                "position": "belowBar" if is_long else "aboveBar",
                "shape": "arrowUp" if is_long else "arrowDown",
                "color": "#26a69a" if is_long else "#ef5350",
                "text": "L" if is_long else "S",
            })
            if not open_now:
                markers.append({
                    "time": int(tr["ExitTime"].timestamp()),
                    "position": "aboveBar" if is_long else "belowBar",
                    "shape": "circle", "color": "#9aa4b2", "text": "x",
                })
        trade_rows.append({
            "side": "long" if is_long else "short",
            "entry_time": str(tr["EntryTime"]),
            "exit_time": "open" if open_now else str(tr["ExitTime"]),
            "entry": _num(tr["EntryPrice"] * scale),
            "exit": None if open_now else _num(tr["ExitPrice"] * scale),
            "ret_pct": _num(tr["ReturnPct"] * 100),
        })

    position = "FLAT"
    if len(trades):
        last = trades.iloc[-1]
        if last["ExitTime"] >= last_bar:
            position = "LONG" if last["Size"] > 0 else "SHORT"

    return {
        "candles": candles, "equity": eq_points, "markers": markers,
        "trades": trade_rows[-12:][::-1],
        "position": position,
        "last_candle": str(last_bar),
        "stats": {
            "Return %": _num(stats["Return [%]"]),
            "Buy & hold %": _num(stats["Buy & Hold Return [%]"]),
            "Profit factor": _num(check.profit_factor(rets)),
            "Max drawdown %": _num(stats["Max. Drawdown [%]"]),
            "Trades": int(stats["# Trades"]),
            "Win rate %": _num(stats["Win Rate [%]"]),
        },
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # keep the console quiet
        pass

    def _send(self, body, ctype="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body if isinstance(body, bytes)
                         else json.dumps(body).encode())

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(url.query))
        try:
            if url.path == "/":
                with open(os.path.join(HERE, "dashboard.html"), "rb") as fh:
                    self._send(fh.read(), "text/html; charset=utf-8")
            elif url.path == "/lightweight-charts.js":
                js = os.path.join(
                    HERE, "vendor", "lightweight-charts.standalone.production.js"
                )
                with open(js, "rb") as fh:
                    self._send(fh.read(), "application/javascript")
            elif url.path == "/api/meta":
                self._send({"strategies": sorted(REGISTRY),
                            "symbols": SYMBOLS, "timeframes": TIMEFRAMES,
                            "verdicts": verdicts()})
            elif url.path == "/api/run":
                self._send(run_backtest(
                    q.get("strategy", "devma"), q.get("symbol", "BTC/USDT"),
                    q.get("timeframe", "1d"), q.get("fresh") == "1"))
            else:
                self.send_error(404)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"signal-check dashboard: http://localhost:{PORT}")
    try:
        webbrowser.open(f"http://localhost:{PORT}")
    except Exception:
        pass
    server.serve_forever()
