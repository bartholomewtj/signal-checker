# Five fixes to make the pipeline statistically honest

Make the five changes below to the signal-check pipeline. They were agreed
after a critical review; the intent of each is stated so no fix drifts.

Where: check.py, data.py, strategies.py (only if a fix requires it), plus new
files tests/ and trials.csv. Do not touch permute.py's shuffle algorithm,
dashboard.py/dashboard.html, the robustness*.py batteries, or anything under
adws/.

## Fix 1 — hold-out period

Reserve the final 12 months of every dataset as a hold-out that no
optimisation, walk-forward, or verdict stage ever sees. check.py runs stages
1–4 on data ending 12 months before the last cached candle. Add a
`--holdout` flag that runs the strategy exactly once on the reserved period
(using the final walk-forward fold's chosen parameters) and reports its
result separately, clearly labelled as the one number selection bias cannot
reach.

Done means: a normal `check.py` run prints the data range it used and the
range it reserved; `check.py --holdout` prints the hold-out result and warns
that it should be looked at once per strategy, not tuned against.

## Fix 2 — multiple-testing ledger

Every check.py run appends one row to `trials.csv` at repo root (strategy,
timeframe, date, headline p-values, verdict). The verdict stage reads the
ledger, counts distinct strategy-timeframe trials ever run, and reports the
Bonferroni-adjusted threshold (0.05 divided by that count) alongside the raw
0.05 one. The verdict text must state both, e.g. "passes at 0.05 but with 14
trials the corrected bar is 0.0036 — treat LOOKS REAL as provisional".

Done means: two consecutive runs grow trials.csv by two rows, and the
verdict text shows the corrected threshold and whether each p-value clears it.

## Fix 3 — better selection metric and a benchmark

Replace per-bar-equity profit factor as the optimiser's selection score with
trade-level profit factor (gross trade profits / gross trade losses) combined
with a minimum-trade floor: parameter combos producing fewer than 10 trades
in the window score as unviable. Report the Sharpe ratio (mean per-bar return
over its standard deviation, annualised) of the walk-forward equity alongside
profit factor. Add a buy-and-hold line to the verdict: the walk-forward
out-of-sample return must be shown next to buy-and-hold return over the same
stitched period.

Done means: optimize() selects on trade-level PF with the floor; the verdict
prints Sharpe and the buy-and-hold comparison. Existing report file format
may change; that is fine.

## Fix 4 — charge the shorts

Short positions currently pay nothing to hold, which is unrealistic for spot
crypto. Apply a funding/borrow cost of 0.01% per 8 hours (pro-rated to the
bar size) to equity for every bar a short position is open, in all stages
including permutation runs so real and shuffled are treated alike. Add a
`--direction` flag (both/long/short, default both) so a long-only verdict
can be produced; the verdict must name which direction mode produced it.

Done means: a strategy that shorts frequently scores measurably worse than
before; `--direction long` runs and labels its verdict; costs are identical
between real and permuted runs.

## Fix 5 — pytest suite with a lookahead tripwire

Create tests/ with fast unit tests (no network, no full pipeline runs, no
downloads; build small synthetic OHLCV frames in the tests). Cover:
- swing_high, swing_low, anchored_sma, last_swing_levels, sticky_state,
  rejection against hand-computed expectations on ~10-bar series.
- permute_bars: OHLC integrity (High >= max(Open,Close), Low <= min),
  identical return distribution moments, prefix preserved up to start_index,
  determinism for a fixed rng seed.
- profit_factor and pvalue edge cases (all-gains, all-losses, empty).
- A lookahead tripwire: for every strategy in REGISTRY, compute its
  precomputed signal arrays on a truncated copy data[:t] and on the full
  series, and assert the first t signals match. Use a small synthetic series
  sized to clear each strategy's WARMUP.

Done means: `uv run --with pytest --with-requirements requirements.txt
pytest -q tests` passes, runs in well under a minute, and the lookahead test
genuinely fails if a shift(1) is removed from an HTF band (verify by
reasoning, do not commit a broken variant).

## Out of scope

Data hygiene changes (cache filenames, gap detection, exchange source
tracking), new strategies, dashboard changes, report stamping with git SHA,
deflated Sharpe ratio, White's Reality Check. The permutation algorithm in
permute.py must not change.
