# Next session

_Last handoff: 2026-08-21 — `main` at PR #14 and #16_

## Where this stopped

The idea-testing factory is on `main`. You describe an idea. The agent
asks clarifying questions (`ask_user_question`), writes a Strategy
class, runs pytest and `--quick` only. A full `check.py` run is a logged
trial and raises Bonferroni N.

PR #14 (liqproxy + `liq_flush`) and PR #16 (`break_retest`) are merged.
Both ideas were previewed only. Neither is on the ledger.

`liq_flush` — sell a big long-liquidation day, buy a big short-liquidation
day. The two legs are not alike. Selling long flushes is dead (forward
20-day return after those days averaged **+4.65%**). Buying short flushes
is the only half with anything in it and it still fails on trade count
and the walk-forward shuffle.

| Run | OOS PF | Trades | In-sample p | Walk-fwd p | Verdict |
|---|---|---|---|---|---|
| 1d both | 1.00 | 35 | 0.129 | 0.273 | NOT PROVEN |
| 1d long only | 1.17 | 20 | 0.032 | 0.636 | NOT PROVEN |
| 1d short only | 0.78 | 20 | 0.806 | 0.545 | NO EDGE |
| 12h both | 0.98 | 37 | 0.871 | 0.273 | NO EDGE |

`break_retest` — daily close breaks a swing high, then buy a later bar
that wicks into that frozen level and closes back above. Long only,
BTC 1d. Three exits on the grid: bearish structure break, take profit
at the break-candle high, hold 10 days.

| Gate | Result |
|---|---|
| Default (hold 10) | PF 0.92, −52%, 64 trades |
| Best in-sample | `break_high`, trade PF 11.3, p = 0.13 |
| Walk-forward | PF 0.86, −54%, 14 trades, p = 1.00 |
| Verdict | NO EDGE FOUND |

DEVMA forward-test (issue #1) stays parked.

## Resume with

```
cd C:\ClaudeOS\Projects\signalchecker
uv run --with pytest --with-requirements requirements.txt pytest -q tests
uv run --with-requirements requirements.txt python ledger.py status
```

114 tests. Ledger: N=5, bar=0.0100. Contract: `ADDING-AN-IDEA.md`.

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
- `data/BTC-USDT_liqproxy_1d.csv` is a stale cache from the first cut of
  PR #14. Nothing reads it. Safe to delete.

## Watch out for

- Do not run a full `check.py` unless asked to log it. `--quick` does
  not write `trials.csv`.
- Do not re-tune existing examples off hold-out numbers.
- `combo`, `liq_flush`, and `break_retest` stay negative. Do not "fix"
  them into a pass.
- Do not call a pre-#13 mental model of `data.update` — refreshes now
  pin Binance, drop unclosed bars, and append only.
- `permute.py` shuffles **every** non-OHLC column with its bar, not
  just Volume. Before #14 an extra column stayed in real time order on
  shuffled data.
- A `liq_flush`-style verdict is fragile. Five dropped bars moved the 1d
  run from NO EDGE to NOT PROVEN, because with ~5 folds and ~35 trades
  the fold boundaries matter that much. Read those verdicts as a range,
  not a number.
- Plain `python` lacks pandas. Use `uv run --with-requirements requirements.txt`.
