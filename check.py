"""signal-check: does this trading signal have a real edge, or is it luck?

Runs four stages and prints a plain-language verdict:

1. Full backtest        - the naive number everyone gets excited about.
2. In-sample honesty    - re-optimize the strategy on shuffled copies of
   (permutation test)     the data. If shuffled noise scores as well as
                          the real data, the backtest means nothing.
3. Walk-forward         - repeatedly: pick parameters on past data only,
                          then trade the next unseen chunk. The stitched
                          result is what you'd plausibly have earned.
4. Walk-forward honesty - same shuffle test applied to the walk-forward,
                          the strictest test in the pipeline.

Usage:
    python check.py            # full run (slow, ~30-60 min)
    python check.py --quick    # fewer shuffles, ~5-10 min
"""

import argparse
import os
import time

os.environ.setdefault("TQDM_DISABLE", "1")  # silence per-run progress bars

import numpy as np
import pandas as pd
from backtesting import Backtest

import data
from permute import permute_bars
from strategy import DiamondHands, PARAM_GRID, WARMUP

CASH = 100_000
COMMISSION = 0.0015  # 0.15% per side
SPREAD = 0.0005      # 0.05% slippage stand-in


def run(df, lookback, trend_len):
    """One backtest. Returns (per-bar log returns of equity, stats)."""
    bt = Backtest(df, DiamondHands, cash=CASH, commission=COMMISSION,
                  spread=SPREAD, finalize_trades=True)
    stats = bt.run(lookback=lookback, trend_len=trend_len)
    equity = stats["_equity_curve"]["Equity"]
    rets = np.log(equity).diff().fillna(0.0)
    return rets, stats


def profit_factor(rets):
    """Gross gains divided by gross losses on per-bar returns."""
    gains = rets[rets > 0].sum()
    losses = -rets[rets < 0].sum()
    if losses == 0:
        return np.inf if gains > 0 else 0.0
    return gains / losses


def optimize(df):
    """Try every parameter combo, return (best_params, best_pf)."""
    best_pf, best_params = -np.inf, None
    for lb in PARAM_GRID["lookback"]:
        for tl in PARAM_GRID["trend_len"]:
            rets, _ = run(df, lb, tl)
            pf = profit_factor(rets)
            if pf > best_pf:
                best_pf, best_params = pf, (lb, tl)
    return best_params, best_pf


def walkforward(df, train_bars, test_bars):
    """Optimize on a rolling window, trade the next chunk, stitch results.

    Returns (stitched out-of-sample returns, number of OOS trades, folds).
    Each fold's backtest includes the training window so indicators are
    warmed up, but only the test segment counts toward the result.
    """
    oos_rets = []
    oos_trades = 0
    folds = []
    start = 0
    while start + train_bars + test_bars <= len(df):
        train_end = start + train_bars           # test starts here
        test_end = train_end + test_bars
        (lb, tl), _ = optimize(df.iloc[start:train_end])
        rets, stats = run(df.iloc[start:test_end], lb, tl)
        fold_rets = rets.iloc[train_bars:]       # test segment only
        oos_rets.append(fold_rets)
        test_start_time = df.index[train_end]
        trades = stats["_trades"]
        n_trades = int((trades["EntryTime"] >= test_start_time).sum())
        oos_trades += n_trades
        folds.append({
            "test_start": str(test_start_time.date()),
            "params": (lb, tl),
            "pf": profit_factor(fold_rets),
            "trades": n_trades,
        })
        start += test_bars                       # roll forward
    return pd.concat(oos_rets), oos_trades, folds


def pvalue(real_score, perm_scores):
    """Fraction of shuffles that beat the real result (with +1 smoothing)."""
    perm_scores = np.asarray(perm_scores)
    return (1 + (perm_scores >= real_score).sum()) / (1 + len(perm_scores))


def mcpt_insample(df, real_pf, n_perms):
    """Shuffle the data, re-optimize each time, collect best scores."""
    scores = []
    t0 = time.time()
    for i in range(n_perms):
        perm = permute_bars(df, start_index=WARMUP, rng=np.random.default_rng(i))
        _, pf = optimize(perm)
        scores.append(pf)
        if (i + 1) % 10 == 0:
            print(f"  in-sample shuffle {i+1}/{n_perms} "
                  f"({time.time()-t0:.0f}s elapsed)")
    return pvalue(real_pf, scores), scores


def mcpt_walkforward(df, train_bars, test_bars, real_pf, n_perms):
    """Shuffle everything after the first training window, re-run the
    whole walk-forward each time, collect scores."""
    scores = []
    t0 = time.time()
    for i in range(n_perms):
        perm = permute_bars(df, start_index=train_bars,
                            rng=np.random.default_rng(10_000 + i))
        rets, _, _ = walkforward(perm, train_bars, test_bars)
        scores.append(profit_factor(rets))
        if (i + 1) % 5 == 0:
            print(f"  walk-forward shuffle {i+1}/{n_perms} "
                  f"({time.time()-t0:.0f}s elapsed)")
    return pvalue(real_pf, scores), scores


def main():
    ap = argparse.ArgumentParser(description="Honest signal check")
    ap.add_argument("--quick", action="store_true", help="fewer shuffles")
    ap.add_argument("--insample-perms", type=int, default=None)
    ap.add_argument("--wf-perms", type=int, default=None)
    ap.add_argument("--train-bars", type=int, default=1460,  # 2 years of 12h
                    help="bars in each training window")
    ap.add_argument("--test-bars", type=int, default=365,    # 6 months
                    help="bars traded after each training window")
    args = ap.parse_args()

    n_is = args.insample_perms or (30 if args.quick else 200)
    n_wf = args.wf_perms or (10 if args.quick else 100)

    df = data.load()
    print(f"Data: {len(df)} bars, {df.index[0].date()} to {df.index[-1].date()}\n")

    lines = []
    def say(msg=""):
        print(msg)
        lines.append(msg)

    # ---- Stage 1: full backtest with default parameters ----
    say("=" * 62)
    say("STAGE 1 - Full backtest (default parameters)")
    rets, stats = run(df, DiamondHands.lookback, DiamondHands.trend_len)
    say(f"  Return: {stats['Return [%]']:.1f}%   "
        f"Buy&hold: {stats['Buy & Hold Return [%]']:.1f}%")
    say(f"  Profit factor: {profit_factor(rets):.3f}   "
        f"Max drawdown: {stats['Max. Drawdown [%]']:.1f}%   "
        f"Trades: {stats['# Trades']}")
    say("  (This number alone proves nothing - stages 2-4 are the test.)")

    # ---- Stage 2: in-sample optimization + permutation test ----
    say()
    say("=" * 62)
    say(f"STAGE 2 - In-sample honesty test ({n_is} shuffles)")
    (lb, tl), real_is_pf = optimize(df)
    say(f"  Best in-sample params: lookback={lb}, trend_len={tl}, "
        f"profit factor {real_is_pf:.3f}")
    p_is, _ = mcpt_insample(df, real_is_pf, n_is)
    say(f"  p-value: {p_is:.3f}  "
        f"(chance that shuffled noise scores this well)")

    # ---- Stage 3: walk-forward ----
    say()
    say("=" * 62)
    say(f"STAGE 3 - Walk-forward ({args.train_bars} train bars, "
        f"{args.test_bars} test bars per fold)")
    wf_rets, wf_trades, folds = walkforward(df, args.train_bars, args.test_bars)
    wf_pf = profit_factor(wf_rets)
    wf_total = float(np.exp(wf_rets.sum()) - 1) * 100
    for f in folds:
        say(f"  fold from {f['test_start']}: params={f['params']}, "
            f"PF={f['pf']:.2f}, trades={f['trades']}")
    say(f"  Out-of-sample: total return {wf_total:.1f}%, "
        f"profit factor {wf_pf:.3f}, trades {wf_trades}")

    # ---- Stage 4: walk-forward permutation test ----
    say()
    say("=" * 62)
    say(f"STAGE 4 - Walk-forward honesty test ({n_wf} shuffles, slow)")
    p_wf, _ = mcpt_walkforward(df, args.train_bars, args.test_bars, wf_pf, n_wf)
    say(f"  p-value: {p_wf:.3f}")

    # ---- Verdict ----
    say()
    say("=" * 62)
    say("VERDICT")
    checks = {
        f"Made money out of sample (PF {wf_pf:.2f} > 1.0)": wf_pf > 1.0,
        f"Enough out-of-sample trades ({wf_trades} >= 30)": wf_trades >= 30,
        f"In-sample result beats noise (p {p_is:.3f} < 0.05)": p_is < 0.05,
        f"Walk-forward result beats noise (p {p_wf:.3f} < 0.05)": p_wf < 0.05,
    }
    for label, ok in checks.items():
        say(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    n_pass = sum(checks.values())
    say()
    if n_pass == 4:
        say("  LOOKS REAL. All checks passed. Worth paper-trading; still")
        say("  not a guarantee - markets change.")
    elif n_pass >= 2:
        say("  NOT PROVEN. Some evidence, but you would not want to risk")
        say("  money on this. Treat it as an idea, not an edge.")
    else:
        say("  NO EDGE FOUND. The backtest result is consistent with luck.")

    with open("report.txt", "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\nSaved to report.txt")


if __name__ == "__main__":
    main()
