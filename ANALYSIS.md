# Test results: the TVscripts strategies

Six strategies were extracted from the original TradingView indicator repo
and run through the full four-stage honesty pipeline (backtest with real
costs → in-sample shuffle test → walk-forward → walk-forward shuffle test).

Costs in all tests: 0.15% commission per side + 0.05% slippage, fills at
next bar open, no leverage. 12-hour strategies tested on Bitcoin
2017–2026; the two intraday level strategies on 1-hour bars 2021–2026.

## Scoreboard

| Strategy | From indicator | Full backtest | Out-of-sample PF | OOS trades | p (in-sample) | p (walk-fwd) | Verdict |
|---|---|---|---|---|---|---|---|
| structure_break | Structure break + Alerts | +8.5% | 1.001 | 386 | **0.005** | 0.059 | NOT PROVEN (3/4) |
| diamond_hands | Diamond Hands strategy | +33.6% | 1.030 | 23 | 0.413 | 0.248 | NO EDGE (1/4) |
| hl_band_breakout | HL Bands + Alerts | −72.2% | 0.904 | 725 | **0.015** | 0.287 | NOT PROVEN (2/4) |
| trend_step | Trend Shifts / Trend Classifier | −99.2% | 0.909 | 963 | 0.075 | 0.198 | NO EDGE (1/4) |
| open_rejection | Killzones + Opens | −100% | 0.880 | 594 | 0.941 | 0.902 | NO EDGE (1/4) |
| vwap_rejection | VWAP daily anchor | −100% | 0.842 | 2161 | 1.000 | 0.980 | NO EDGE (1/4) |

PF = profit factor (gross gains ÷ gross losses; above 1.0 = profitable).
p = chance that shuffled, pattern-free price data scores as well as the
real data. Low p means the strategy is reading something real.

## Rerun: Diamond Hands on 4-hour bars (2026-08-07)

Rerunning the sweep reversal on 4h bars (same costs, same pipeline,
walk-forward windows scaled to match) produced the first full pass:

| | 12h | 4h |
|---|---|---|
| Full backtest | +33.6% | +1094.9% (buy & hold +1396.8%) |
| Out-of-sample return | +41.7% | +119.3% |
| Out-of-sample PF | 1.030 | 1.085 |
| Out-of-sample trades | 23 | 42 |
| p in-sample | 0.413 | **0.025** |
| p walk-forward | 0.248 | **0.030** |
| Verdict | NO EDGE | **LOOKS REAL (4/4)** |

Caveat that must travel with this result: the 4h timeframe was the
*second* one tried for this signal. Trying configurations until one
passes is itself a form of overfitting — with two attempts, the honest
reading of p ≈ 0.03 is closer to p ≈ 0.06. And the fold results are
lumpy: several folds had 0–3 trades. So: the strongest evidence produced
in this project, worth pursuing — not yet worth funding. The right next
tests, on data this pipeline has never touched: the same signal on
another asset (e.g. ETH), and paper trading forward.

## What the numbers say

**Nothing here is tradeable as-is.** No strategy passed all four checks.

**But the breakout family reads something real.** The most interesting
result is `structure_break`: its in-sample p-value of 0.005 means fewer
than 1 in 200 shuffled price histories scored as well — the pattern
(single-bar breaks of swing highs/lows continuing) genuinely exists in
Bitcoin's price series. `hl_band_breakout` shows the same fingerprint
(p = 0.015). The problem is economics, not statistics: out of sample,
structure_break's profit factor is 1.001 — the real pattern earns almost
exactly what trading costs consume. A real signal, fully eaten by fees.

**The mean-reversion family reads worse than nothing.** `open_rejection`
and `vwap_rejection` scored p ≈ 0.9–1.0: shuffled data was consistently
*better* for them than real data. That's informative — real Bitcoin
1-hour prices trend more than random noise does, so fading a move back
through a level (betting on reversion) is systematically the wrong side.
The rejection alerts aren't just unprofitable, they're anti-signal.

**The trend-step churns.** The sticky rising/falling midband flips far
too often (1,676 trades), and every flip pays the toll. Its borderline
in-sample p (0.075) hints at weak trend structure, but after costs it
lost 99%.

**Diamond Hands stays the best *idea*, on the worst *evidence*.** It's
the only strategy whose out-of-sample result made money (+41.7%, PF
1.03), but with just 23 trades and shuffle tests that can't tell it from
luck. Too selective to prove, too plausible to dismiss.

## Not tested, and why

- **Volume heatmap** and **MTF close times** — display tools; they
  contain no entry/exit rules to test.
- **Killzone session windows** — a session filter isn't a strategy by
  itself; it could be tested later as a *filter* on another signal.
- The rejection indicators gave alerts but no exits; the timed exit
  (12/24/48 bars, optimizer's choice) is this port's addition. A
  different exit could change their numbers, but not their p-values —
  those measure the entry signal's information content, and it's absent.

## Honest takeaways

1. The original alert-based tools were used for *discretionary* trading.
   Tested mechanically, none of them survives costs. Any value they had
   came from the human filtering the alerts, not from the alerts.
2. The one lead worth pursuing: breakout continuation on 12h bars is
   statistically real. Ways it could clear costs: trade it less often
   (higher timeframe, stricter filter — e.g. only breaks on abnormal
   volume, which the volume heatmap already measures), or cheaper
   execution (maker fees are ~0.02% on major venues vs the 0.15% taker
   rate assumed here).
3. Every one of these conclusions cost ~10 minutes of compute. The same
   lessons from live trading would have cost the account.

Full per-strategy reports: `report_<strategy>.txt` (regenerate with
`python check.py --strategy <name>`).
