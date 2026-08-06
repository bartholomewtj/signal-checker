# Robustness check: DEVMA on daily (added 2026-08-07)

DEVMA passed the four-stage check on both 12h and daily. This battery
attacks the daily result from nine angles (`python robustness_devma.py`;
BTC daily 2018–2026, defaults vol_ma=20/vol_run=5, bands 2D/3D, 0.15%
commission + 0.05% spread unless varied).

| # | Test | Result | Read |
|---|---|---|---|
| 1 | Vol-filter sweep (35 combos) | 35/35 profitable, median PF 1.111 | Total plateau — PASS |
| 2 | Band-timeframe sweep (8 combos) | 8/8 profitable, PF 1.07–1.18 | Structural plateau — PASS |
| 3 | Vol-gate ablation | normal +2060%; gate off +104%; inverted +145% | The gate IS the edge — PASS |
| 4 | Cost stress | PF 1.086 even at 0.40%/side | PASS |
| 5 | Long vs short | Long PF 1.19 (+1119%); short PF 1.03 (+38%) | Long-biased — CAUTION |
| 6 | Entry delayed one day | PF 1.167 (+1301%) | Timing-insensitive — PASS |
| 7 | Sub-periods | 2018–20 PF 1.27; 2021–23 PF 1.09; 2024–26 PF 0.995 | **Edge decaying — WARNING** |
| 8 | Bootstrap (10,000x) | 2.2% chance of overall loss | PASS |
| 9 | ETH transfer, no re-tuning | PF 1.070, +849% vs +152% buy-and-hold | PASS |

**The ablation (test 3) is the standout.** With the volatility gate
removed, returns collapse from +2060% to +104%; with the gate inverted
(enter on falling volatility instead of rising), +145%. The gate isn't
decoration — "only enter when volatility is expanding" is where most of
the strategy's edge lives, and it's directional: both wrong versions
land in the same much-worse place. This also explains the earlier
finding that the raw breakout signals were real but cost-eaten: DEVMA
is those signals traded only when conditions favour follow-through.

**The sub-period decay (test 7) is the serious warning.** Each third is
weaker than the last, and 2024–2026 is breakeven (−3%) while
buy-and-hold made +46%. The walk-forward folds showed the same shape.
Everything else in this battery says the strategy was well-built; this
test says the market it was built for has been fading. A strategy can
be statistically real *and* past its prime — forward paper-trading is
the only way to find out which side of that line it's on now.

Everything else: parameter and band plateaus are as clean as they come
(43/43 profitable configurations), it survives nearly 3x realistic
costs, a full day's entry delay costs nothing, shorts add little (as
with Diamond Hands), and the same untouched rules made 5.6x
buy-and-hold on ETH. Fold-level detail in report_devma_12h.txt and
report_devma_1d.txt.

## Cross-asset extension (2026-08-07, `python assets_devma.py`)

DEVMA with untouched default parameters on eight majors, daily and 12h:

| Asset | Daily PF | Daily return vs buy&hold | 12h PF | 12h return vs buy&hold |
|---|---|---|---|---|
| BTC | 1.092 | +894% vs +1231% | 1.071 | +872% vs +1251% |
| ETH | 1.070 | +849% vs +152% | 1.067 | +1473% vs +157% |
| BNB | 1.034 | +188% vs +6904% | 1.009 | +42% vs +7154% |
| XRP | 1.068 | +784% vs +17% | 1.065 | +1104% vs +13% |
| ADA | 1.104 | +4650% vs −17% | 1.069 | +2402% vs −23% |
| LTC | 0.889 | −99% vs −80% | 0.961 | −83% vs −80% |
| DOGE | 1.082 | +1276% vs +1683% | 1.065 | +1295% vs +1683% |
| SOL | 1.132 | +3617% vs +2103% | 1.060 | +948% vs +2283% |

**14 of 16 combinations profitable** (only LTC failed, both timeframes),
each with 140–300 trades. The most telling pattern: the strategy's
biggest wins are on assets where buy-and-hold went nowhere — ADA
(−17% market, +4650% strategy), XRP (+17% market, +784% strategy),
ETH (+152% market, +849% strategy). That's the signature of genuine
trend/volatility timing rather than disguised market exposure. The LTC
failure fits the same logic in reverse: a long-biased trend strategy on
an asset in near-permanent decline with no sustained upside expansions
bleeds to death.

Caveats: crypto majors are heavily correlated, so these are not eight
independent confirmations — call it perhaps two or three. Alt drawdowns
at full-equity sizing are unsurvivable in practice (−70% to −99%);
any real deployment needs smaller sizing. And BNB/DOGE/SOL trailing
their own moonshot buy-and-hold is expected: no risk-managed strategy
keeps up with a 70x asset.

---

# Robustness check: Diamond Hands on 4h

The 4h result passed the four-stage honesty check (see ANALYSIS.md). A
passing strategy can still be fragile, so this battery attacks it from
seven angles. Reproduce everything with `python robustness.py`.
Data: BTC 4h 2018–2026 unless stated; defaults lookback=20, trend_len=200;
0.15% commission + 0.05% spread unless varied.

## Results at a glance

| # | Test | Result | Read |
|---|---|---|---|
| 1 | Parameter sweep (54 combos) | 35/54 profitable, median PF 1.037 | Plateau, not a spike — PASS |
| 2 | Cost stress | PF 1.061 → 1.037 as fees rise 0.02% → 0.40% | Survives 2.5x realistic fees — PASS |
| 3 | Long vs short leg | Long PF 1.08 (+376%); short PF 1.02 (+39%) | Long leg carries it — CAUTION |
| 4 | Entry delayed one bar | PF 1.053 → 1.050, return 563% → 489% | Degrades gracefully — PASS |
| 5 | Sub-periods (3-year thirds) | PF 1.084 / 1.011 / 1.066, all positive | No dead regime — PASS |
| 6 | Bootstrap (10,000 resamples) | Median +529%; 4.7% chance of loss | Skewed favourably — PASS |
| 7 | ETH, same rules, no re-tuning | PF 1.051, +766% vs +106% buy-and-hold | Transfers — PASS |

## What each test showed

**1. Parameter plateau.** Profitability is spread across a broad region
(lookback 8–48 × trend 150–400 is almost uniformly PF > 1), and the
defaults sit inside the plateau rather than on the best cell. The
failure zones make sense: a 50-bar trend filter whipsaws, and lookback
64 waits too long for sweeps. One warning from the map: the optimizer's
favourite corner (lookback 48, trend 100, PF 1.142) sits next to a
cliff (lookback 64, trend 100 = PF 0.590). Trade the plateau, not the
optimum.

**2. Costs barely matter.** With only 111 trades in 8.6 years, turnover
is so low that even 0.40% per side (nearly 3x a normal taker fee) leaves
PF at 1.037 and +282%. This edge is not an artifact of the cost model.

**3. The short leg is a passenger.** Longs delivered +376% (PF 1.08);
shorts +39% (PF 1.02). Shorts didn't lose — surviving short exposure
through two crypto bull runs is itself notable — but nearly all the
edge is the long side. A long-only version is simpler and loses little.

**4. Not a timing fluke.** Entering a full bar late (8 hours after the
signal on 4h bars) keeps PF essentially unchanged. Strategies that
depend on razor-sharp fills die in this test; this one doesn't.

**5. No dead regime.** 2018–20: +186% (PF 1.08). 2021–23: +15%
(PF 1.01). 2024–26: +86% (PF 1.07). The middle third — chop and the
2022 bear — was breakeven-ish, matching buy-and-hold's +16% with far
less drawdown. It has flat stretches, not fatal ones.

**6. Luck envelope.** Reshuffling which trades you happened to get,
10,000 times: median outcome +529%, 5th percentile +3%, chance of
overall loss 4.7%. The right tail is huge (95th pct +5,111%) — a few
big winners drive results, consistent with the 33% win rate. Expect
long losing streaks on the way to the average.

**7. The strongest evidence: ETH.** Same rules, same defaults, zero
re-tuning, on an asset the pipeline never saw during development:
PF 1.051, +766% against ETH's +106% buy-and-hold, from 101 trades.
Cross-asset transfer without adjustment is hard to fake. Max drawdown
was −66%, though — ETH is wilder.

## Weak points, honestly

- **Drawdowns are serious**: −37% (BTC), −66% (ETH). At 100% equity per
  trade this is not a comfortable ride; smaller position sizing scales
  the pain and the profit together.
- **The edge is long-biased** and concentrated in a few large winners;
  the bootstrap's 5th percentile is roughly breakeven. Eight years can
  still be one long lucky draw at ~5% probability.
- **Multiple-testing residue remains** from ANALYSIS.md: 4h was the
  second timeframe tried. The ETH transfer mitigates this materially
  but doesn't erase it.

## Bottom line

The 4h Diamond Hands result is robust by every test available offline:
plateau not spike, cost-insensitive, timing-insensitive, no dead regime,
and it transfers to an untouched asset. The remaining unknowns (regime
change, live execution) can only be answered by paper trading it
forward. If pursued: use plateau parameters (lookback ~20–40, trend
150–300), expect the long side to do the work, and size positions for
a −40% drawdown you will eventually meet.
