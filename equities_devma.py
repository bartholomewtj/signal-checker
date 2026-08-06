"""DEVMA on non-crypto markets: equity indices (large and small cap),
single large caps, and gold. Daily bars from stooq.com, 2018 onward,
default parameters, no re-tuning.

Each market runs at two cost levels:
  crypto costs: 0.15% commission + 0.05% spread per side (as elsewhere)
  equity costs: 0.03% commission + 0.01% spread per side (realistic ETF)

Run:  python equities_devma.py
"""

import os

os.environ.setdefault("TQDM_DISABLE", "1")

import warnings

import numpy as np

warnings.filterwarnings(
    "ignore", message=".*insufficient margin.*", category=UserWarning)

import data
from backtesting.lib import FractionalBacktest
from check import CASH, profit_factor
from strategies import Devma

MARKETS = [
    ("SPY", "SPY  (S&P 500, large cap)"),
    ("QQQ", "QQQ  (Nasdaq 100, large cap)"),
    ("IWM", "IWM  (Russell 2000, small cap)"),
    ("IJR", "IJR  (S&P 600, small cap)"),
    ("AAPL", "AAPL"),
    ("MSFT", "MSFT"),
    ("JPM", "JPM"),
    ("XOM", "XOM"),
    ("GLD", "GLD  (gold)"),
]
DEFAULTS = dict(vol_ma=20, vol_run=5)


def run(df, commission, spread):
    bt = FractionalBacktest(df, Devma, fractional_unit=1e-6, cash=CASH,
                            commission=commission, spread=spread,
                            finalize_trades=True)
    stats = bt.run(**DEFAULTS)
    rets = np.log(stats["_equity_curve"]["Equity"]).diff().fillna(0.0)
    return rets, stats


def main():
    wins_hi = wins_lo = rows = 0
    for sym, label in MARKETS:
        try:
            df = data.load_yahoo(sym)
        except Exception as e:
            print(f"{label}: data unavailable ({e})")
            continue
        r_hi, s_hi = run(df, 0.0015, 0.0005)
        r_lo, s_lo = run(df, 0.0003, 0.0001)
        pf_hi, pf_lo = profit_factor(r_hi), profit_factor(r_lo)
        rows += 1
        wins_hi += pf_hi > 1
        wins_lo += pf_lo > 1
        print(f"{label:32} from {df.index[0].date()}  "
              f"cryptoCosts: PF={pf_hi:.3f} ret={s_hi['Return [%]']:6.0f}%   "
              f"equityCosts: PF={pf_lo:.3f} ret={s_lo['Return [%]']:6.0f}%   "
              f"b&h={s_hi['Buy & Hold Return [%]']:5.0f}%  "
              f"trades={s_hi['# Trades']}")
    print(f"\nprofitable at crypto costs: {wins_hi}/{rows}   "
          f"at equity costs: {wins_lo}/{rows}")


if __name__ == "__main__":
    main()
