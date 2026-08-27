# signal-check

Honest backtests for trading ideas. You describe a rule. An agent turns
it into a Strategy class. The pipeline tells you whether the backtest
looks real or looks like luck. Most ideas fail. That is the product
working.

## How an idea gets tested

```
you describe the idea
        ↓
agent asks clarifying questions, then writes a class in strategies.py
        ↓
just test                (lookahead runs automatically)
        ↓
just check X T
        (verdict page opens, not logged)
        ↓
you read it. if you want it on the ledger:
just check-full X T
        (full shuffles, appends mode=full, N goes up)
```

The agent must ask you questions before writing any class. Do not run
a full `check.py` unless you say to log it.

## How to run it

From `C:\ClaudeOS\Projects\signalchecker`:

```
just check devma 12h
```

About a minute. Verdict page opens when it finishes. Does **not** write
`trials.csv`. Other recipes:

```
just check-full devma 12h   # logged trial, tens of minutes, N goes up
just visual                 # reopen last_run.html
just test
just ledger
just dash                   # http://localhost:8787
just log-devma              # append today's DEVMA long-only 1d position
```

`just log-devma` writes one line to `forward/devma_lo_1d.csv`. It is not a ledger row and it does not burn the holdout year. A second run on the same candle prints `already logged` and writes nothing.

`--quick` / `--preview` is display only. A full run is a logged trial.
`just visual` reopens the last page without running anything. `--no-open`
on check.py writes `last_run.html` without opening it.

Dashboard (`just dash`) is a live chart of one strategy, plus an
all-strategies overview (current position and last signal date on
BTC/USDT 1d). Those runs are not ledger rows. Charts use the vendored
Lightweight Charts file (no CDN). Click an overview row to open that
strategy in the chart.

Named idea already in the registry (no LLM):

```
python refine.py questions --idea "devma on bitcoin"
python refine.py spec --idea "devma on bitcoin" --answers answers.json
```

That prints a spec. It does not run the backtest and it does not write
`trials.csv`.

A `--holdout` look is once per `(strategy, timeframe)`. A second look is
refused unless you pass `--i-know-this-burns-the-holdout`.

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
with `mode=full`. Today N = 5, bar = 0.0100. Each new pair on a full run
raises N.

The last 12 calendar months are a reserved hold-out (`data.split_holdout`).
Stages 1–4 never see them.

Crypto refreshes pin Binance, drop the unclosed current bar, and append
new closed timestamps only.

## Liquidation data

`liqproxy.py` builds a liquidation estimate for any of the crypto symbols,
cached hourly at `data/<SYMBOL>_liqproxy_1h.csv`:

```
python liqproxy.py              # BTC/USDT
python liqproxy.py ETH/USDT
```

Refreshes are append-only, the same as price bars: hours already cached
are never re-fetched or rewritten.

Real liquidation history is not free any more, so this estimates forced
deleveraging from Binance open interest instead: open interest falling
while price falls means longs are being flushed, falling while price rises
means shorts are. Coverage starts when Binance starts publishing open
interest for the symbol - 2020-09 for BTC, 2021-12 for the rest.

Hourly is the stored resolution because it divides evenly into 4h, 12h and
1d, so the columns line up with the price bars of any run. A bar the cache
cannot fully cover is dropped rather than half-counted.

A strategy that sets `NEEDS_LIQ = True` gets `LongLiq` and `ShortLiq`
columns attached by `check.py` and by the dashboard, and the frame is
trimmed to the bars the proxy covers. `permute.py` shuffles those columns
along with their bar, so the honesty tests destroy the signal the same way
they destroy a price pattern.

It is a proxy, not a liquidation print - open interest also falls when
traders close voluntarily. Judge results accordingly.

## Existing examples

The ten registry classes are examples the pipeline already judged.
`combo` is a documented negative — do not "fix" it. `liq_flush` and
`break_retest` have previews only, no logged trial; do not "fix"
either into a pass.

## Files

- `check.py` — four stages, verdict, `trials.csv`
- `strategies.py` — named ideas (`REGISTRY`) plus an unregistered template
- `data.py` — Binance via ccxt, Yahoo for ETFs
- `liqproxy.py` — hourly liquidation proxy from Binance open interest
- `permute.py` — Masters bar-permutation
- `ledger.py` — `status` / `list`
- `dashboard.py` / `dashboard.html` — local UI
- `visual.py` — `last_run.html` after a check.py run
- `refine.py` — named idea → spec
- `vendor/lightweight-charts.standalone.production.js` — chart library
- `ARCHIVE.md` — what stayed off GitHub

## Credit

- Backtest engine: [backtesting.py](https://github.com/kernc/backtesting.py)
- Permutation: Timothy Masters, via [neurotrader888/mcpt](https://github.com/neurotrader888/mcpt)
