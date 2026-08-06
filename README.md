# signal-check

A small, honest backtesting pipeline. You give it a trading signal; it tells
you whether the signal's performance looks real or looks like luck.

Most backtests lie by accident: they test on the same data the idea was tuned
on, they ignore costs, and they never ask "would random noise have scored
this well?" This pipeline asks exactly that.

## How to run it

```
pip install -r requirements.txt
python data.py      # downloads ~9 years of Bitcoin 12-hour candles (once)
python check.py     # full check, roughly 10 minutes
python check.py --quick   # rough answer in about a minute
```

The result prints to the screen and is saved to `report.txt`. It ends with a
verdict: **LOOKS REAL**, **NOT PROVEN**, or **NO EDGE FOUND**.

## What it actually does

Four stages, each one harder to fool than the last:

1. **Full backtest.** Runs the strategy over all the data with realistic
   costs (0.15% commission per side plus 0.05% slippage, fills at the next
   bar's open, no leverage). This is the flattering number — it proves
   nothing by itself.

2. **In-sample honesty test.** Shuffles the price history into hundreds of
   fake-but-statistically-identical versions (same daily moves, random
   order — a *Monte Carlo permutation test*), and re-tunes the strategy on
   each one. If tuned-on-noise scores as well as tuned-on-reality, the
   backtest number was just curve-fitting.

3. **Walk-forward.** Repeatedly picks the best settings using only past
   data, then trades the *next* six months blind, and stitches the blind
   segments together. This is the closest a backtest gets to "what would I
   actually have earned."

4. **Walk-forward honesty test.** The shuffle test applied to the whole
   walk-forward process. Hardest test in the pipeline.

The verdict requires: money made out of sample, a decent number of trades,
and both shuffle tests showing the real data beats noise (p < 0.05).

## The signal under test

`strategy.py` holds a "sweep reversal" ported from an old TradingView Pine
Script: price dips below the recent low but closes back above it (a stop
run), while the longer trend agrees. Swap in your own signal by editing
that file — anything that can be expressed as buy/sell rules on
open/high/low/close works.

## Dashboard

```
python dashboard.py
```

Opens a live dashboard at http://localhost:8787: pick any strategy,
asset and timeframe; see the price chart with every trade marked, the
equity curve, headline stats, what position the strategy holds right
now, and the honesty-test verdicts. "Update data" pulls just the newest
candles from the exchange; the auto-refresh checkbox re-runs every
minute.

## Files

- `data.py` — downloads and caches price candles (Binance via ccxt)
- `strategy.py` — the signal being tested, plus its parameter grid
- `permute.py` — builds the shuffled price series for the honesty tests
- `check.py` — runs the four stages and prints the verdict

## Credit where due

- Backtest engine: [backtesting.py](https://github.com/kernc/backtesting.py)
  (handles fills, costs and accounting so those aren't my bugs)
- Permutation method: Timothy Masters' bar-permutation test, as implemented
  by [neurotrader888/mcpt](https://github.com/neurotrader888/mcpt)

## Honest limitations

- One asset (Bitcoin), one bar size (12h). A real edge should survive on
  more than one.
- Slippage is a flat estimate; live trading is messier.
- Passing all four stages still isn't proof. Markets change. It just means
  the idea earned the right to be paper-traded.
