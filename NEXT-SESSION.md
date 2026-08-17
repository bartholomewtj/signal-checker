# Next session

_Last handoff: 2026-08-17 — branch `idea-factory` (open this PR)_

## Where this stopped

The product is the idea-testing factory, not a specific strategy.
DEVMA forward-test (old Phase A / issue #1) is parked.

Intake: you describe an idea → agent asks clarifying questions
(`ask_user_question`) → writes a Strategy class → `--quick` (not logged)
→ you decide whether to log a full run.

## Resume with

```
cd C:\ClaudeOS\Projects\signalchecker
uv run --with pytest --with-requirements requirements.txt pytest -q tests
uv run --with-requirements requirements.txt python ledger.py status
```

## Next thing to do

1. Merge this PR if it is still open.
2. Bring a new idea. Agent follows `ADDING-AN-IDEA.md` — questions first,
   then a class, then `--quick` only.
3. Later, not now: dashboard reads `trials.csv` generally (no strategy
   pins). Generic paper-trade logger only after some idea earns LOOKS REAL.

## Open

- No strategy-specific work.
- Issues: #1 DEVMA forward-test **parked** · #2 dashboard honesty
  (still no sliders/blend) · #3 killzone parked · #6 `adw_rerun.py`
  only if a long check.py is scheduled.

## Watch out for

- Do not run a full `check.py` unless asked to log it. `--quick` does
  not write `trials.csv`.
- Do not re-tune existing examples off hold-out numbers.
- `combo` stays a negative result.
- Plain `python` lacks pandas. Use `uv run --with-requirements requirements.txt`.
