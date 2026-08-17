# Adding an idea

One job: turn a described idea into a Strategy class the pipeline can judge.

## Inputs

- Working: the user's idea text from this chat
- Reference: `NewIdea` at the bottom of `strategies.py` (not in `REGISTRY`)
- Closed assets: crypto `BTC/USDT ETH/USDT BNB/USDT XRP/USDT ADA/USDT LTC/USDT DOGE/USDT SOL/USDT`; ETFs `SPY QQQ IWM EFA EEM TLT GLD`
- Timeframes: `4h`, `12h`, `1d` unless they name another cached file

Do NOT load: `docs/UNIFIED-ROADMAP.md`, `ANALYSIS.md`, robustness scripts, `adws/`.

## Process

1. **Stop. Ask first.** Call `ask_user_question` before writing any class. Lock at least: asset, timeframe, entry, exit, direction (both / long / short). If the idea is still vague after one round, ask again. Do not skip this because the idea "sounds clear."
2. Copy `NewIdea`, rename it, fill `init` / `next`. Causal indicators only. Any rolling min/max that must not include the current bar uses `.shift(1)`. Set `GRID` (small) and `WARMUP`.
3. Add the new name to `REGISTRY`.
4. `uv run --with pytest --with-requirements requirements.txt pytest -q tests` — lookahead runs on every registry name.
5. Only if they ask for a smoke look: `python check.py --strategy <name> --timeframe <tf> --quick`. **Never** a full `check.py` unless they say to log it.

## Outputs

- New class + `REGISTRY` line in `strategies.py`
- No `trials.csv` write. No `report_*.txt` from a preview.

## Human check

Read `init` / `next` aloud against the answers from step 1. Then they decide whether to log a full run (that raises Bonferroni N).
