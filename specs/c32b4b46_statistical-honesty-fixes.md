# Plan — five fixes to make the signal-check pipeline statistically honest

## What this is

The pipeline in this repo asks "does this trading signal have a real edge, or
is it luck?". A review found five ways the answer can still be flattering.
This plan makes five changes that each remove one source of self-deception:

1. **Hold-out period** — keep the last 12 months of data untouched, so there is
   one number that no tuning ever saw.
2. **Multiple-testing ledger** — record every run, and raise the bar for
   "significant" as the number of runs grows.
3. **Better selection metric + a benchmark** — pick parameters on trade-level
   profit factor with a minimum-trade floor, and show Sharpe and buy-and-hold
   next to the result.
4. **Charge the shorts** — shorts currently cost nothing to hold, which is
   fantasy. Charge a funding cost, and add a long-only mode.
5. **Test suite with a lookahead tripwire** — fast unit tests, plus one test
   that catches the worst bug class in backtesting (using data from the future).

## Files

| File | What happens |
| --- | --- |
| `check.py` | Most of the work: holdout split + `--holdout`, ledger, new metrics, funding cost, `--direction` |
| `data.py` | Add one helper: `split_holdout()` |
| `strategies.py` | Add a `Base` class that all strategies inherit, giving them the `direction` filter |
| `trials.csv` | New, at repo root. Created on first run, appended to thereafter |
| `tests/` | New: `conftest.py`, `test_indicators.py`, `test_permute.py`, `test_metrics.py`, `test_lookahead.py` |

## Do not touch

- `permute.py` — the shuffle algorithm must not change.
- `dashboard.py` / `dashboard.html`, `robustness.py`, `robustness_devma.py`,
  `assets_devma.py`, `equities_devma.py`, anything under `adws/`.

## Two hard constraints — read these before you start

These are contracts that other files rely on. Breaking either is a silent
regression.

1. **`check.run(df, strat, params)` must keep returning exactly
   `(rets, stats)`.** `dashboard.py` line 84 does
   `rets, stats = check.run(df, strat, params)`. You may change what is *in*
   `rets`, but not the shape of the return value.
2. **The verdict must keep printing the exact strings `LOOKS REAL`,
   `NOT PROVEN` and `NO EDGE`.** `dashboard.py` `verdicts()` greps the report
   files for those three substrings. Everything else about the report text is
   free to change.

---

# Fix 1 — hold-out period

## Intent

Stages 1–4 are all forms of looking at the data. Anything you look at, you can
accidentally tune to. Reserve the last 12 months so there is exactly one number
in the whole project that selection bias cannot reach.

## `data.py` — add one helper

```python
def split_holdout(df, months=12):
    """Split a price frame into (working set, hold-out).

    The hold-out is the final `months` months of data. Nothing in the
    optimisation, walk-forward or verdict stages may see it.
    Returns (work, holdout). `holdout` may be empty if the data is short.
    """
    cutoff = df.index[-1] - pd.DateOffset(months=months)
    return df[df.index <= cutoff], df[df.index > cutoff]
```

## `check.py` — normal runs

In `main()`, right after `df = data.load(...)`:

- Keep the full frame as `full_df`.
- `work_df, holdout_df = data.split_holdout(full_df)`.
- **Every existing stage (1, 2, 3, 4) and the verdict now uses `work_df`, not
  `df`.** Rename the variable or reassign `df = work_df` immediately so no
  stage can accidentally use the full frame.
- Print, and put in the report, two lines:

```
Data used:     4680 12h bars, 2017-09-01 to 2024-08-07
Reserved:       730 12h bars, 2024-08-08 to 2025-08-07  (hold-out, untouched)
```

If `holdout_df` is empty, say so plainly (`Reserved: none - dataset is shorter
than 12 months`) and carry on.

## `check.py` — `--holdout` mode

Add `ap.add_argument("--holdout", action="store_true", help="run once on the
reserved period and stop")`.

When the flag is set, skip stages 1–4 entirely and do this instead:

1. Load and split as above.
2. Run `walkforward(work_df, strat, args.train_bars, args.test_bars)` on the
   **working set only** to obtain `folds`. Take `folds[-1]["params"]` — the
   parameters the walk-forward last chose. No permutation tests are run in this
   mode; it should take a couple of minutes, not hours.
3. Run one backtest on the **full** frame (`full_df`) with those parameters.
   Running on the full frame is what warms the indicators up; because every
   indicator in `strategies.py` is causal (only ever looks backwards), including
   the earlier data cannot leak the hold-out into itself.
4. Slice the results to the hold-out only:
   - `hold_rets = rets[rets.index >= holdout_df.index[0]]`
   - trades: rows of `stats["_trades"]` with `EntryTime >= holdout_df.index[0]`
5. Report, from the hold-out slice only: total return, trade-level profit
   factor (Fix 3), Sharpe (Fix 3), number of trades, and buy-and-hold return
   over the same period.
6. Print this warning verbatim, above the numbers:

```
HOLD-OUT RESULT - look at this once per strategy, then stop.
The moment you change the strategy because of what you see here, this
number stops being a hold-out and becomes just another in-sample result.
```

7. Write the report to `holdout_<strategy>_<timeframe>.txt`.
   **Not `report_...`** — `dashboard.py` matches `report_(\w+?)(?:_(\w+))?\.txt`
   and would list a hold-out file as a phantom extra timeframe.
8. Append a ledger row with `mode=holdout` (see Fix 2).

## Done means

- A normal `check.py` run prints both the range it used and the range it
  reserved.
- `check.py --holdout` prints the hold-out result plus the warning.

---

# Fix 2 — multiple-testing ledger

## Intent

Run twenty strategies against the same data and one will clear p < 0.05 by
chance alone. The ledger makes that cost visible instead of invisible.

## The file

`trials.csv` at repo root. Create it with a header row if it does not exist.
Keep it tracked in git — it is the record; that is the whole point. Do not add
it to `.gitignore`. It holds no sensitive data.

Columns, in this order:

```
timestamp,mode,strategy,timeframe,direction,train_bars,test_bars,p_insample,p_walkforward,wf_pf,wf_sharpe,wf_trades,verdict
```

- `mode` is `full` for a normal run, `holdout` for a `--holdout` run.
- For `holdout` rows leave `p_insample`, `p_walkforward`, `wf_pf`, `wf_sharpe`
  empty and set `verdict` to `HOLDOUT`.
- `timestamp` is ISO-8601 local time to the second.
- Use the stdlib `csv` module. No new dependency.

## Two small functions in `check.py`

```python
LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trials.csv")

def append_trial(row):  # row is a dict keyed by the column names
    """Add one line to trials.csv, writing the header if the file is new."""

def count_trials():
    """Distinct strategy-timeframe pairs ever recorded, counting mode=full
    rows only. Hold-out looks are not selection trials."""
```

`count_trials()` counts **distinct `(strategy, timeframe)` pairs**, not rows —
re-running the same strategy on the same timeframe is one trial, not two. This
matches the wording of the requirement. `direction` is deliberately *not* part
of the key.

## Order of operations in `main()`

Compute the verdict → **append the row** → **then** call `count_trials()`. That
way the current run is included in its own correction, which is correct: this
run is one of the trials.

## Verdict text

Print the raw PASS/FAIL checks as they are today, then add this block:

```
  Multiple-testing correction
    14 distinct strategy-timeframe trials recorded in trials.csv
    Raw bar:       p < 0.0500
    Corrected bar: p < 0.0036   (0.05 / 14, Bonferroni)
    in-sample     p=0.0100   clears raw: YES   clears corrected: NO
    walk-forward  p=0.0200   clears raw: YES   clears corrected: NO
```

Then, in the plain-language verdict paragraph, when a p-value clears the raw
bar but not the corrected one, say so in a sentence like the one the review
asked for:

```
  Passes at 0.05, but with 14 trials the corrected bar is 0.0036 - treat
  LOOKS REAL as provisional.
```

Keep the existing four PASS/FAIL checks on the raw 0.05 threshold so the
`LOOKS REAL` / `NOT PROVEN` / `NO EDGE` label logic is unchanged (the dashboard
depends on those strings). The correction is reported alongside, as an explicit
caveat, not folded into the label.

## Done means

Two consecutive runs grow `trials.csv` by two rows, and the verdict shows the
corrected threshold and whether each p-value clears it.

---

# Fix 3 — better selection metric and a benchmark

## Intent

Per-bar-equity profit factor rewards a strategy that sits flat and drifts. It
also happily picks a parameter set that made three lucky trades. Trade-level
profit factor with a minimum-trade floor is a harder target. Sharpe and
buy-and-hold give the number context.

## Three new functions in `check.py`

```python
MIN_TRADES = 10   # a parameter combo with fewer trades than this is unviable


def trade_profit_factor(stats, df=None):
    """Gross trade profits divided by gross trade losses.

    Uses stats['_trades']['PnL'], adjusted for short funding (Fix 4).
    No trades -> 0.0. All winners -> inf. All losers -> 0.0.
    """


def sharpe(rets, df):
    """Annualised Sharpe of a per-bar log-return series.

    mean(rets) / std(rets) * sqrt(bars per year), where bars per year is
    derived from the spacing of df.index. Returns 0.0 if std is 0 or the
    series is empty.
    """


def buy_and_hold_pct(df, start=None, end=None):
    """Percentage return of simply holding the asset over a slice."""
```

For `sharpe`, get bars per year from the index spacing:

```python
bar_hours = (df.index[1] - df.index[0]).total_seconds() / 3600
bars_per_year = 365.25 * 24 / bar_hours
```

## Change `optimize()`

```python
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
```

Score unviable combos **0.0, not `-inf`**. Profit factor is never negative, so
0.0 is already the worst possible real score. This keeps two things working:
`best_params` is always set (no crash when every combo is thin), and the
permutation p-values stay meaningful — a shuffled series with no viable combo
scores 0.0, which is legitimately worse than any viable real result.

Because `mcpt_insample()` scores each shuffle through `optimize()`, stage 2's
real and shuffled scores are both trade-level PF automatically. Nothing else in
that function changes.

## Leave stage 4's score alone

`mcpt_walkforward()` scores the stitched out-of-sample equity with the existing
per-bar `profit_factor()`. Keep it. The stitched curve spans folds with
different parameters, so per-bar is the honest measure there, and real and
shuffled are still scored identically — which is what makes the p-value valid.
Keep `profit_factor()` in the file; it is still used here and by the folds.

## Stage 3 and the verdict

Stage 3 already prints out-of-sample total return, profit factor and trades.
Add to it, and to the verdict block:

```
  Out-of-sample:  total return 41.2%,  profit factor 1.18,  trades 63
  Sharpe (annualised): 0.62
  Buy and hold over the same period (2019-08-01 to 2024-08-07): 310.5%
```

The buy-and-hold comparison must cover **the same stitched period the
walk-forward actually traded** — from `wf_rets.index[0]` to `wf_rets.index[-1]`
— not the whole dataset. Compute it with `buy_and_hold_pct(work_df, start, end)`.

## Done means

`optimize()` selects on trade-level PF with the floor; the verdict prints
Sharpe and the buy-and-hold comparison. Report file format changing is fine.

---

# Fix 4 — charge the shorts

## Intent

Holding a short costs money — you are borrowing the asset. Right now shorts are
free, which flatters every strategy that shorts. Charge 0.01% per 8 hours,
pro-rated to the bar size, in **every** stage including the permutation runs, so
real and shuffled data are treated identically.

## Where the cost is applied

Inside `run()`, so every caller gets it with no chance of a stage being missed.

```python
FUNDING_PER_8H = 0.0001   # 0.01% per 8 hours on the notional of a short


def funding_rate_per_bar(df):
    """Pro-rate the 8-hourly funding cost to this data's bar size."""
    bar_hours = (df.index[1] - df.index[0]).total_seconds() / 3600
    return FUNDING_PER_8H * (bar_hours / 8.0)
```

## In `run()`

After `stats = bt.run(**params)` and computing `rets`:

1. Build a boolean mask over the bars, one entry per row of the equity curve,
   marking bars on which a short position was open. For each row of
   `stats["_trades"]` with `Size < 0`, mark bars `EntryBar + 1` through
   `ExitBar` inclusive. (The return recorded on bar *i* is the move into bar
   *i*, so the entry bar itself is not charged and the exit bar is.)
2. Subtract the cost from the log returns on those bars:
   `rets = rets + mask * np.log(1 - rate)` — adding a negative log term is the
   exact multiplicative equivalent of shaving the rate off equity.
3. Return `(rets, stats)` as before. **Do not change the return signature.**

Note the consequence: `stats["Return [%]"]` and the raw `stats["_equity_curve"]`
still exclude funding, because they come from the broker. Anywhere the report
prints a return figure, derive it from the adjusted `rets` instead:
`(np.exp(rets.sum()) - 1) * 100`. Fix this in **Stage 1** (which currently reads
`stats['Return [%]']`) as well as everywhere else. Stage 3 already computes its
return from `rets`, so it picks the cost up for free.

## Trade-level PF must feel it too

Otherwise the optimiser's selection metric (Fix 3) would still see shorts as
free. In `trade_profit_factor(stats, df)`, before summing PnL, subtract a
funding charge from each short trade:

```
bars_held    = ExitBar - EntryBar
notional     = abs(Size) * EntryPrice
charge       = notional * funding_rate_per_bar(df) * bars_held
adjusted_pnl = PnL - charge      # for rows where Size < 0
```

`abs(Size) * EntryPrice` is the correct cash notional even under
`FractionalBacktest` — it scales price down and size up by the same factor, so
the product is unchanged.

## `--direction` flag

Add `ap.add_argument("--direction", default="both", choices=["both", "long",
"short"])`.

Implement it once, in `strategies.py`, rather than editing eight `next()`
methods. Every strategy calls `self.buy()` / `self.sell()`, so intercepting
those two methods covers all of them:

```python
class Base(Strategy):
    """Shared base for every strategy in this file.

    `direction` filters which side may be opened:
      both  - unchanged
      long  - sell() is ignored, so a short signal just flattens the position
      short - buy() is ignored
    Strategies already call `self.position.close()` before opening the
    opposite side, so ignoring the open is exactly the behaviour we want.
    """
    direction = "both"

    def buy(self, **kwargs):
        if self.direction == "short":
            return None
        return super().buy(**kwargs)

    def sell(self, **kwargs):
        if self.direction == "long":
            return None
        return super().sell(**kwargs)
```

Then change all eight strategy classes to inherit `Base` instead of `Strategy`
(`Combo` already inherits `Devma`, so it needs no change). `Devma` already has
its own `direction` attribute used by `robustness_devma.py` — leave its
existing `next()` checks in place. They become redundant but stay correct, and
`robustness_devma.py` keeps working untouched.

In `check.py`, pass the direction into every backtest by setting it on the
strategy class once, in `main()`, before any stage runs:

```python
strat = REGISTRY[args.strategy]
strat.direction = args.direction
```

Setting it on the class (not per-run params) keeps it out of the optimiser grid
and guarantees permutation runs use the same setting as real runs.

## Verdict must name the mode

Add a line to the verdict block and the report header:

```
  Direction mode: long-only   (shorts disabled for this run)
```

Also record `direction` in the ledger row (Fix 2).

## Done means

A strategy that shorts frequently scores measurably worse than before;
`--direction long` runs and labels its verdict; costs are identical between real
and permuted runs (guaranteed, because the cost lives in `run()`).

---

# Fix 5 — pytest suite with a lookahead tripwire

## Ground rules

- No network, no downloads, no `data.load()`, no full pipeline runs. Every test
  builds its own small synthetic OHLCV frame.
- The whole suite must finish in well under a minute.
- Run with:
  `uv run --with pytest --with-requirements requirements.txt pytest -q tests`

## `tests/conftest.py`

Two jobs.

1. Put the repo root on the import path, so `import strategies` works. With no
   `__init__.py` in `tests/`, pytest inserts `tests/` on `sys.path`, not the
   repo root:

```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

2. Provide shared fixtures that build synthetic frames:
   - `tiny_frame()` — a ~10-bar OHLCV frame with hand-chosen values, used for
     the indicator tests. Choose the highs and lows so swings are obvious when
     you read them (e.g. a clear peak at bar 3 and a clear trough at bar 6).
   - `synthetic_frame(n=700, freq="12h", seed=0)` — a seeded geometric random
     walk with `Open/High/Low/Close/Volume` columns and a `DatetimeIndex` at
     12-hour spacing. Build High as `max(Open, Close) + noise` and Low as
     `min(Open, Close) - noise` so OHLC is always valid. Deterministic for a
     given seed.

## `tests/test_indicators.py`

Cover `swing_high`, `swing_low`, `anchored_sma`, `last_swing_levels`,
`sticky_state`, `rejection` on the ~10-bar frame.

**Write the expected values as literals you derived by reading each function's
definition and working through the bars by hand.** Do not generate them by
calling the function and pasting the output — a test that asserts a function
equals itself catches nothing.

Points worth asserting explicitly, because they are the parts people get wrong:

- `swing_high(high, n)` is True on the bar where the swing is **confirmed**
  (n bars *after* the peak), not on the peak itself.
- `anchored_sma` re-anchors at every event and is NaN before the first one.
- `last_swing_levels(values, events, k)` returns the value at the bar *before*
  the event bar (`high[1]` in the Pine original), and NaN until enough events
  have occurred.
- `sticky_state` holds the previous state through flat bars and is NaN before
  the first move.
- `rejection` bull = opened above the level, dipped below, closed back above.
  Include a bar that touches but does not cross, and assert it is False.

## `tests/test_permute.py`

Use `synthetic_frame` and `permute_bars(df, start_index=k, rng=np.random.default_rng(seed))`.

- **OHLC integrity**: `High >= max(Open, Close)` and `Low <= min(Open, Close)`
  for every bar, with a 1e-9 tolerance.
- **Prefix preserved**: rows `0..start_index` inclusive are exactly equal to the
  input frame.
- **Determinism**: two calls with `default_rng(7)` produce identical frames;
  a call with `default_rng(8)` produces a different one.
- **Return distribution moments** — read this carefully, the obvious test is
  wrong:

  A permuted bar's close-to-close log return is `gap[gi] + r_c[bi]` where the
  gap and the intrabar move come from **two independent shuffles**. So the
  multiset of close-to-close returns is *not* preserved, and asserting equal
  standard deviation will fail.

  What *is* exactly preserved, and what you should assert:
  - The **sum** (hence the mean) of close-to-close log returns over the
    permuted region matches the real series' to ~1e-9, because both shuffles
    are permutations of the same values.
  - The **multiset of intrabar moves** is preserved: over the permuted region,
    `np.sort(log(High/Open))`, `np.sort(log(Low/Open))` and
    `np.sort(log(Close/Open))` each match the real series' sorted values.
  - The **multiset of gaps** is preserved: `np.sort(log(Open[i]/Close[i-1]))`
    over the permuted region matches the real series'.

  Add a one-line comment in the test saying why std is not asserted, so a future
  reader does not "fix" it.

## `tests/test_metrics.py`

Edge cases for `check.profit_factor`, `check.trade_profit_factor` and
`check.pvalue`:

- `profit_factor`: all gains -> `inf`; all losses -> `0.0`; empty series ->
  `0.0`; a mixed series -> a hand-computed ratio.
- `trade_profit_factor`: no trades -> `0.0`; all winning trades -> `inf`; all
  losing -> `0.0`. Build a small fake `stats` dict holding a `_trades`
  DataFrame with the columns the function reads (`Size`, `EntryBar`, `ExitBar`,
  `EntryPrice`, `PnL`) rather than running a backtest.
- `pvalue`: no shuffle beats the real score -> `1 / (1 + n)`; every shuffle
  beats it -> `1.0`; empty `perm_scores` -> `1.0`.

## `tests/test_lookahead.py` — the tripwire

This is the test that earns its keep. A strategy that accidentally reads a
future bar will show a *different* signal at bar 50 depending on whether the
data ends at bar 520 or bar 700. A causal strategy cannot.

```python
@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_no_lookahead(name, synthetic_frame):
    ...
```

For each strategy:

1. Build a 700-bar synthetic 12h frame. 700 bars clears the largest
   `WARMUP` in the registry (`Devma.WARMUP = 360`) with room to spare.
2. Pick `t = 517`. Two requirements: comfortably past every WARMUP, and
   **deliberately not on a 2-day or 3-day boundary** from the start of the
   series. `Devma` resamples to `"2D"` and `"3D"` bands; truncating mid-bucket
   is exactly the case the `.shift(1)` in `htf_bands()` exists to protect, so
   this is where the tripwire bites.
3. Run the strategy twice with default parameters, once on `df.iloc[:t]` and
   once on the full `df`, using `FractionalBacktest` with the same settings
   `check.run()` uses.
4. Pull the precomputed signal arrays off each run's strategy instance:
   `stats["_strategy"]` is the strategy object, and every `self.I(...)`
   attribute on it is a numpy array as long as the data it was run on. Collect
   them generically:

```python
def signal_arrays(stats, n):
    """Every precomputed indicator array on the strategy instance."""
    strat_obj = stats["_strategy"]
    out = {}
    for attr in dir(strat_obj):
        if attr.startswith("_"):
            continue
        val = getattr(strat_obj, attr, None)
        if isinstance(val, np.ndarray) and val.shape[-1] == n:
            out[attr] = np.asarray(val)
    return out
```

5. Assert that for every array present in both runs, the truncated run's values
   equal the full run's first `t` values:
   `np.testing.assert_allclose(trunc[k], full[k][..., :t], equal_nan=True)`.
   Compare on the last axis — a couple of indicators may be 2D.
   Assert the collected dict is non-empty first, so a refactor that renames the
   attributes turns the test red rather than silently passing on nothing.

**Verify the tripwire by reasoning, do not commit a broken variant.** The logic:
`htf_bands()` resamples to a higher timeframe, then calls `.shift(1)` before
mapping back. That shift means each low-timeframe bar sees only the last
*completed* higher-timeframe bar. In the truncated run the final HTF bucket is
partial, and its (different) high/low would land on the bucket after it — which
does not exist in the truncated frame. So the first `t` values match. Remove the
`.shift(1)` and the partial final bucket's values map onto the bars inside it;
those bars now use a max/min computed from fewer bars than the full run
computes, the arrays diverge before index `t`, and the assert fires.

## Done means

`uv run --with pytest --with-requirements requirements.txt pytest -q tests`
passes, in well under a minute.

---

# Order of work

Fixes 3 and 4 both change `run()` and `optimize()`, so do them together. The
suggested order:

1. **Fix 4 first** — `Base` class in `strategies.py`, funding cost in `run()`,
   `--direction` in `check.py`. Nothing else depends on it, and it changes the
   numbers everything else reports.
2. **Fix 3** — `trade_profit_factor`, `sharpe`, `buy_and_hold_pct`, the new
   `optimize()`, the extra report lines.
3. **Fix 1** — `split_holdout()` in `data.py`, the split in `main()`, the
   `--holdout` branch.
4. **Fix 2** — ledger functions, the append call, the verdict block.
5. **Fix 5** — tests last, once the functions they test have settled.

# How to verify

Run these from the repo root. Judge each by its exit status.

```bash
# 1. Tests (fast — run this after every step from Fix 5 onwards)
uv run --with pytest --with-requirements requirements.txt pytest -q tests

# 2. A quick end-to-end run. --quick cuts the shuffles right down.
uv run --with-requirements requirements.txt python check.py \
    --strategy diamond_hands --timeframe 1d --quick

# 3. Same again, to prove the ledger grows by exactly one row per run
uv run --with-requirements requirements.txt python check.py \
    --strategy trend_step --timeframe 1d --quick

# 4. Long-only mode labels its verdict
uv run --with-requirements requirements.txt python check.py \
    --strategy diamond_hands --timeframe 1d --quick --direction long

# 5. Hold-out mode
uv run --with-requirements requirements.txt python check.py \
    --strategy diamond_hands --timeframe 1d --holdout
```

Check by eye after those runs:

- `trials.csv` exists at the repo root with a header and 4 rows (3 `full`,
  1 `holdout`).
- Run 3's verdict shows a corrected bar of `0.05 / 2` = `0.0250` (two distinct
  strategy-timeframe pairs at that point).
- Runs 2 and 4 print different out-of-sample numbers — that is the funding cost
  and the direction filter both biting.
- Run 2's report prints both the data range used and the range reserved, and
  those ranges do not overlap.
- Run 5 writes `holdout_diamond_hands_1d.txt`, not `report_...`.
- `dashboard.py` still starts and lists verdicts:
  `uv run --with-requirements requirements.txt python dashboard.py`

# Out of scope

Data hygiene (cache filenames, gap detection, exchange source tracking), new
strategies, dashboard changes, stamping reports with the git SHA, deflated
Sharpe ratio, White's Reality Check. The permutation algorithm in `permute.py`
must not change.

# Git

Branch, then PR — this touches four files plus a new test directory.

```bash
git checkout -b statistical-honesty-fixes
```
