# Next session

_Last handoff: 2026-08-07 — branch `main`_

## Where this stopped

A finished, working pipeline that answers "is this trading signal real
or luck" (backtest → shuffle test → walk-forward → shuffle test), with
8 strategies ported from old TradingView scripts, robustness batteries,
and a live local dashboard. Everything is committed and pushed; the
project just moved here from C:\Users\barth\projects\signal-check
(old path deleted — this is the only copy). Headline findings are in
ANALYSIS.md and ROBUSTNESS.md: DEVMA passed everything (12h and 1d),
Diamond Hands passed on 4h, everything else failed honestly.

## Resume with

```bash
"C:\Users\barth\AppData\Local\Python\pythoncore-3.14-64\python.exe" dashboard.py
```

(then open http://localhost:8787 — note: plain `python` is a different
install without pandas; always use the full path above)

## Next thing to do

1. Issue #1 — start logging DEVMA's daily position from the dashboard
   so the "is the edge fading?" question accumulates forward evidence.
2. Issue #2 — pick one dashboard v2 feature (all-strategies grid is
   the most useful) and add it to dashboard.py / dashboard.html.
3. Nothing else is urgent; the analysis phase is complete.

## Open

- No PRs.
- Issues: #1 forward-test DEVMA's fading edge · #2 dashboard v2
  features · #3 killzone sessions as a filter (low priority).

## Watch out for

- `report.txt` (no suffix) is the original Diamond Hands 12h run from
  before reports got per-strategy names; newer runs write
  `report_<strategy>_<timeframe>.txt`.
- `combo` in strategies.py is a documented *negative* result (merging
  the two winners dilutes them) — don't "fix" it; ANALYSIS.md explains.
- First dashboard load of an uncached asset/timeframe downloads full
  history from Binance (up to a minute); cached combos are instant.
- data/ is gitignored on purpose (regenerable, and keeps the repo
  small); a fresh clone rebuilds it on first use.
