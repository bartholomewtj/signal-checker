# Next session

_Last handoff: 2026-08-17 — branch `unify-one-project`_

## Where this stopped

algoideas and grok-trading-test were absorbed into this repo and those
folders were deleted. Living plan: `docs/UNIFIED-ROADMAP.md`. Next build
slice is still **Phase A / PR 1**: data hygiene + DEVMA 12h `forward.py`
(pinned `{vol_ma: 20, vol_run: 8}`, both sides). Do not re-tune DEVMA.

Honest-rules history: **devma 12h survived** (hold-out +7.2% vs buy-and-hold
−44.9%). devma 1d and diamond_hands 4h are NOT PROVEN. `combo` stays a
negative result.

## Resume with

```bash
uv run --with pytest --with-requirements requirements.txt pytest -q tests
```

(28+ tests, ~3s, proves the environment works; the dashboard still needs
the full python path — see Watch out for)

## Next thing to do

1. Issue #1 / Phase A — `forward.py` + pin Binance + drop unclosed bars.
   Spec in `docs/UNIFIED-ROADMAP.md` Appendix C. Not daily long-only:
   12h, both sides, params 20/8.
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
