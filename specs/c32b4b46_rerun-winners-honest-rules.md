# Plan — re-earn the winners' verdicts under the honest rules

## What this is

Three strategy-timeframe combos were called **LOOKS REAL** in `ANALYSIS.md`
before the five honesty fixes landed: DEVMA on 12h, DEVMA on 1d, and Diamond
Hands on 4h. Those verdicts predate the hold-out split, trade-level profit
factor with a minimum-trade floor, short funding costs, and the
Bonferroni-corrected threshold.

Re-run all three through the full pipeline under the new rules and write down
honestly what survives.

**This is a measurement job, not a coding job.** You run three commands, take up
to three hold-out looks, and write a section of `ANALYSIS.md`. The only code you
may change is a genuine crash. You may not touch thresholds, metrics, funding
rates, or permutation logic to make anything pass.

---

# Read this before you run anything

I checked the repo state against the brief and found **two things the brief gets
wrong**. Both change what you type. Do not skip this section.

## Correction 1 — the walk-forward windows are NOT the defaults

The brief says to run each combo with only `--insample-perms` and `--wf-perms`
changed. That would silently use the default `--train-bars 1460 --test-bars 365`
for all three. **Two of the three original runs did not use the defaults.** I
read this out of the old report files:

| Combo | Original window (from the old report) | Is that the default? |
| --- | --- | --- |
| devma 12h | `1460 train / 365 test` | Yes |
| devma 1d | `730 train / 182 test` | **No** |
| diamond_hands 4h | `4380 train / 1095 test` | **No** |

If you use the defaults, you are not re-running the old test — you are running a
different one, and the old-vs-new comparison that is the entire point of this
task becomes meaningless. On 1d the defaults would leave only **3 folds** instead
of 11. On 4h they would produce **43 folds** instead of 11, and take an hour
longer for a result you cannot compare to anything.

**Pass the original windows explicitly.** They are in the commands below.

## Correction 2 — the Bonferroni bar is 0.01, not 0.004

The brief says "with ~12 distinct trials recorded, the Bonferroni bar is about
0.004". I counted the actual ledger:

```
$ python -c "..."   # distinct (strategy, timeframe) pairs with mode=full
2 [('diamond_hands', '1d'), ('trend_step', '1d')]
```

There are **2** distinct trials on record, not 12. Your three reruns add
`devma/12h`, `devma/1d` and `diamond_hands/4h`, ending at **5**. So the final
corrected bar is `0.05 / 5 = 0.0100`.

Two consequences:

1. **Each run prints a different corrected bar**, because the ledger grows as you
   go. Run them in the order below and the reports will read 0.0167 (3 trials),
   then 0.0125 (4), then 0.0100 (5). This is correct behaviour, not a bug. In
   `ANALYSIS.md`, judge all three against the **final 0.0100** bar so the table
   is internally consistent, and add a footnote saying each individual report
   shows the bar as it stood at that moment.
2. **The shuffle counts still work.** The brief's reasoning was based on the
   wrong count but lands in the right place: 250 walk-forward shuffles bottom out
   at `1/251 = 0.0040` and 400 in-sample shuffles at `1/401 = 0.0025`, both
   comfortably below 0.0100. Keep the counts as specified. Do not reduce them.

## Runtime — the brief's estimate is roughly right, and I measured it

I timed a single backtest for each combo on the real cached data:

| Combo | Work bars (after hold-out) | Grid combos | One backtest |
| --- | --- | --- | --- |
| devma 12h | 5,793 | 9 | 0.06s |
| devma 1d | 2,897 | 9 | 0.04s |
| diamond_hands 4h | 17,367 | 12 | 0.17s |

Multiplying out the stages (stage 2 = perms × combos; stage 4 = perms × folds ×
(combos + 1)) gives roughly:

- devma 12h: **~20 minutes**
- devma 1d: **~12 minutes**
- diamond_hands 4h: **~50 minutes**

**About 80 minutes total.** Run them sequentially in the background and let them
finish. Do not poll in a tight loop, and do not shrink the shuffle counts to
hurry it up.

---

# Step 1 — save the old reports before you overwrite them

`report_devma_12h.txt` and `report_devma_1d.txt` will be overwritten by the
reruns, and they are gitignored, so git will not save you. The old numbers also
live in `ANALYSIS.md`, but keep the full files while you work:

```bash
mkdir -p /tmp/prefix_reports
cp report_devma_12h.txt report_devma_1d.txt report_diamond_hands.txt /tmp/prefix_reports/
```

(`report_diamond_hands.txt` is the old 4h run — it predates the timeframe going
into the filename, so the new run writes `report_diamond_hands_4h.txt` and will
not clobber it.)

# Step 2 — the three runs

Run these **one at a time, in this order**, in the background, each tee'd to a
log so you can read what happened.

```bash
uv run --with-requirements requirements.txt python check.py \
    --strategy devma --timeframe 12h \
    --train-bars 1460 --test-bars 365 \
    --insample-perms 400 --wf-perms 250 2>&1 | tee /tmp/rerun_devma_12h.log
```

```bash
uv run --with-requirements requirements.txt python check.py \
    --strategy devma --timeframe 1d \
    --train-bars 730 --test-bars 182 \
    --insample-perms 400 --wf-perms 250 2>&1 | tee /tmp/rerun_devma_1d.log
```

```bash
uv run --with-requirements requirements.txt python check.py \
    --strategy diamond_hands --timeframe 4h \
    --train-bars 4380 --test-bars 1095 \
    --insample-perms 400 --wf-perms 250 2>&1 | tee /tmp/rerun_dh_4h.log
```

Direction mode is the default `both` for all three. Do not pass `--direction`.

## What to pull out of each run

From each report file (`report_<strategy>_<timeframe>.txt`):

- Stage 1 return and buy-and-hold
- Stage 2 best params + trade-level profit factor, and `p (in-sample)`
- Stage 3 out-of-sample return, profit factor, trades, **Sharpe**, and the
  **buy-and-hold over the same stitched period**
- Stage 4 `p (walk-forward)`
- The verdict label, the four PASS/FAIL checks, and the multiple-testing block
- The `Data used:` / `Reserved:` ranges

## Two things that are findings, not bugs

- **A combo scores 0.0 in stage 2, or folds pick odd parameters.** `optimize()`
  now scores any parameter combo with fewer than `MIN_TRADES = 10` trades in the
  window as 0.0 (unviable). Diamond Hands on 4h averaged about 4 out-of-sample
  trades per fold in the old run, so some of its training windows may genuinely
  fall below the floor. If that happens, it is the floor doing its job — the
  strategy is too thin to select on. Write it down as a result. Do not lower the
  floor.
- **Numbers are worse than the old run.** That is the expected outcome of
  charging shorts, using a stricter selection metric, and cutting 12 months off
  the data. That is the finding.

## If a run crashes

Fixing a genuine crash is in scope. Fix the smallest thing that makes it run,
say what you changed and why in the PR, and re-run that combo from the start.
Tuning results is not in scope — if you find yourself changing a threshold, a
funding rate, a metric or the permutation logic, stop and hand it back.

# Step 3 — hold-out looks, for survivors only

**Only for combos whose rerun still says `LOOKS REAL` at the raw 0.05 bar.** A
combo that failed the rerun does not get a hold-out look. The one-shot look is
spent on surviving candidates only, and once spent it cannot be un-spent.

For each survivor, with the same window flags:

```bash
uv run --with-requirements requirements.txt python check.py \
    --strategy devma --timeframe 12h \
    --train-bars 1460 --test-bars 365 --holdout
```

This takes a couple of minutes — it runs the walk-forward once to pick the final
fold's parameters, with no shuffles. It writes `holdout_<strategy>_<tf>.txt` and
adds a `mode=holdout` row to the ledger, which does **not** count toward the
trial total.

Record from it: total return, trade-level profit factor, Sharpe, trades, and
buy-and-hold over the hold-out period.

Then stop looking. Do not run a hold-out twice for the same combo, and do not
change anything because of what it says.

# Step 4 — write the ANALYSIS.md section

Add a new dated section. Put it after the DEVMA section and before "Combining
Diamond Hands and DEVMA", so the file stays roughly chronological.

Match the existing tone: plain language, short sentences, a table then prose
that says what it means. Look at the "Rerun: Diamond Hands on 4-hour bars"
section as the model — it states the result, then states the caveat that must
travel with it.

```markdown
## Reruns under the honest rules (2026-08-07)

[One short paragraph: what changed in the pipeline since these three were
first judged — hold-out split, trade-level profit factor with a 10-trade
floor, funding cost on shorts, Bonferroni-corrected threshold — and why the
old verdicts needed re-earning.]

| | DEVMA 12h | DEVMA 1d | Diamond Hands 4h |
|---|---|---|---|
| Old verdict | LOOKS REAL (4/4) | LOOKS REAL (4/4) | LOOKS REAL (4/4) |
| New verdict | | | |
| Direction mode | both | both | both |
| Data used / reserved | | | |
| OOS return | | | |
| Buy & hold, same period | | | |
| OOS trade-level PF | | | |
| Sharpe (annualised) | | | |
| OOS trades | | | |
| p in-sample | | | |
| p walk-forward | | | |
| Clears raw 0.05? | | | |
| Clears corrected 0.0100? | | | |
| Hold-out result | | | |
```

Then prose covering, plainly:

- **Which of the three survived and which died.** Name them.
- **Why each one died**, attributed to a specific cause — funding cost on shorts,
  the stricter trade-level metric and its 10-trade floor, the corrected
  threshold, or the reserved hold-out shrinking the data (12h lost 730 of 6,523
  bars, 1d lost 365 of 3,262, 4h lost 2,190 of 19,557). If you cannot tell which
  cause dominated, say that rather than guessing.
- **The buy-and-hold comparison.** If a strategy made money out of sample but
  less than simply holding Bitcoin over the same period, say so in plain words.
  That is the comparison a reader cares about most and the old analysis never
  showed it.
- **The hold-out numbers** for any survivor, with the standing caveat: it is one
  look, it is not a guarantee, and it must not be tuned against.
- **A footnote** that the corrected bar is `0.05 / 5 = 0.0100` as of this
  session's ledger, that it tightens as more trials are recorded, and that each
  individual report file shows the bar as it stood when that run finished.

Also add a line to the older sections — or immediately under the scoreboard —
noting that the pre-fix verdicts above were produced under looser rules and are
superseded by this section. A reader who stops at the scoreboard should not walk
away with a stale LOOKS REAL.

# Step 5 — verify and commit

```bash
# The suite must still pass, untouched
uv run --with pytest --with-requirements requirements.txt pytest -q tests
```

Check by eye:

- `trials.csv` has **three new `mode=full` rows** — devma/12h, devma/1d,
  diamond_hands/4h — plus one `mode=holdout` row per survivor.
- The distinct full-trial count is now 5:
  ```bash
  python -c "import csv;print(len({(r['strategy'],r['timeframe']) for r in csv.DictReader(open('trials.csv')) if r['mode']=='full'}))"
  ```
- `report_devma_12h.txt`, `report_devma_1d.txt` and `report_diamond_hands_4h.txt`
  all exist and are freshly dated.
- `ANALYSIS.md` carries the new section and the tables render (count your pipes).

Commit on a branch and open a PR:

```bash
git checkout -b rerun-winners-honest-rules
git add ANALYSIS.md trials.csv specs/
git commit
gh pr create
```

`trials.csv` must be committed — it is the record that makes the correction
mean anything. The `report_*.txt` and `holdout_*.txt` files are gitignored and
stay that way; their numbers live in `ANALYSIS.md` instead.

Put the headline in the PR description: which of the three old LOOKS REAL
verdicts survived, and which did not.

# Out of scope

Changing thresholds, metrics, funding rates or permutation logic to make a
strategy pass. Dashboard changes. The robustness batteries. Anything under
`adws/`. New strategies. Re-running combos that are not one of these three.
