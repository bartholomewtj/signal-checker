# Test results: the TVscripts strategies

Six strategies were extracted from the original TradingView indicator repo
and run through the full four-stage honesty pipeline (backtest with real
costs → in-sample shuffle test → walk-forward → walk-forward shuffle test).

Costs in all tests: 0.15% commission per side + 0.05% slippage, fills at
next bar open, no leverage. 12-hour strategies tested on Bitcoin
2017–2026; the two intraday level strategies on 1-hour bars 2021–2026.

## Scoreboard

*The DEVMA and Diamond Hands 4h "LOOKS REAL" verdicts below and in the
"Added later: DEVMA" section were produced under looser rules — no
hold-out split, per-bar profit factor instead of trade-level, no funding
cost on shorts, no multiple-testing correction. They are superseded by
"Reruns under the honest rules" further down. Read that section before
trusting any LOOKS REAL on this page.*

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

## Added later: DEVMA (v6 script, tested 2026-08-07)

The newer "DEVMA strat NR 18/03" combines the 3D HL-band breakout and
structure breaks with a 2D trend-step and a volatility gate (enter only
while smoothed volatility is rising; exit signals only honoured while it
falls). Port notes: BitMEX BVOL7D replaced with locally computed 7-day
realized volatility; position size capped at 100% equity (the original's
1%-risk sizing could lever up unboundedly); only the volatility-filter
parameters were optimized (band timeframes stayed 2D/3D as authored).

Tested on both timeframes as requested — both passed all four checks:

| | 12h | 1d |
|---|---|---|
| Full backtest | +872% (b&h +1251%) | +894% (b&h +1231%) |
| Out-of-sample return | +208% | +240% |
| Out-of-sample PF | 1.052 | 1.070 |
| Out-of-sample trades | 204 | 158 |
| p in-sample / walk-forward | 0.005 / 0.010 | 0.015 / 0.010 |
| Max drawdown (full) | −66% | −53% |
| Verdict | **LOOKS REAL (4/4)** | **LOOKS REAL (4/4)** |

This is stronger evidence than the Diamond Hands 4h pass: an order of
magnitude more out-of-sample trades, lower p-values, and two timeframes
specified up front rather than found by searching. One honest worry from
the fold tables: on both timeframes most of the out-of-sample profit
came from 2019–2021; the 2023–2025 folds hover at or below breakeven
(daily: 0.84, 0.93, 0.84, 0.97, 0.91 before the last fold's 1.13). The
edge as measured is real but looks thinner in recent years. And the
tested strategy is the port — realized-vol gate, capped sizing — not
literally the leveraged BVOL original.

**Both LOOKS REAL verdicts above were re-earned under stricter rules —
see the next section.** Only one survives, and only partially.

## Reruns under the honest rules (2026-08-07)

Since the two DEVMA passes and the Diamond Hands 4h pass above were
judged, the pipeline gained four things: a 12-month hold-out that no
optimisation or walk-forward stage ever sees; trade-level profit factor
(gross trade profit ÷ gross trade loss, with a 10-trade minimum floor per
window) in place of per-bar equity profit factor as the selection score;
a funding cost of 0.01% per 8 hours charged against every bar a short
position is held, in every stage including the shuffle tests; and a
Bonferroni-corrected significance bar that accounts for how many
strategy/timeframe combinations have been tried in total, not just this
one. None of the three old LOOKS REAL verdicts were judged under any of
that. All three were re-run, using the same data windows and walk-forward
settings as the original runs so the comparison is apples to apples, but
with 400 in-sample and 250 walk-forward shuffles (up from 200/100) so the
p-values have enough resolution to test against the corrected bar.

**One of the three survived, and only provisionally. Two died.**

| | DEVMA 12h | DEVMA 1d | Diamond Hands 4h |
|---|---|---|---|
| Old verdict | LOOKS REAL (4/4) | LOOKS REAL (4/4) | LOOKS REAL (4/4) |
| New verdict | **LOOKS REAL (4/4), provisional** | NOT PROVEN (2/4) | NOT PROVEN (3/4) |
| Direction mode | both | both | both |
| Data used / reserved | 5,793 / 730 bars | 2,897 / 365 bars | 17,367 / 2,190 bars |
| OOS return | +231.7% | +150.2% | +233.7% |
| Buy & hold, same period | **+767.4%** | **+892.8%** | **+767.5%** |
| OOS trade-level PF | 1.061 | 1.059 | 1.065 |
| Sharpe (annualised) | 0.44 | 0.33 | 0.63 |
| OOS trades | 169 | 132 | 44 |
| p in-sample | 0.0399 | 0.0698 | 0.0075 |
| p walk-forward | 0.0159 | 0.0598 | 0.0558 |
| Clears raw 0.05? | in-sample yes, wf yes | no | in-sample yes, wf no |
| Clears corrected 0.0100?* | **no** | no | no |
| Hold-out result | +7.2% return, PF 1.208, Sharpe 0.23, 30 trades, buy&hold −44.9% | — (not earned) | — (not earned) |

\* The corrected bar is `0.05 / 5 = 0.0100`, based on 5 distinct
strategy/timeframe combinations recorded in `trials.csv` as of this
session (up from 2 before these reruns). It tightens as more trials are
recorded. Each individual `report_*.txt` file shows the bar as it stood
the moment that run finished — 12h's report shows 0.0167, 1d's shows
0.0125, 4h's shows 0.0100 — because the ledger grew while the three runs
were in progress. Judge all three against the final 0.0100 shown in the
table above, not against what their own report file says. In particular,
the DEVMA 12h report's own "clears corrected: YES" line is stale — it
was checked against 0.0167, and against the final 0.0100 its
walk-forward p (0.0159) does not clear.

**DEVMA 12h is the only survivor, and only at the raw 0.05 bar.** Its
in-sample p (0.0399) and walk-forward p (0.0159) both clear 0.05, so it
still earns LOOKS REAL — but neither clears the corrected 0.0100 bar, so
that verdict is provisional, not proven. No combo in this rerun clears
the corrected bar on both p-values.

**DEVMA 1d died from the combination of everything at once.** Both
p-values drifted past 0.05 (0.0698 and 0.0598) once shorts started
paying funding, selection moved from per-bar to trade-level profit
factor, and a year of data came off the end for the hold-out. No single
cause stands out as dominant here — it is several small honest costs
adding up, not one clear culprit.

**Diamond Hands 4h died with an overfitting fingerprint, not a
near-miss.** Its in-sample p (0.0075) is the single strongest number in
this whole rerun — strong enough to clear even the corrected bar on its
own. But its stage-2 selection found a trade-level profit factor of
**3.005** in the training windows, and that collapsed to **1.065** out of
sample, with the walk-forward p (0.0558) failing even the raw bar. A
selection score of 3.0 falling to 1.07 the moment it meets unseen data is
the classic sign the optimiser fit noise in-sample rather than finding a
durable edge — not a strategy that "almost" passed. 44 out-of-sample
trades spread across 11 folds (about 4 per fold) is thin evidence either
way.

**The buy-and-hold comparison is the most important number the old
analysis never showed.** All three strategies made money out of sample in
absolute terms, but every one of them made a third to a sixth of what
simply holding Bitcoin made over the identical stitched period (DEVMA
12h: +232% vs +767%; DEVMA 1d: +150% vs +893%; Diamond Hands 4h: +234%
vs +767%). A strategy that turns a profit but does worse than doing
nothing is not a strategy worth trading, no matter how clean its
p-value looks. This is true even for DEVMA 12h, the one survivor.

**The hold-out look, taken once, for DEVMA 12h only.** Running the
walk-forward once more on the full working set (no shuffles) to pick the
final fold's parameters (`{'vol_ma': 20, 'vol_run': 8}`) and testing them,
untouched by any optimisation, on the reserved final 12 months
(2025-08-07 to 2026-08-06): total return +7.2%, trade-level profit factor
1.208, Sharpe 0.23, 30 trades — against a buy-and-hold of −44.9% over the
same reserved window (Bitcoin fell over that stretch, so beating it here
is a lower bar than the earlier walk-forward periods where it rallied).
This is one look at one strategy. It is not a second confirmation and it
must not be tuned against — the moment the strategy changes because of
what this number says, it stops being a hold-out. DEVMA 1d and Diamond
Hands 4h did not earn a hold-out look because they failed the raw-0.05
rerun; none was taken for them.

## Combining Diamond Hands and DEVMA (2026-08-07)

Two ways to combine were tested (`combo` in strategies.py; blend
numbers below reproducible from check.run outputs):

**Merged into one book — makes things worse.** Adding the sweep entry
to DEVMA (gated by DEVMA's own trend-step) diluted the parent on both
timeframes: 12h PF 1.071 → 1.043, daily PF 1.092 → 1.056, returns
falling from ~+880% to ~+300%. DEVMA's vol-gated entries are the
edge; interleaving pullback entries takes positions the vol gate would
have refused, and inherits their stop-outs. Negative result, kept in
the repo (`--strategy combo`) as documentation.

**Blended as a portfolio — makes things better.** Running each parent
as designed (Diamond Hands on 4h, DEVMA on daily) with capital split
50/50 and daily rebalancing:

| | DH 4h | DEVMA 1d | 50/50 blend |
|---|---|---|---|
| Total return | +1095% | +894% | **+1224%** |
| Max drawdown | −57% | −53% | **−45%** |
| Profit factor | 1.143 | 1.092 | 1.126 |

Daily return correlation between the two is 0.64 — related (both are
long-biased crypto trend systems) but different enough that the blend
returns more than either parent with a smaller drawdown, the classic
diversification-plus-rebalancing effect. Caveat: 0.64 is still high;
this is one style diversified two ways, not two independent edges, and
both parents share the same fading-regime risk flagged elsewhere.

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
