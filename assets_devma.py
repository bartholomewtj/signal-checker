"""DEVMA cross-asset transfer test.

Runs DEVMA with its default parameters (no re-tuning of any kind) on a
basket of major cryptocurrencies, daily and 12h. A real edge should be
roughly portable; an overfit one should only work on the asset it was
built against (BTC).

Run:  python assets_devma.py
"""

import os

os.environ.setdefault("TQDM_DISABLE", "1")

import warnings

import numpy as np

warnings.filterwarnings(
    "ignore", message=".*insufficient margin.*", category=UserWarning)

import data
from check import run, profit_factor
from strategies import Devma

ASSETS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT",
          "LTC/USDT", "DOGE/USDT", "SOL/USDT"]
DEFAULTS = dict(vol_ma=20, vol_run=5)


def main():
    for tf in ["1d", "12h"]:
        print(f"=== {tf} ===")
        wins = beats = 0
        rows = 0
        for sym in ASSETS:
            try:
                df = data.load(symbol=sym, timeframe=tf, since="2018-01-01")
            except Exception as e:
                print(f"  {sym}: data unavailable ({e})")
                continue
            rets, stats = run(df, Devma, DEFAULTS)
            pf = profit_factor(rets)
            bh = stats["Buy & Hold Return [%]"]
            ret = stats["Return [%]"]
            rows += 1
            wins += pf > 1
            beats += ret > bh
            print(f"  {sym:10} from {df.index[0].date()}  PF={pf:.3f}  "
                  f"return={ret:9.0f}%  b&h={bh:9.0f}%  "
                  f"trades={stats['# Trades']:3d}  "
                  f"maxDD={stats['Max. Drawdown [%]']:.0f}%")
        print(f"  -> profitable: {wins}/{rows}   beat buy-and-hold: "
              f"{beats}/{rows}\n")


if __name__ == "__main__":
    main()
