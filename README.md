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

The result prints to the screen and is saved to
`report_<strategy>_<timeframe>.txt`. It ends with a verdict: **LOOKS REAL**,
**NOT PROVEN**, or **NO EDGE FOUND**.

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

`strategies.py` holds 8 strategies, each with its own parameter grid. One is
"sweep reversal" (`DiamondHands`), a stop-run pattern ported from an old
TradingView Pine Script: price dips below the recent low but closes back
above it, while the longer trend agrees. The other seven are variations on
trend-following and breakout ideas.

All 8 were run through the pipeline above, across multiple assets and
timeframes. See `ANALYSIS.md` for the per-strategy results and `ROBUSTNESS.md`
for how they hold up out of sample and on other markets.

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
- `strategies.py` — the 8 strategies being tested, each with its parameter grid
- `permute.py` — builds the shuffled price series for the honesty tests
- `check.py` — runs the four stages and prints the verdict, saving
  `report_<strategy>_<timeframe>.txt`
- `robustness.py` / `robustness_devma.py` — re-run the pipeline across
  multiple assets and timeframes to check a strategy isn't a one-market fluke
- `assets_devma.py` / `equities_devma.py` — extend that robustness check to
  more crypto assets and to equities/gold

## Credit where due

- Backtest engine: [backtesting.py](https://github.com/kernc/backtesting.py)
  (handles fills, costs and accounting so those aren't my bugs)
- Permutation method: Timothy Masters' bar-permutation test, as implemented
  by [neurotrader888/mcpt](https://github.com/neurotrader888/mcpt)

## Honest limitations

- Tested across 8 crypto majors, four timeframes (1h/4h/12h/1d), and a
  handful of equities and gold — but that's still a small slice of markets a
  real edge would need to survive.
- Slippage is a flat estimate; live trading is messier.
- Passing all four stages still isn't proof. Markets change. It just means
  the idea earned the right to be paper-traded.
