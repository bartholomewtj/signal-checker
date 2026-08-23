set dotenv-load

py     := "uv run --with-requirements requirements.txt python"

# list every recipe
default:
    @just --list

# ── signal-check ────────────────────────────────────────────────────────────

# preview an idea (not logged). opens last_run.html
check STRATEGY TIMEFRAME="12h":
    {{py}} check.py --strategy {{STRATEGY}} --timeframe {{TIMEFRAME}} --quick

# logged trial. raises Bonferroni N. only if you mean to log it
check-full STRATEGY TIMEFRAME="12h":
    {{py}} check.py --strategy {{STRATEGY}} --timeframe {{TIMEFRAME}}

# reopen last_run.html without re-running
visual:
    python visual.py

# pytest, including lookahead on every registry name
test:
    uv run --with pytest --with-requirements requirements.txt pytest -q tests

# N, Bonferroni bar, last verdict per pair
ledger:
    {{py}} ledger.py status

# live charts at http://localhost:8787 (not a ledger row)
dash:
    {{py}} dashboard.py
