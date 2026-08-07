# Plan: bring README.md back in line with the project

## What this is

`README.md` describes an older version of this project — back when there was
one strategy file (`strategy.py`), one signal, one asset and one bar size.
The code has moved on: there are now 8 strategies in `strategies.py`, four
extra scripts that stress-test the winners, and results written up in
`ANALYSIS.md` and `ROBUSTNESS.md`.

This job is a documentation edit. **Only `README.md` changes.** No code, no
other markdown file.

## Ground truth (already checked — don't re-verify unless something looks off)

- `strategies.py` (plural, 22 KB) holds 8 strategy classes. Its `REGISTRY`
  dict at the bottom maps the names you pass to `check.py --strategy`:
  `diamond_hands`, `trend_step`, `hl_band_breakout`, `structure_break`,
  `open_rejection`, `vwap_rejection`, `devma`, `combo`.
- `diamond_hands` **is** the sweep reversal the old README described
  ("Price sweeps the recent low but closes back above it, trend agrees").
- Each class carries a `GRID` (the parameter combinations the optimizer may
  try) and a `WARMUP` constant.
- There is no `strategy.py` singular any more.
- `check.py` writes its report to `report_<strategy>_<timeframe>.txt`
  (line ~256), e.g. `report_devma_1d.txt`. It does **not** write `report.txt`
  any more — the `report.txt` sitting in the repo is a leftover from before.
- Extra scripts in the repo root:
  - `robustness.py` — nine-angle robustness battery for the Diamond Hands
    4h result
  - `robustness_devma.py` — the same battery for the DEVMA daily result
  - `assets_devma.py` — runs DEVMA, untouched defaults, across 8 crypto
    majors (BTC ETH BNB XRP ADA LTC DOGE SOL) on daily and 12h
  - `equities_devma.py` — runs DEVMA, untouched defaults, on US equity
    indices, single large caps and gold (daily)
- Timeframes actually tested across the write-ups: 1h, 4h, 12h, 1d.
- Results live in `ANALYSIS.md` (the scoreboard for all 8) and
  `ROBUSTNESS.md` (the stress tests, cross-asset, and non-crypto results).

## Files to touch

- `C:\claudeOS\Projects\signalchecker\README.md` — the only file.

## The four edits

Keep the existing voice: plain language, short lines, wrapped around 76
characters like the rest of the file. Don't grow the README — the sections
below should end up roughly the same length as what they replace.

### Edit 1 — fix the report filename in "How to run it" (line 19)

The command block itself is correct and stays. Only the saved-file name is
wrong.

Replace:

```
The result prints to the screen and is saved to `report.txt`. It ends with a
verdict: **LOOKS REAL**, **NOT PROVEN**, or **NO EDGE FOUND**.
```

with:

```
The result prints to the screen and is saved to a report file named after
what you ran, e.g. `report_diamond_hands_12h.txt`. It ends with a verdict:
**LOOKS REAL**, **NOT PROVEN**, or **NO EDGE FOUND**.
```

(This is a one-fact correction, not a rewrite of the section — the section's
instructions are otherwise still right and stay as they are.)

### Edit 2 — replace the "The signal under test" section (lines 48–54)

Currently it describes a single sweep-reversal signal in `strategy.py`.
Replace the whole section, heading included, with:

```markdown
## The signals under test

`strategies.py` holds 8 strategies, each ported from an old TradingView
Pine Script, each with its own small parameter grid. Pick one with
`--strategy`:

`diamond_hands` (the sweep reversal: price dips below the recent low but
closes back above it while the longer trend agrees), `trend_step`,
`hl_band_breakout`, `structure_break`, `open_rejection`, `vwap_rejection`,
`devma`, `combo`.

All 8 went through the four stages. Two came out the far side:
`diamond_hands` on 4-hour bars and `devma` on daily. The full scoreboard is
in [ANALYSIS.md](ANALYSIS.md); the follow-up stress tests are in
[ROBUSTNESS.md](ROBUSTNESS.md).

Swap in your own signal by adding a class to `strategies.py` and an entry to
the `REGISTRY` at the bottom — anything expressible as buy/sell rules on
open/high/low/close works.
```

### Edit 3 — replace the "Files" list (lines 71–74)

Replace the four bullets with:

```markdown
- `data.py` — downloads and caches price candles (Binance via ccxt, plus
  daily stock and gold data)
- `strategies.py` — the 8 strategies being tested, each with its parameter
  grid
- `permute.py` — builds the shuffled price series for the honesty tests
- `check.py` — runs the four stages and prints the verdict; saves
  `report_<strategy>_<timeframe>.txt` (one report per strategy and bar
  size, e.g. `report_devma_1d.txt`)
- `robustness.py`, `robustness_devma.py` — extra stress tests for the two
  strategies that passed (Diamond Hands 4h, DEVMA daily)
- `assets_devma.py` — reruns DEVMA on 8 crypto majors, no re-tuning
- `equities_devma.py` — reruns DEVMA on US stocks and gold, no re-tuning
```

### Edit 4 — replace the first bullet of "Honest limitations" (lines 85–86)

Delete the "One asset (Bitcoin), one bar size (12h)" bullet and put the
multi-asset / multi-timeframe picture in its place. **Keep the other two
bullets exactly as they are** (flat slippage estimate; passing four stages
still isn't proof).

Replace:

```
- One asset (Bitcoin), one bar size (12h). A real edge should survive on
  more than one.
```

with:

```
- Testing now spans 8 crypto majors, four bar sizes (1h, 4h, 12h, 1d), and
  US stocks and gold — but crypto majors move together, so eight assets is
  more like two or three independent checks. DEVMA did not transfer to
  stocks or gold at all: it looks like a crypto-specific edge, not a
  general one.
```

## What must not change

- "How to run it" beyond the one filename in Edit 1
- "What it actually does" and the four numbered stages
- "Dashboard"
- "Credit where due"
- The last two bullets of "Honest limitations"
- Every file other than `README.md`

## How to verify

Run from the repo root (`C:\claudeOS\Projects\signalchecker`).

1. Only the README moved:
   `git status --short` → the single line `M README.md` and nothing else.
2. No stale singular filename left:
   `grep -n "strategy.py" README.md` → no hits (note: `strategies.py`
   contains the substring, so search for the exact `` `strategy.py` ``
   backtick form if the plain grep is noisy).
3. Old limitation gone:
   `grep -n "One asset" README.md` → no hits.
4. New names present:
   `grep -n "strategies.py\|robustness.py\|robustness_devma.py\|assets_devma.py\|equities_devma.py\|report_<strategy>_<timeframe>" README.md`
   → a hit for each.
5. Pointers present:
   `grep -n "ANALYSIS.md\|ROBUSTNESS.md" README.md` → at least one each.
6. Read the whole file top to bottom once. It should still sound like one
   person wrote it in plain English, and should not have grown by more than
   a dozen lines.

Nothing here executes code, so there are no tests to run.

## Notes

- Every number quoted above comes from `ANALYSIS.md` and `ROBUSTNESS.md` as
  they stand. Don't invent new figures for the README — point at those two
  files instead.
- The stale `report.txt` in the repo root is not this job's problem. Leave
  it alone.
