# Next session

_Last handoff: 2026-08-07 — branch `main`_

## Where this stopped

Big session. The claudeSSSF agent factory was installed (`adws/`, run jobs
with `just sdlc "..."`), then used to make the pipeline statistically
honest: a reserved 12-month hold-out, a `trials.csv` multiple-testing
ledger with Bonferroni-corrected verdicts, trade-level profit factor with
a 10-trade floor, funding costs on shorts plus a `--direction` flag, and a
pytest suite with a lookahead tripwire. The three old LOOKS REAL verdicts
were then re-earned under the new rules: **devma 12h survived** (and its
one-shot hold-out look was excellent: +7.2% over a year where buy-and-hold
lost 44.9%); devma 1d and diamond_hands 4h are now NOT PROVEN. All merged
to main (PRs #4, #5). ANALYSIS.md "Reruns under the honest rules" has the
full table.

## Resume with

```bash
uv run --with pytest --with-requirements requirements.txt pytest -q tests
```

(28+ tests, ~3s, proves the environment works; the dashboard still needs
the full python path — see Watch out for)

## Next thing to do

1. Issue #1 — forward-test DEVMA 12h: log its daily position from
   dashboard.py so real out-of-sample evidence accumulates. The hold-out
   pass makes this worth doing properly now.
2. Issue #6 — small `adw_rerun.py` with code phases for long check.py
   runs, so multi-hour backtests don't have to live inside an agent phase.
3. Issue #2 — dashboard v2 (all-strategies grid); note the dashboard does
   not yet show the new verdict fields (corrected bar, Sharpe, direction).

## Open

- No PRs.
- Issues: #1 forward-test DEVMA (now the headline task) · #2 dashboard v2
  · #3 killzone filter (low priority) · #6 rerun ADW for long backtests.

## Watch out for

- **Do not re-tune devma because of the hold-out number.** The moment the
  strategy changes in response to `holdout_devma_12h.txt`, that number
  stops being out-of-sample. One look per strategy; it has been taken.
- `trials.csv` is append-only and drives the Bonferroni bar — never prune
  rows to make a verdict look better; every new strategy-timeframe run
  raises the bar for everyone.
- Old reports (`report.txt`, `report_diamond_hands.txt`) predate the
  per-strategy naming and the honest rules; trust ANALYSIS.md over them.
- Plain `python` on this machine lacks pandas. Dashboard:
  `"C:\Users\barth\AppData\Local\Python\pythoncore-3.14-64\python.exe" dashboard.py`
  Pipeline runs: `uv run --with-requirements requirements.txt python check.py ...`
- `combo` in strategies.py stays a documented negative result — don't fix.
- The SSSF trace visualizer is `just obs` → localhost:4600 (needs bun; if
  the port is busy, a stale instance from another project may hold it).
