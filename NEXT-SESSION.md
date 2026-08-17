# Next session

_Last handoff: 2026-08-17 — branch `main`_

## Where this stopped

One project: `signalchecker` (PR #11 merged). The `algoideas` and
`grok-trading-test` folders are gone. Plan: `docs/UNIFIED-ROADMAP.md`.
Nothing is uncommitted. Next build is Phase A: data hygiene + DEVMA 12h
`forward.py`. Do not re-tune DEVMA.

## Resume with

```
cd C:\ClaudeOS\Projects\signalchecker
uv run --with pytest --with-requirements requirements.txt pytest -q tests
```

62 tests, ~7s. Dashboard:
`"C:\Users\barth\AppData\Local\Python\pythoncore-3.14-64\python.exe" dashboard.py`
→ http://localhost:8787

## Next thing to do

1. Issue #1 / Phase A — `forward.py` + pin Binance + drop unclosed bars.
   Build ticket: `docs/UNIFIED-ROADMAP.md` Appendix C. 12h, both sides,
   `{vol_ma: 20, vol_run: 8}`. Not the stale daily long-only issue text.
2. Phase B — dashboard shows Bonferroni bar, Sharpe, direction, buy-and-hold.
   Pin `devma`+`12h` to 20/8. Partial issue #2. No sliders, no blend.
3. Phase C — shade the reserved 12 months on :8787; drag-recalculate
   must not write `trials.csv`. Reference: `docs/archive/grok-panel.html`.

## Open

- No PRs.
- Issues: #1 DEVMA 12h forward-test (headline) · #2 dashboard honesty
  fields (not the old grid/blend) · #3 killzone (parked ~3 months) ·
  #6 `adw_rerun.py` (only if a long check.py run is scheduled)

## Watch out for

- **Do not re-tune DEVMA** off `holdout_devma_12h.txt`. One look, taken.
- Do not run `check.py --holdout` for DEVMA again (no code guard yet —
  that lands in Phase A).
- `trials.csv` is append-only. Freeze new `mode=full` pairs until Phase G
  unless you open a PR that names the new hypothesis.
- `combo` stays a negative result. Don't fix it.
- Plain `python` lacks pandas. Use `uv run --with-requirements requirements.txt`.
- `just obs` → localhost:4600 for the factory trace UI (needs bun).
