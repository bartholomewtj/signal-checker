# Re-earn the winners' verdicts under the honest rules

The pre-fix ANALYSIS.md verdicts (DEVMA LOOKS REAL on 12h and 1d, Diamond
Hands LOOKS REAL on 4h) predate the hold-out split, trade-level profit
factor, short funding costs, and the Bonferroni-corrected threshold. Re-run
those three strategy-timeframe combos through the full pipeline under the
new rules and document what survives.

Where: run `check.py` (no code changes to it unless a rerun exposes a real
bug); update ANALYSIS.md; trials.csv grows by itself.

## What to run

For each of: devma 12h, devma 1d, diamond_hands 4h —

    python check.py --strategy devma --timeframe 12h \
        --insample-perms 400 --wf-perms 250

(same flags for the other two; use the project's working python). The
permutation counts are deliberate: with ~12 distinct trials recorded, the
Bonferroni bar is about 0.004, and the smallest p-value N shuffles can
produce is 1/(N+1) — 100 walk-forward shuffles bottom out at 0.0099 and
could never clear the corrected bar. 250 wf / 400 in-sample shuffles make
clearing it possible. These runs are slow (expect roughly 30–60 minutes
each); run them sequentially and be patient — do not reduce the counts to
save time.

## Hold-out discipline

Only for combos whose full rerun still says LOOKS REAL at the raw 0.05 bar:
take the single `--holdout` look and record it. Combos that fail the rerun
do not get a hold-out look — the one-shot look is only spent on surviving
candidates.

## Document

Add a dated section to ANALYSIS.md ("Reruns under the honest rules") with a
table: strategy, timeframe, old verdict, new verdict, wf trade-level PF,
Sharpe, buy-and-hold comparison, p-values vs raw and corrected bars,
direction mode, and the hold-out result where taken. State plainly which of
the old LOOKS REAL verdicts survived and which died, and why (funding costs
on shorts, stricter metric, corrected threshold, or reserved hold-out
shrinking the data). Plain language, same tone as the existing file.

Done means: three new full-run rows in trials.csv, report files for each
combo, ANALYSIS.md carries the new section, and the pytest suite still
passes untouched.

Out of scope: changing thresholds, metrics, funding rates, or permutation
logic to make a strategy pass; dashboard changes; robustness batteries;
adws/. If a rerun crashes, fixing the crash is in scope; tuning results is
not.
