# Plan — finish the rerun: one hold-out look, then write it up

## Read this first: the three reruns are already done

A builder has already run all three combos through the full pipeline, using the
corrected walk-forward windows. **Do not re-run them.** Each took real time and
re-running would add duplicate rows to `trials.csv` and waste an hour.

What is already on disk:

- `report_devma_12h.txt`, `report_devma_1d.txt`, `report_diamond_hands_4h.txt`
- Three new `mode=full` rows in `trials.csv` (uncommitted — `git status` shows
  `M trials.csv`)
- The distinct full-trial count is now **5**, so the final corrected bar is
  `0.05 / 5 = 0.0100`

**Two things remain:** the hold-out look for the single survivor, and the
`ANALYSIS.md` write-up. Then commit.

---

# The results, already extracted

I read all three reports so you do not have to re-derive anything. These numbers
are the source of truth for the write-up.

## Headline

**Of the three old LOOKS REAL verdicts, one survived and two died.**

| Combo | Old verdict | New verdict |
| --- | --- | --- |
| DEVMA 12h | LOOKS REAL (4/4) | **LOOKS REAL (4/4)** — provisional |
| DEVMA 1d | LOOKS REAL (4/4) | **NOT PROVEN (2/4)** |
| Diamond Hands 4h | LOOKS REAL (4/4) | **NOT PROVEN (3/4)** |

## Old vs new, side by side

| | DEVMA 12h old | DEVMA 12h new | DEVMA 1d old | DEVMA 1d new | DH 4h old | DH 4h new |
|---|---|---|---|---|---|---|
| Full backtest | +872% | +505.8% | +894% | +674.3% | +1094.9% | +813.3% |
| OOS return | +208% | +231.7% | +240% | +150.2% | +119.3% | +233.7% |
| OOS PF | 1.052 | 1.061 | 1.070 | 1.059 | 1.085 | 1.065 |
| OOS trades | 204 | 169 | 158 | 132 | 42 | 44 |
| Sharpe | — | 0.44 | — | 0.33 | — | 0.63 |
| p in-sample | 0.005 | 0.0399 | 0.015 | 0.0698 | 0.025 | 0.0075 |
| p walk-forward | 0.010 | 0.0159 | 0.010 | 0.0598 | 0.030 | 0.0558 |
| Max drawdown | −66% | −64.9% | −53% | −52.6% | −57% | −59.5% |

Other new numbers worth having to hand:

- **Windows used** (matching the originals): 12h `1460/365`, 1d `730/182`,
  4h `4380/1095`. Direction mode `both` throughout.
- **Data used / reserved:** 12h 5,793 bars used, 730 reserved (2025-08-07 to
  2026-08-06). 1d 2,897 used, 365 reserved. 4h 17,367 used, 2,190 reserved.
- **Stage 2 best trade-level PF:** 12h 1.167 `{vol_ma:10, vol_run:3}`; 1d 1.203
  `{vol_ma:10, vol_run:3}`; 4h **3.005** `{lookback:48, trend_len:300}`.

## The buy-and-hold comparison — this is the most important new number

Every one of the three earned far less out of sample than simply holding Bitcoin
over the same stitched period:

| Combo | OOS return | Buy & hold, same period | Period |
| --- | --- | --- | --- |
| DEVMA 12h | +231.7% | **+767.4%** | 2019-09-01 → 2025-02-28 |
| DEVMA 1d | +150.2% | **+892.8%** | 2019-09-01 → 2025-02-22 |
| Diamond Hands 4h | +233.7% | **+767.5%** | 2019-09-03 → 2025-03-03 |

The old analysis never showed this. All three underperformed doing nothing, by a
factor of three to six. Say it plainly.

## Three traps in reading these results

You must get these right or the write-up will be wrong.

### Trap 1 — the corrected bar in each report is stale

Each report shows the bar as it stood when that run finished, because the ledger
grew as the runs went: 12h saw 3 trials (0.0167), 1d saw 4 (0.0125), 4h saw 5
(0.0100). **The final bar is 0.0100.**

The DEVMA 12h report says its walk-forward p "clears corrected: YES" — that was
against 0.0167. Against the final **0.0100 it does not clear** (p = 0.0159).
Do not copy that YES into the table.

Judged against the final 0.0100 bar:

| Combo | p in-sample | Clears 0.0100? | p walk-forward | Clears 0.0100? |
| --- | --- | --- | --- | --- |
| DEVMA 12h | 0.0399 | No | 0.0159 | **No** |
| DEVMA 1d | 0.0698 | No | 0.0598 | No |
| Diamond Hands 4h | 0.0075 | **Yes** | 0.0558 | No |

**So no combo clears the corrected bar on both p-values.** DEVMA 12h survives at
the raw bar only. That is the honest bottom line.

### Trap 2 — the old p-values were at their resolution floor

The old runs used 200 in-sample / 100 walk-forward shuffles. The smallest
p-value 100 shuffles can produce is `1/101 = 0.0099`. So DEVMA's old
`p_wf = 0.010` on both timeframes meant "**zero** of 100 shuffles beat it" — it
was pinned at the floor and could not go lower.

The new runs use 400/250. DEVMA 12h's new `p_wf = 0.0159` is `(1+3)/251` — three
of 250 shuffles beat it. That is a modest, partly-resolution change, not a
collapse. Do not write "the p-value went up 60%" as though it were a dramatic
degradation.

The in-sample move is different and **is** real: DEVMA 12h went from 0 of 200
shuffles beating it to **15 of 400**. That is a genuine shift, caused by the
stricter metric and the funding cost, not by resolution.

### Trap 3 — Diamond Hands 4h has an overfitting signature, not an edge

Its in-sample p of 0.0075 is the strongest single number in the whole rerun and
clears even the corrected bar. But look at the pair: stage 2 found a trade-level
PF of **3.005** in sample, while the walk-forward delivered **1.065** out of
sample, with `p_wf = 0.0558` failing the raw bar. A selection score of 3.0
collapsing to 1.07 out of sample is the classic overfit fingerprint — the
optimiser found something in the training windows that did not survive contact
with unseen data. And 44 out-of-sample trades across 11 folds is about 4 per
fold, which is thin. Frame it that way rather than as "nearly passed".

---

# Step 1 — the hold-out look, for DEVMA 12h only

**DEVMA 12h is the only combo that says LOOKS REAL at the raw 0.05 bar, so it is
the only one that earns a hold-out look.** DEVMA 1d and Diamond Hands 4h both
came back NOT PROVEN and must not get one — the one-shot look is spent only on
surviving candidates, and once spent it cannot be un-spent.

```bash
uv run --with-requirements requirements.txt python check.py \
    --strategy devma --timeframe 12h \
    --train-bars 1460 --test-bars 365 --holdout
```

The window flags must match the rerun, because `--holdout` runs the walk-forward
to pick the final fold's parameters and different windows would pick different
ones. This takes a couple of minutes — it runs no shuffles.

Record from `holdout_devma_12h.txt`: the parameters chosen, total return,
trade-level profit factor, Sharpe, trade count, and buy-and-hold over the
hold-out period (2025-08-07 to 2026-08-06).

Then stop. Do not run it twice, and do not change anything because of what it
says.

# Step 2 — write the ANALYSIS.md section

Add a dated section titled `## Reruns under the honest rules (2026-08-07)`.
Place it **after** the "Added later: DEVMA" section and **before** "Combining
Diamond Hands and DEVMA", so the file stays chronological.

Match the existing tone — plain language, short sentences, table then prose that
says what it means. The "Rerun: Diamond Hands on 4-hour bars" section is the
model: state the result, then state the caveat that must travel with it.

Structure:

1. **A short opening paragraph** — what changed in the pipeline since these three
   were first judged (hold-out split, trade-level profit factor with a 10-trade
   floor, funding cost on shorts, Bonferroni-corrected threshold), and why the
   old verdicts needed re-earning.

2. **The main table.** Use the numbers above. Columns: strategy, timeframe, old
   verdict, new verdict, direction mode, data used / reserved, OOS return,
   buy-and-hold over the same period, OOS trade-level PF, Sharpe, OOS trades,
   p in-sample, p walk-forward, clears raw 0.05, clears corrected 0.0100, and
   hold-out result (DEVMA 12h only; `—` for the other two, with a note that they
   did not earn a look).

3. **Prose covering, plainly:**
   - **Which survived and which died.** One survived — DEVMA 12h, and only
     provisionally. Two died.
   - **Why each died.** DEVMA 1d: both p-values drifted past 0.05 (0.0698 and
     0.0598) once shorts paid funding and selection moved to trade-level PF, on
     a dataset a year shorter. Diamond Hands 4h: the walk-forward shuffle test
     failed at 0.0558 — see Trap 3, its in-sample strength did not survive out
     of sample.
   - **The buy-and-hold comparison**, stated bluntly: all three earned a third
     to a sixth of what holding Bitcoin earned over the same period. A strategy
     that underperforms doing nothing is not worth trading even if its p-value
     is pretty.
   - **The corrected threshold.** No combo clears 0.0100 on both p-values.
     DEVMA 12h's LOOKS REAL rests on the raw bar alone.
   - **The hold-out number** for DEVMA 12h, with the standing caveat: one look,
     no guarantee, must not be tuned against.
   - **A footnote** that the corrected bar is `0.05 / 5 = 0.0100` as of this
     session's ledger, that it tightens as more trials are recorded, and that
     each individual report file shows the bar as it stood when that run
     finished — which is why the DEVMA 12h report's "clears corrected: YES" is
     superseded here.

4. **Supersede the stale verdicts.** Add a line directly under the top scoreboard
   and under the DEVMA section noting those verdicts were produced under looser
   rules and are superseded by this section. A reader who stops at the
   scoreboard must not walk away with a stale LOOKS REAL.

# Step 3 — verify and commit

```bash
# The suite must still pass, untouched
uv run --with pytest --with-requirements requirements.txt pytest -q tests
```

Check by eye:

- `trials.csv` has the three `mode=full` rerun rows plus **one** new
  `mode=holdout` row for devma/12h — and no others.
- Distinct full-trial count is 5:
  ```bash
  python -c "import csv;print(len({(r['strategy'],r['timeframe']) for r in csv.DictReader(open('trials.csv')) if r['mode']=='full'}))"
  ```
- `ANALYSIS.md` tables render — count your pipes.

Commit on a branch and open a PR:

```bash
git checkout -b rerun-winners-honest-rules
git add ANALYSIS.md trials.csv specs/
git commit
gh pr create
```

`trials.csv` must be committed — it is the record that makes the correction mean
anything. `report_*.txt` and `holdout_*.txt` are gitignored and stay that way;
their numbers live in `ANALYSIS.md`. Leave `requests/rerun-winners.md` alone.

Put the headline in the PR description: one of the three old LOOKS REAL verdicts
survived, provisionally, and none clears the multiple-testing-corrected bar.

# Out of scope

Changing thresholds, metrics, funding rates or permutation logic to make a
strategy pass. Re-running the three combos. Taking a hold-out look at DEVMA 1d
or Diamond Hands 4h. Dashboard changes. The robustness batteries. Anything under
`adws/`. New strategies.
