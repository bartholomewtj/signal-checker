# Next session

_Last handoff: 2026-08-20 — PR #14 open (liquidation data + `liq_flush`)_

## Where this stopped

The idea-testing factory is on `main`. You describe an idea. The agent
asks clarifying questions (`ask_user_question`), writes a Strategy
class, runs pytest and `--quick` only. A full `check.py` run is a logged
trial and raises Bonferroni N.

PR #14 adds the first non-price data source. `liqproxy.py` estimates
liquidations from Binance open interest, cached hourly per symbol, and
any strategy setting `NEEDS_LIQ = True` gets `LongLiq` / `ShortLiq`
columns. See the README section and `ADDING-AN-IDEA.md`.

The idea it was built for, `liq_flush` — sell a big long-liquidation day,
buy a big short-liquidation day — did not survive. Previews only, nothing
logged:

| Run | OOS PF | Trades | In-sample p | Walk-fwd p | Verdict |
|---|---|---|---|---|---|
| 1d both | 1.00 | 35 | 0.129 | 0.273 | NOT PROVEN |
| 1d long only | 1.17 | 20 | 0.032 | 0.636 | NOT PROVEN |
| 1d short only | 0.78 | 20 | 0.806 | 0.545 | NO EDGE |
| 12h both | 0.98 | 37 | 0.871 | 0.273 | NO EDGE |

The two legs are not alike. Selling long-liquidation flushes is dead —
noise beat it 80% of the time, and the raw forward 20-day return after
one of those days averaged **+4.65%**, so it was shorting into an up move.
Buying short-liquidation flushes is the only half with anything in it and
it still fails on trade count and the walk-forward shuffle.

DEVMA forward-test (issue #1) stays parked.

## Resume with

```
cd C:\ClaudeOS\Projects\signalchecker
uv run --with pytest --with-requirements requirements.txt pytest -q tests
uv run --with-requirements requirements.txt python ledger.py status
```

103 tests. Ledger: N=5, bar=0.0100. Contract: `ADDING-AN-IDEA.md`.

## Next thing to do

1. Merge or close PR #14. Nothing depends on it staying open.
2. Bring a new idea. Agent follows `ADDING-AN-IDEA.md` — questions first,
   then a class, then `--quick` only. Do not log unless you say so.
3. Later: dashboard reads `trials.csv` generally (no strategy pins).
4. Later: generic paper-trade logger, only after some idea earns LOOKS REAL.

## Open

- PR #14 — liquidation data + `liq_flush`.
- Issues: #1 DEVMA forward-test **parked** · #2 dashboard honesty
  (not grid/blend/sliders) · #3 killzone parked · #6 `adw_rerun.py`
  only if a long check.py is scheduled.
- `data/BTC-USDT_liqproxy_1d.csv` is a stale cache from the first cut of
  PR #14. Nothing reads it. Safe to delete.

## Watch out for

- Do not run a full `check.py` unless asked to log it. `--quick` does
  not write `trials.csv`.
- Do not re-tune existing examples off hold-out numbers.
- `combo` stays a negative result. `liq_flush` is heading the same way —
  do not "fix" it into a pass.
- Do not call a pre-#13 mental model of `data.update` — refreshes now
  pin Binance, drop unclosed bars, and append only.
- `permute.py` now shuffles **every** non-OHLC column with its bar, not
  just Volume. Before #14 an extra column stayed in real time order on
  shuffled data, which would have made the honesty tests trivial to pass
  for anything using one. No existing verdict changes; nothing else used
  extra columns.
- A `liq_flush`-style verdict is fragile. Five dropped bars moved the 1d
  run from NO EDGE to NOT PROVEN, because with ~5 folds and ~35 trades
  the fold boundaries matter that much. Read those verdicts as a range,
  not a number.
- Plain `python` lacks pandas. Use `uv run --with-requirements requirements.txt`.
