"""Robustness battery for the Diamond Hands 4h result.

A strategy that passed the four-stage check can still be fragile. This
script attacks the 4h result from seven angles and prints everything;
interpretation lives in ROBUSTNESS.md.

Run:  python robustness.py
"""

import os

os.environ.setdefault("TQDM_DISABLE", "1")

import warnings

import numpy as np

warnings.filterwarnings(
    "ignore", message=".*insufficient margin.*", category=UserWarning)

import data
from backtesting.lib import FractionalBacktest
from check import profit_factor, CASH, COMMISSION, SPREAD
from strategies import DiamondHands

DEFAULTS = dict(lookback=20, trend_len=200)


def run(df, strat=DiamondHands, params=DEFAULTS, commission=COMMISSION,
        spread=SPREAD):
    bt = FractionalBacktest(df, strat, fractional_unit=1e-6, cash=CASH,
                            commission=commission, spread=spread,
                            finalize_trades=True)
    stats = bt.run(**params)
    rets = np.log(stats["_equity_curve"]["Equity"]).diff().fillna(0.0)
    return rets, stats


# Variants for the long/short and delayed-entry tests -----------------------

class LongOnly(DiamondHands):
    def next(self):
        if np.isnan(self.trend[-1]) or np.isnan(self.prior_low_min[-1]):
            return
        close, low = self.data.Close[-1], self.data.Low[-1]
        long_sig = (low < self.prior_low_min[-1]
                    and close > self.prior_close_min[-1]
                    and close > self.trend[-1])
        if long_sig and not self.position.is_long:
            self.buy()
        elif self.position.is_long and close < self.trend[-1]:
            self.position.close()


class ShortOnly(DiamondHands):
    def next(self):
        if np.isnan(self.trend[-1]) or np.isnan(self.prior_low_min[-1]):
            return
        close, high = self.data.Close[-1], self.data.High[-1]
        short_sig = (high > self.prior_high_max[-1]
                     and close < self.prior_close_max[-1]
                     and close < self.trend[-1])
        if short_sig and not self.position.is_short:
            self.sell()
        elif self.position.is_short and close > self.trend[-1]:
            self.position.close()


class DelayedEntry(DiamondHands):
    """Acts on the signal one bar late (fill two bars after the sweep).
    A real, durable pattern should degrade gracefully, not vanish."""
    def next(self):
        if len(self.data) < 3 or np.isnan(self.trend[-1]) \
                or np.isnan(self.prior_low_min[-2]):
            return
        close = self.data.Close[-1]
        long_sig = (self.data.Low[-2] < self.prior_low_min[-2]
                    and self.data.Close[-2] > self.prior_close_min[-2]
                    and self.data.Close[-2] > self.trend[-2])
        short_sig = (self.data.High[-2] > self.prior_high_max[-2]
                     and self.data.Close[-2] < self.prior_close_max[-2]
                     and self.data.Close[-2] < self.trend[-2])
        if long_sig and not self.position.is_long:
            self.position.close(); self.buy()
        elif short_sig and not self.position.is_short:
            self.position.close(); self.sell()
        elif self.position.is_long and close < self.trend[-1]:
            self.position.close()
        elif self.position.is_short and close > self.trend[-1]:
            self.position.close()


def main():
    df = data.load(timeframe="4h", since="2017-09-01")
    df = df[df.index >= "2018-01-01"]
    print(f"BTC 4h, {df.index[0].date()} to {df.index[-1].date()}, "
          f"{len(df)} bars\n")

    # 1 -------------------------------------------------------------------
    print("1) PARAMETER SWEEP (PF per combo; original defaults were 20/200)")
    lookbacks = [8, 12, 16, 20, 26, 32, 40, 48, 64]
    trends = [50, 100, 150, 200, 300, 400]
    pfs = []
    print("            " + "".join(f"t={t:<7}" for t in trends))
    for lb in lookbacks:
        row = []
        for t in trends:
            rets, _ = run(df, params=dict(lookback=lb, trend_len=t))
            row.append(profit_factor(rets))
        pfs.extend(row)
        print(f"  lb={lb:<4} " + "".join(f"{p:<8.3f}" for p in row))
    pfs = np.array(pfs)
    print(f"  combos with PF>1: {(pfs > 1).sum()}/{len(pfs)}   "
          f"median PF: {np.median(pfs):.3f}   "
          f"min/max: {pfs.min():.3f}/{pfs.max():.3f}\n")

    # 2 -------------------------------------------------------------------
    print("2) COST STRESS (defaults 20/200; commission per side, "
          "spread fixed at 0.05%)")
    for comm in [0.0002, 0.0005, 0.001, 0.0015, 0.0025, 0.004]:
        rets, stats = run(df, commission=comm)
        print(f"  commission {comm*100:.2f}%:  PF={profit_factor(rets):.3f}  "
              f"return={stats['Return [%]']:.0f}%")
    print()

    # 3 -------------------------------------------------------------------
    print("3) LONG vs SHORT LEG (defaults)")
    for name, strat in [("both ", DiamondHands), ("long ", LongOnly),
                        ("short", ShortOnly)]:
        rets, stats = run(df, strat=strat)
        print(f"  {name}: PF={profit_factor(rets):.3f}  "
              f"return={stats['Return [%]']:.0f}%  "
              f"trades={stats['# Trades']}")
    print()

    # 4 -------------------------------------------------------------------
    print("4) ENTRY DELAYED ONE BAR (defaults)")
    rets, stats = run(df, strat=DelayedEntry)
    print(f"  delayed: PF={profit_factor(rets):.3f}  "
          f"return={stats['Return [%]']:.0f}%  trades={stats['# Trades']}\n")

    # 5 -------------------------------------------------------------------
    print("5) SUB-PERIODS (defaults)")
    for a, b in [("2018-01-01", "2021-01-01"), ("2021-01-01", "2024-01-01"),
                 ("2024-01-01", "2027-01-01")]:
        sub = df[(df.index >= a) & (df.index < b)]
        rets, stats = run(sub)
        print(f"  {a[:4]}-{str(int(b[:4])-1)}: PF={profit_factor(rets):.3f}  "
              f"return={stats['Return [%]']:.0f}%  "
              f"trades={stats['# Trades']}  "
              f"buy&hold={stats['Buy & Hold Return [%]']:.0f}%")
    print()

    # 6 -------------------------------------------------------------------
    print("6) BOOTSTRAP: resample the actual trades 10,000x")
    _, stats = run(df)
    tr = stats["_trades"]["ReturnPct"].to_numpy()
    if np.abs(tr).max() > 3:      # tolerate percent-vs-fraction ambiguity
        tr = tr / 100
    rng = np.random.default_rng(0)
    totals = np.array([
        np.prod(1 + rng.choice(tr, size=len(tr), replace=True)) - 1
        for _ in range(10_000)])
    print(f"  actual trades: {len(tr)}, mean per trade "
          f"{tr.mean()*100:.2f}%")
    print(f"  resampled total return: 5th pct {np.percentile(totals,5)*100:.0f}%  "
          f"median {np.percentile(totals,50)*100:.0f}%  "
          f"95th pct {np.percentile(totals,95)*100:.0f}%")
    print(f"  probability of overall loss: {(totals < 0).mean()*100:.1f}%\n")

    # 7 -------------------------------------------------------------------
    print("7) CROSS-ASSET: same rules, ETH (never used in development)")
    eth = data.load(symbol="ETH/USDT", timeframe="4h", since="2018-01-01")
    rets, stats = run(eth)
    print(f"  ETH defaults: PF={profit_factor(rets):.3f}  "
          f"return={stats['Return [%]']:.0f}%  trades={stats['# Trades']}  "
          f"buy&hold={stats['Buy & Hold Return [%]']:.0f}%  "
          f"maxDD={stats['Max. Drawdown [%]']:.0f}%")


if __name__ == "__main__":
    main()
