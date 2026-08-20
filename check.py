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
    python check.py --strategy diamond_hands
    python check.py --strategy vwap_rejection --timeframe 1h --since 2021-01-01
    python check.py --strategy trend_step --quick
"""

import argparse
import csv
import datetime
import itertools
import os
import time

os.environ.setdefault("TQDM_DISABLE", "1")  # silence per-run progress bars

import warnings

import numpy as np
import pandas as pd
from backtesting.lib import FractionalBacktest

# Without fractional units the broker would skip trades whenever equity
# is below the price of one whole Bitcoin. Belt and braces: silence the
# cancellation warning too, so a long run doesn't produce megabytes of
# repeated text.
warnings.filterwarnings(
    "ignore", message=".*insufficient margin.*", category=UserWarning)

import data
import liqproxy
from permute import permute_bars
from strategies import REGISTRY

CASH = 100_000
COMMISSION = 0.0015  # 0.15% per side
SPREAD = 0.0005      # 0.05% slippage stand-in
MIN_TRADES = 10       # a parameter combo with fewer trades than this is unviable

FUNDING_PER_8H = 0.0001   # 0.01% per 8 hours on the notional of a short

LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trials.csv")
LEDGER_COLUMNS = ["timestamp", "mode", "strategy", "timeframe", "direction",
                  "train_bars", "test_bars", "p_insample", "p_walkforward",
                  "wf_pf", "wf_sharpe", "wf_trades", "verdict"]


def funding_rate_per_bar(df):
    """Pro-rate the 8-hourly funding cost to this data's bar size."""
    bar_hours = (df.index[1] - df.index[0]).total_seconds() / 3600
    return FUNDING_PER_8H * (bar_hours / 8.0)


def run(df, strat, params):
    """One backtest. Returns (per-bar log returns of equity, stats).

    Returns are charged a funding/borrow cost for every bar a short
    position is open (0.01% per 8h, pro-rated to the bar size), so real
    and permuted runs are treated identically - the charge lives here,
    not in any one stage.
    """
    bt = FractionalBacktest(df, strat, fractional_unit=1e-6,
                            cash=CASH, commission=COMMISSION,
                            spread=SPREAD, finalize_trades=True)
    stats = bt.run(**params)
    equity = stats["_equity_curve"]["Equity"]
    rets = np.log(equity).diff().fillna(0.0)

    trades = stats["_trades"]
    if len(trades):
        rate = funding_rate_per_bar(df)
        n = len(rets)
        short_mask = np.zeros(n, dtype=bool)
        shorts = trades[trades["Size"] < 0]
        for _, tr in shorts.iterrows():
            start = int(tr["EntryBar"]) + 1
            end = int(tr["ExitBar"])  # inclusive
            if start <= end:
                short_mask[start:end + 1] = True
        if short_mask.any():
            charge = np.where(short_mask, np.log(1 - rate), 0.0)
            rets = rets + charge
    return rets, stats


def profit_factor(rets):
    """Gross gains divided by gross losses on per-bar returns."""
    gains = rets[rets > 0].sum()
    losses = -rets[rets < 0].sum()
    if losses == 0:
        return np.inf if gains > 0 else 0.0
    return gains / losses


def trade_profit_factor(stats, df):
    """Gross trade profits divided by gross trade losses.

    Uses stats['_trades']['PnL'], adjusted for short funding cost so the
    selection metric feels the same charge the equity curve does.
    No trades -> 0.0. All winners -> inf. All losers -> 0.0.

    `df` is required: it sets the bar size for the short funding charge.
    Making it optional would let a caller silently skip the charge, which
    is the exact bias Fix 4 exists to remove.
    """
    trades = stats["_trades"]
    if len(trades) == 0:
        return 0.0
    pnl = trades["PnL"].to_numpy(dtype=float).copy()
    rate = funding_rate_per_bar(df)
    for i, (_, tr) in enumerate(trades.iterrows()):
        if tr["Size"] < 0:
            bars_held = int(tr["ExitBar"]) - int(tr["EntryBar"])
            notional = abs(tr["Size"]) * tr["EntryPrice"]
            charge = notional * rate * bars_held
            pnl[i] -= charge
    gains = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    if losses == 0:
        return np.inf if gains > 0 else 0.0
    return gains / losses


def sharpe(rets, df):
    """Annualised Sharpe of a per-bar log-return series.

    mean(rets) / std(rets) * sqrt(bars per year), where bars per year is
    derived from the spacing of df.index. Returns 0.0 if std is 0 or the
    series is empty.
    """
    if len(rets) == 0 or len(df.index) < 2:
        return 0.0
    std = rets.std()
    if std == 0 or np.isnan(std):
        return 0.0
    bar_hours = (df.index[1] - df.index[0]).total_seconds() / 3600
    bars_per_year = 365.25 * 24 / bar_hours
    return float(rets.mean() / std * np.sqrt(bars_per_year))


def buy_and_hold_pct(df, start=None, end=None):
    """Percentage return of simply holding the asset over a slice."""
    sl = df
    if start is not None:
        sl = sl[sl.index >= start]
    if end is not None:
        sl = sl[sl.index <= end]
    if len(sl) < 2:
        return 0.0
    return float(sl["Close"].iloc[-1] / sl["Close"].iloc[0] - 1) * 100


def grid_combos(strat):
    keys = list(strat.GRID)
    for values in itertools.product(*strat.GRID.values()):
        yield dict(zip(keys, values))


def optimize(df, strat):
    """Try every parameter combo, return (best_params, best_score).

    Score = trade-level profit factor. A combo producing fewer than
    MIN_TRADES trades in this window is unviable and scores 0.0.
    """
    best_score, best_params = -np.inf, None
    for params in grid_combos(strat):
        rets, stats = run(df, strat, params)
        n_trades = len(stats["_trades"])
        score = 0.0 if n_trades < MIN_TRADES else trade_profit_factor(stats, df)
        if score > best_score:
            best_score, best_params = score, params
    return best_params, best_score


def is_preview(args):
    """--quick and --preview are display-only. They must not write the ledger."""
    return bool(getattr(args, "quick", False) or getattr(args, "preview", False))


def append_trial(row, path=None):
    """Add one line to trials.csv, writing the header if the file is new."""
    path = path or LEDGER
    is_new = not os.path.exists(path)
    with open(path, "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=LEDGER_COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def _iter_rows(path=None):
    path = path or LEDGER
    if not os.path.exists(path):
        return
    with open(path, newline="") as fh:
        yield from csv.DictReader(fh)


def count_trials(path=None):
    """Distinct strategy-timeframe pairs ever recorded, counting mode=full
    rows only. Hold-out looks are not selection trials."""
    pairs = set()
    for row in _iter_rows(path):
        if row.get("mode") == "full":
            pairs.add((row.get("strategy"), row.get("timeframe")))
    return len(pairs)


def pair_is_recorded(strategy, timeframe, path=None):
    """True if this pair already has a mode=full row."""
    for row in _iter_rows(path):
        if (row.get("mode") == "full"
                and row.get("strategy") == strategy
                and row.get("timeframe") == timeframe):
            return True
    return False


def has_holdout(strategy, timeframe, path=None):
    """True if this pair already has a mode=holdout row."""
    for row in _iter_rows(path):
        if (row.get("mode") == "holdout"
                and row.get("strategy") == strategy
                and row.get("timeframe") == timeframe):
            return True
    return False


def trial_announcement(strategy, timeframe, path=None):
    """(n_now, n_after, bar, is_new_pair) for a forthcoming full run."""
    n_now = count_trials(path)
    is_new = not pair_is_recorded(strategy, timeframe, path)
    n_after = n_now + (1 if is_new else 0)
    bar = 0.05 / n_after if n_after else 0.05
    return n_now, n_after, bar, is_new


def walkforward(df, strat, train_bars, test_bars):
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
        params, _ = optimize(df.iloc[start:train_end], strat)
        rets, stats = run(df.iloc[start:test_end], strat, params)
        fold_rets = rets.iloc[train_bars:]       # test segment only
        oos_rets.append(fold_rets)
        test_start_time = df.index[train_end]
        trades = stats["_trades"]
        n_trades = int((trades["EntryTime"] >= test_start_time).sum())
        oos_trades += n_trades
        folds.append({
            "test_start": str(test_start_time.date()),
            "params": params,
            "pf": profit_factor(fold_rets),
            "trades": n_trades,
        })
        start += test_bars                       # roll forward
    return pd.concat(oos_rets), oos_trades, folds


def pvalue(real_score, perm_scores):
    """Fraction of shuffles that beat the real result (with +1 smoothing)."""
    perm_scores = np.asarray(perm_scores)
    return (1 + (perm_scores >= real_score).sum()) / (1 + len(perm_scores))


def mcpt_insample(df, strat, real_pf, n_perms):
    """Shuffle the data, re-optimize each time, collect best scores."""
    scores = []
    t0 = time.time()
    for i in range(n_perms):
        perm = permute_bars(df, start_index=strat.WARMUP,
                            rng=np.random.default_rng(i))
        _, pf = optimize(perm, strat)
        scores.append(pf)
        if (i + 1) % 10 == 0:
            print(f"  in-sample shuffle {i+1}/{n_perms} "
                  f"({time.time()-t0:.0f}s elapsed)", flush=True)
    return pvalue(real_pf, scores), scores


def mcpt_walkforward(df, strat, train_bars, test_bars, real_pf, n_perms):
    """Shuffle everything after the first training window, re-run the
    whole walk-forward each time, collect scores."""
    scores = []
    t0 = time.time()
    for i in range(n_perms):
        perm = permute_bars(df, start_index=train_bars,
                            rng=np.random.default_rng(10_000 + i))
        rets, _, _ = walkforward(perm, strat, train_bars, test_bars)
        scores.append(profit_factor(rets))
        if (i + 1) % 5 == 0:
            print(f"  walk-forward shuffle {i+1}/{n_perms} "
                  f"({time.time()-t0:.0f}s elapsed)", flush=True)
    return pvalue(real_pf, scores), scores


def main():
    ap = argparse.ArgumentParser(description="Honest signal check")
    ap.add_argument("--strategy", default="diamond_hands",
                    choices=sorted(REGISTRY))
    ap.add_argument("--timeframe", default="12h")
    ap.add_argument("--since", default="2017-09-01")
    ap.add_argument("--quick", action="store_true",
                    help="fewer shuffles; display only, not logged")
    ap.add_argument("--preview", action="store_true",
                    help="same as --quick: fewer shuffles, not logged")
    ap.add_argument("--insample-perms", type=int, default=None)
    ap.add_argument("--wf-perms", type=int, default=None)
    ap.add_argument("--train-bars", type=int, default=1460,  # 2 years of 12h
                    help="bars in each training window")
    ap.add_argument("--test-bars", type=int, default=365,    # 6 months
                    help="bars traded after each training window")
    ap.add_argument("--direction", default="both",
                    choices=["both", "long", "short"],
                    help="restrict which side may open (default: both)")
    ap.add_argument("--holdout", action="store_true",
                    help="run once on the reserved hold-out period and stop")
    ap.add_argument("--i-know-this-burns-the-holdout", action="store_true",
                    dest="burn_holdout",
                    help="allow a second --holdout for a pair that already has one")
    args = ap.parse_args()
    if args.preview:
        args.quick = True

    strat = REGISTRY[args.strategy]
    strat.direction = args.direction
    direction_label = {"both": "both (long+short)", "long": "long-only",
                       "short": "short-only"}[args.direction]
    n_is = args.insample_perms or (30 if args.quick else 200)
    n_wf = args.wf_perms or (10 if args.quick else 100)

    full_df = data.load(timeframe=args.timeframe, since=args.since)
    if getattr(strat, "NEEDS_LIQ", False):
        # Strategy needs the liquidation proxy columns. This also trims the
        # frame to the days the proxy covers (Binance open interest starts
        # 2020-09), so the hold-out split below is taken on the short frame.
        full_df = liqproxy.attach(full_df)
    work_df, holdout_df = data.split_holdout(full_df)

    if args.holdout:
        run_holdout(args, strat, full_df, work_df, holdout_df, direction_label)
        return

    df = work_df  # every stage below uses the working set only

    print(f"Strategy: {args.strategy}   Data: {len(df)} bars "
          f"({args.timeframe}), {df.index[0].date()} to {df.index[-1].date()}\n",
          flush=True)

    lines = [f"Strategy: {args.strategy}",
             f"Direction mode: {direction_label}"]
    def say(msg=""):
        print(msg, flush=True)
        lines.append(msg)

    say(f"Data used:     {len(df)} {args.timeframe} bars, "
        f"{df.index[0].date()} to {df.index[-1].date()}")
    if len(holdout_df):
        say(f"Reserved:      {len(holdout_df)} {args.timeframe} bars, "
            f"{holdout_df.index[0].date()} to {holdout_df.index[-1].date()}  "
            f"(hold-out, untouched)")
    else:
        say("Reserved:      none - dataset is shorter than 12 months")
    if is_preview(args):
        say("DISPLAY ONLY — not logged in trials.csv")
    else:
        n_now, n_after, bar, is_new = trial_announcement(
            args.strategy, args.timeframe)
        pair_note = ("new pair, N becomes "
                     if is_new else "same pair, N stays ")
        say(f"Logged trial:  N={n_now} now; {pair_note}{n_after}; "
            f"bar={bar:.4f} (0.05 / {n_after})")
    say()

    # ---- Stage 1: full backtest with default parameters ----
    say("=" * 62)
    say("STAGE 1 - Full backtest (default parameters)")
    defaults = {k: getattr(strat, k) for k in strat.GRID}
    rets, stats = run(df, strat, defaults)
    total_return = (np.exp(rets.sum()) - 1) * 100
    say(f"  Return: {total_return:.1f}%   "
        f"Buy&hold: {stats['Buy & Hold Return [%]']:.1f}%")
    say(f"  Profit factor: {profit_factor(rets):.3f}   "
        f"Max drawdown: {stats['Max. Drawdown [%]']:.1f}%   "
        f"Trades: {stats['# Trades']}")
    say("  (This number alone proves nothing - stages 2-4 are the test.)")

    # ---- Stage 2: in-sample optimization + permutation test ----
    say()
    say("=" * 62)
    say(f"STAGE 2 - In-sample honesty test ({n_is} shuffles)")
    best, real_is_pf = optimize(df, strat)
    say(f"  Best in-sample params: {best}, trade-level profit factor {real_is_pf:.3f}")
    p_is, _ = mcpt_insample(df, strat, real_is_pf, n_is)
    say(f"  p-value: {p_is:.3f}  "
        f"(chance that shuffled noise scores this well)")

    # ---- Stage 3: walk-forward ----
    say()
    say("=" * 62)
    say(f"STAGE 3 - Walk-forward ({args.train_bars} train bars, "
        f"{args.test_bars} test bars per fold)")
    wf_rets, wf_trades, folds = walkforward(df, strat,
                                            args.train_bars, args.test_bars)
    wf_pf = profit_factor(wf_rets)
    wf_total = float(np.exp(wf_rets.sum()) - 1) * 100
    wf_sharpe = sharpe(wf_rets, df)
    bh_start, bh_end = wf_rets.index[0], wf_rets.index[-1]
    wf_bh = buy_and_hold_pct(df, bh_start, bh_end)
    for f in folds:
        say(f"  fold from {f['test_start']}: params={f['params']}, "
            f"PF={f['pf']:.2f}, trades={f['trades']}")
    say(f"  Out-of-sample: total return {wf_total:.1f}%, "
        f"profit factor {wf_pf:.3f}, trades {wf_trades}")
    say(f"  Sharpe (annualised): {wf_sharpe:.2f}")
    say(f"  Buy and hold over the same period "
        f"({bh_start.date()} to {bh_end.date()}): {wf_bh:.1f}%")

    # ---- Stage 4: walk-forward permutation test ----
    say()
    say("=" * 62)
    say(f"STAGE 4 - Walk-forward honesty test ({n_wf} shuffles, slow)")
    p_wf, _ = mcpt_walkforward(df, strat, args.train_bars, args.test_bars,
                               wf_pf, n_wf)
    say(f"  p-value: {p_wf:.3f}")

    # ---- Verdict ----
    say()
    say("=" * 62)
    say("VERDICT")
    say(f"  Direction mode: {direction_label}")
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
        verdict = "LOOKS REAL"
        say("  LOOKS REAL. All checks passed. Worth paper-trading; still")
        say("  not a guarantee - markets change.")
    elif n_pass >= 2:
        verdict = "NOT PROVEN"
        say("  NOT PROVEN. Some evidence, but you would not want to risk")
        say("  money on this. Treat it as an idea, not an edge.")
    else:
        verdict = "NO EDGE"
        say("  NO EDGE FOUND. The backtest result is consistent with luck.")

    # ---- Multiple-testing ledger ----
    if is_preview(args):
        say()
        say("  DISPLAY ONLY — not logged in trials.csv")
        return

    append_trial({
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "mode": "full",
        "strategy": args.strategy,
        "timeframe": args.timeframe,
        "direction": args.direction,
        "train_bars": args.train_bars,
        "test_bars": args.test_bars,
        "p_insample": f"{p_is:.4f}",
        "p_walkforward": f"{p_wf:.4f}",
        "wf_pf": f"{wf_pf:.4f}",
        "wf_sharpe": f"{wf_sharpe:.4f}",
        "wf_trades": wf_trades,
        "verdict": verdict,
    })
    n_trials = count_trials()
    corrected = 0.05 / n_trials if n_trials else 0.05
    say()
    say("  Multiple-testing correction")
    say(f"    {n_trials} distinct strategy-timeframe trials recorded in trials.csv")
    say(f"    Raw bar:       p < 0.0500")
    say(f"    Corrected bar: p < {corrected:.4f}   (0.05 / {n_trials}, Bonferroni)")
    say(f"    in-sample     p={p_is:.4f}   clears raw: {'YES' if p_is < 0.05 else 'NO'}   "
        f"clears corrected: {'YES' if p_is < corrected else 'NO'}")
    say(f"    walk-forward  p={p_wf:.4f}   clears raw: {'YES' if p_wf < 0.05 else 'NO'}   "
        f"clears corrected: {'YES' if p_wf < corrected else 'NO'}")
    if verdict == "LOOKS REAL" and (p_is >= corrected or p_wf >= corrected):
        say()
        say(f"  Passes at 0.05, but with {n_trials} trials the corrected bar is "
            f"{corrected:.4f} - treat LOOKS REAL as provisional.")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       f"report_{args.strategy}_{args.timeframe}.txt")
    with open(out, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"\nSaved to {out}")


def run_holdout(args, strat, full_df, work_df, holdout_df, direction_label):
    """Run once on the reserved hold-out period using the walk-forward's
    last chosen parameters, and report that result alone."""
    if has_holdout(args.strategy, args.timeframe) and not getattr(
            args, "burn_holdout", False):
        print(
            f"Refused: {args.strategy}/{args.timeframe} already has a "
            f"mode=holdout row in trials.csv. A second look burns the "
            f"reserved year. Pass --i-know-this-burns-the-holdout to override.",
            flush=True,
        )
        raise SystemExit(2)

    lines = [f"Strategy: {args.strategy}", f"Direction mode: {direction_label}"]
    def say(msg=""):
        print(msg, flush=True)
        lines.append(msg)

    say("=" * 62)
    say("HOLD-OUT RESULT - look at this once per strategy, then stop.")
    say("The moment you change the strategy because of what you see here, this")
    say("number stops being a hold-out and becomes just another in-sample result.")
    say("=" * 62)

    if len(holdout_df) == 0:
        say("Reserved: none - dataset is shorter than 12 months. Nothing to run.")
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           f"holdout_{args.strategy}_{args.timeframe}.txt")
        with open(out, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"\nSaved to {out}")
        return

    say(f"Data used (walk-forward, to pick params): {len(work_df)} "
        f"{args.timeframe} bars, {work_df.index[0].date()} to {work_df.index[-1].date()}")
    say(f"Reserved (hold-out, run once):            {len(holdout_df)} "
        f"{args.timeframe} bars, {holdout_df.index[0].date()} to {holdout_df.index[-1].date()}")
    say()

    print("  Running walk-forward on the working set to pick final parameters "
          "(no shuffles - this is quick)...", flush=True)
    _, _, folds = walkforward(work_df, strat, args.train_bars, args.test_bars)
    if not folds:
        say("  Walk-forward produced no folds (not enough data) - cannot pick "
            "hold-out parameters.")
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           f"holdout_{args.strategy}_{args.timeframe}.txt")
        with open(out, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"\nSaved to {out}")
        return

    params = folds[-1]["params"]
    say(f"  Parameters (from the final walk-forward fold): {params}")

    # Run on the full frame so indicators are warmed up; every indicator
    # in strategies.py is causal, so this cannot leak the hold-out into
    # itself - the bars before the hold-out start only warm up the state.
    rets, stats = run(full_df, strat, params)
    hold_start = holdout_df.index[0]
    hold_rets = rets[rets.index >= hold_start]
    trades = stats["_trades"]
    hold_trades = trades[trades["EntryTime"] >= hold_start]

    hold_total = float(np.exp(hold_rets.sum()) - 1) * 100
    hold_pf_trade = trade_profit_factor(
        {"_trades": hold_trades}, full_df) if len(hold_trades) else 0.0
    hold_sharpe = sharpe(hold_rets, full_df)
    hold_bh = buy_and_hold_pct(full_df, hold_start, full_df.index[-1])

    say()
    say(f"  Total return:              {hold_total:.1f}%")
    say(f"  Trade-level profit factor: {hold_pf_trade:.3f}")
    say(f"  Sharpe (annualised):       {hold_sharpe:.2f}")
    say(f"  Trades:                    {len(hold_trades)}")
    say(f"  Buy and hold over the same period: {hold_bh:.1f}%")

    append_trial({
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "mode": "holdout",
        "strategy": args.strategy,
        "timeframe": args.timeframe,
        "direction": args.direction,
        "train_bars": args.train_bars,
        "test_bars": args.test_bars,
        "p_insample": "",
        "p_walkforward": "",
        "wf_pf": "",
        "wf_sharpe": "",
        "wf_trades": len(hold_trades),
        "verdict": "HOLDOUT",
    })

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       f"holdout_{args.strategy}_{args.timeframe}.txt")
    with open(out, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
