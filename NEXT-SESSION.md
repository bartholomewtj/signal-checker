# Next session

_Last handoff: 2026-08-17 — `main` at PR #13 (idea factory)_

## Where this stopped

The idea-testing factory is on `main`. You describe an idea. The agent
asks clarifying questions (`ask_user_question`), writes a Strategy
class, runs pytest and `--quick` only. A full `check.py` run is a logged
trial and raises Bonferroni N.

DEVMA forward-test (issue #1) stays parked. No strategy-specific work
unless you bring an idea.

## Resume with

```
cd C:\ClaudeOS\Projects\signalchecker
uv run --with pytest --with-requirements requirements.txt pytest -q tests
uv run --with-requirements requirements.txt python ledger.py status
```

76 tests. Ledger: N=5, bar=0.0100. Contract: `ADDING-AN-IDEA.md`.

## Next thing to do

1. Bring a new idea. Agent follows `ADDING-AN-IDEA.md` — questions first,
   then a class, then `--quick` only. Do not log unless you say so.
2. Later: dashboard reads `trials.csv` generally (no strategy pins).
3. Later: generic paper-trade logger, only after some idea earns LOOKS REAL.

## Open

- No PRs.
- Issues: #1 DEVMA forward-test **parked** · #2 dashboard honesty
  (not grid/blend/sliders) · #3 killzone parked · #6 `adw_rerun.py`
  only if a long check.py is scheduled.

## Watch out for

- Do not run a full `check.py` unless asked to log it. `--quick` does
  not write `trials.csv`.
- Do not re-tune existing examples off hold-out numbers.
- `combo` stays a negative result.
- Do not call a pre-#13 mental model of `data.update` — refreshes now
  pin Binance, drop unclosed bars, and append only.
- Plain `python` lacks pandas. Use `uv run --with-requirements requirements.txt`.
