# signal-check

Honest backtests for trading ideas. You give it a rule. It tells you
whether the backtest looks real or looks like luck. Most ideas fail.
That is the product working.

This is the one trading-validation project. The old `algoideas` spec and
the `grok-trading-test` prototype have been absorbed here.

## How to run it

From `C:\ClaudeOS\Projects\signalchecker`:

```
uv run --with-requirements requirements.txt python check.py --strategy devma --timeframe 12h
uv run --with pytest --with-requirements requirements.txt pytest -q tests
```

`--quick` is a rough answer in about a minute. A full run is tens of minutes
(defaults: 200 in-sample shuffles + 100 walk-forward).

Dashboard:

```
python dashboard.py
```

http://localhost:8787. Pick a strategy, asset, and timeframe. Charts use the
vendored Lightweight Charts file (no CDN).

Turn a named idea into a spec (no LLM):

```
python refine.py questions --idea "devma on bitcoin"
python refine.py spec --idea "devma on bitcoin" --answers answers.json
```

That prints `{"strategy": "devma", "symbol": "BTC/USDT", ...}`. It does not
run the backtest and it does not write `trials.csv`.

Do **not** run `check.py --holdout` for DEVMA again. That one look is taken
(`holdout_devma_12h.txt`). A second look burns the reserved year.

## What a run does

Four stages, each harder to fool than the last (`check.py`):

1. **Full backtest** with costs (0.15% commission + 0.05% slippage per side,
   next-bar-open fills, 1 bp / 8h funding on shorts).
2. **In-sample honesty** — re-tune on hundreds of shuffled bar histories
   (Masters permutation). If noise scores as well as reality, it was luck.
3. **Walk-forward** — pick settings on the past, trade the next six months
   blind, stitch the blind segments.
4. **Walk-forward honesty** — the shuffle test on the whole walk-forward.

Verdict: **LOOKS REAL**, **NOT PROVEN**, or **NO EDGE FOUND**. It needs money
made out of sample, enough trades, and both shuffle tests beating noise
(raw p < 0.05). `trials.csv` is the append-only ledger. The live bar is
Bonferroni: `0.05 / N` where N is distinct `(strategy, timeframe)` pairs
with `mode=full`. Today N = 5, bar = 0.0100.

The last 12 calendar months are a reserved hold-out (`data.split_holdout`).
Stages 1–4 never see them.

## What survived

DEVMA on 12h BTC/USDT is the only LOOKS REAL under the honest rules, and
only at the raw 0.05 bar (provisional vs Bonferroni 0.0100). Its one-shot
hold-out used `{vol_ma: 20, vol_run: 8}`, both sides. **Do not re-tune
DEVMA off that number.** `combo` is a documented negative — do not "fix" it.

See `ANALYSIS.md` and `ROBUSTNESS.md`. The unification plan and next slices
(forward-test logger, dashboard honesty, CPCV/DSR later) are in
`docs/UNIFIED-ROADMAP.md`. The deferred v4 spec is `docs/algoideas-v4-spec.md`.

## Files

- `check.py` — four stages, verdict, `trials.csv`
- `strategies.py` — eight named ideas (`REGISTRY`)
- `data.py` — Binance via ccxt, Yahoo for ETFs
- `permute.py` — Masters bar-permutation
- `dashboard.py` / `dashboard.html` — local UI
- `refine.py` — named idea → spec
- `docs/UNIFIED-ROADMAP.md` — one-project plan
- `vendor/lightweight-charts.standalone.production.js` — chart library

## Credit

- Backtest engine: [backtesting.py](https://github.com/kernc/backtesting.py)
- Permutation: Timothy Masters, via [neurotrader888/mcpt](https://github.com/neurotrader888/mcpt)
