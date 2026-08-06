"""Robustness battery for the DEVMA daily result (see robustness.py for
the Diamond Hands equivalent). Prints everything; interpretation lives
in ROBUSTNESS.md.

Run:  python robustness_devma.py
"""

import os

os.environ.setdefault("TQDM_DISABLE", "1")

import warnings

import numpy as np

warnings.filterwarnings(
    "ignore", message=".*insufficient margin.*", category=UserWarning)

import data
from check import run as base_run, profit_factor
from strategies import Devma

DEFAULTS = dict(vol_ma=20, vol_run=5)


def run(df, params=DEFAULTS, commission=None, **attrs):
    """One backtest, optionally overriding Devma's class attributes
    (band timeframes, vol_mode, direction, delay)."""
    cls = type("DevmaVariant", (Devma,), attrs) if attrs else Devma
    if commission is None:
        return base_run(df, cls, params)
    from backtesting.lib import FractionalBacktest
    from check import CASH, SPREAD
    bt = FractionalBacktest(df, cls, fractional_unit=1e-6, cash=CASH,
                            commission=commission, spread=SPREAD,
                            finalize_trades=True)
    stats = bt.run(**params)
    rets = np.log(stats["_equity_curve"]["Equity"]).diff().fillna(0.0)
    return rets, stats


def line(tag, rets, stats):
    print(f"  {tag}: PF={profit_factor(rets):.3f}  "
          f"return={stats['Return [%]']:.0f}%  trades={stats['# Trades']}")


def main():
    df = data.load(timeframe="1d", since="2017-09-01")
    df = df[df.index >= "2018-01-01"]
    print(f"BTC 1d, {df.index[0].date()} to {df.index[-1].date()}, "
          f"{len(df)} bars\n")

    # 1 -------------------------------------------------------------------
    print("1) VOL-FILTER PARAMETER SWEEP (PF; original defaults 20/5)")
    mas = [5, 10, 15, 20, 30, 40, 60]
    runs = [2, 3, 5, 8, 12]
    pfs = []
    print("            " + "".join(f"run={r:<6}" for r in runs))
    for ma in mas:
        row = []
        for r in runs:
            rets, _ = run(df, params=dict(vol_ma=ma, vol_run=r))
            row.append(profit_factor(rets))
        pfs.extend(row)
        print(f"  ma={ma:<5} " + "".join(f"{p:<7.3f}" for p in row))
    pfs = np.array(pfs)
    print(f"  combos with PF>1: {(pfs > 1).sum()}/{len(pfs)}   "
          f"median PF: {np.median(pfs):.3f}\n")

    # 2 -------------------------------------------------------------------
    print("2) BAND-TIMEFRAME SWEEP (structural params, defaults 2D/3D)")
    for b1, b2 in [("1D", "2D"), ("1D", "3D"), ("2D", "3D"), ("2D", "4D"),
                   ("2D", "5D"), ("3D", "4D"), ("3D", "5D"), ("4D", "5D")]:
        rets, stats = run(df, band1=b1, band2=b2)
        line(f"step={b1} bands={b2}", rets, stats)
    print()

    # 3 -------------------------------------------------------------------
    print("3) VOLATILITY GATE ABLATION (the strategy's key ingredient)")
    for mode in ["normal", "off", "inverted"]:
        rets, stats = run(df, vol_mode=mode)
        line(f"{mode:8}", rets, stats)
    print()

    # 4 -------------------------------------------------------------------
    print("4) COST STRESS (commission per side, spread fixed 0.05%)")
    for comm in [0.0002, 0.0005, 0.0015, 0.0025, 0.004]:
        rets, stats = run(df, commission=comm)
        print(f"  commission {comm*100:.2f}%:  PF={profit_factor(rets):.3f}  "
              f"return={stats['Return [%]']:.0f}%")
    print()

    # 5 -------------------------------------------------------------------
    print("5) LONG vs SHORT LEG")
    for d in ["both", "long", "short"]:
        rets, stats = run(df, direction=d)
        line(f"{d:5}", rets, stats)
    print()

    # 6 -------------------------------------------------------------------
    print("6) ENTRY DELAYED ONE BAR (one full day late)")
    rets, stats = run(df, delay=1)
    line("delayed", rets, stats)
    print()

    # 7 -------------------------------------------------------------------
    print("7) SUB-PERIODS")
    for a, b in [("2018-01-01", "2021-01-01"), ("2021-01-01", "2024-01-01"),
                 ("2024-01-01", "2027-01-01")]:
        sub = df[(df.index >= a) & (df.index < b)]
        rets, stats = run(sub)
        print(f"  {a[:4]}-{str(int(b[:4])-1)}: PF={profit_factor(rets):.3f}  "
              f"return={stats['Return [%]']:.0f}%  trades={stats['# Trades']}  "
              f"buy&hold={stats['Buy & Hold Return [%]']:.0f}%")
    print()

    # 8 -------------------------------------------------------------------
    print("8) BOOTSTRAP: resample actual trades 10,000x")
    _, stats = run(df)
    tr = stats["_trades"]["ReturnPct"].to_numpy()
    if np.abs(tr).max() > 3:
        tr = tr / 100
    rng = np.random.default_rng(0)
    totals = np.array([
        np.prod(1 + rng.choice(tr, size=len(tr), replace=True)) - 1
        for _ in range(10_000)])
    print(f"  trades: {len(tr)}, mean per trade {tr.mean()*100:.2f}%")
    print(f"  resampled total: 5th pct {np.percentile(totals,5)*100:.0f}%  "
          f"median {np.percentile(totals,50)*100:.0f}%  "
          f"95th pct {np.percentile(totals,95)*100:.0f}%")
    print(f"  probability of overall loss: {(totals < 0).mean()*100:.1f}%\n")

    # 9 -------------------------------------------------------------------
    print("9) CROSS-ASSET: ETH daily, same rules, no re-tuning")
    eth = data.load(symbol="ETH/USDT", timeframe="1d", since="2018-01-01")
    rets, stats = run(eth)
    print(f"  ETH: PF={profit_factor(rets):.3f}  "
          f"return={stats['Return [%]']:.0f}%  trades={stats['# Trades']}  "
          f"buy&hold={stats['Buy & Hold Return [%]']:.0f}%  "
          f"maxDD={stats['Max. Drawdown [%]']:.0f}%")


if __name__ == "__main__":
    main()
