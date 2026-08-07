# Plan — harden and land the five statistical-honesty fixes

## Read this first: the work is already built

A builder has already implemented all five fixes against the earlier spec
(`specs/c32b4b46_statistical-honesty-fixes.md`). This is a **second pass**. Do
not rebuild anything. Your job is to close four specific gaps found by auditing
the built code, then get it committed.

### What I verified is already working

| Fix | State | Evidence |
| --- | --- | --- |
| 1 — hold-out | Done | `data.split_holdout()` exists; `main()` splits and runs stages on `work_df`; `--holdout` branch calls `run_holdout()`, writes `holdout_<strategy>_<tf>.txt` |
| 2 — ledger | Done | `trials.csv` at repo root has a header + 4 rows from the builder's own verification runs; `append_trial()` / `count_trials()` present; verdict prints both bars |
| 3 — metric + benchmark | Done | `optimize()` scores on `trade_profit_factor` with `MIN_TRADES = 10`, unviable = 0.0; `sharpe()` and `buy_and_hold_pct()` printed in stage 3 |
| 4 — charge the shorts | Done | `funding_rate_per_bar()` + short mask inside `run()`, so every stage including permutations is charged; `Base` class in `strategies.py` gives all 8 strategies the `direction` filter; `--direction` flag wired |
| 5 — tests | Done | `tests/` has 5 files, 424 lines; **29 tests pass in 0.97s** |

I also confirmed the two contracts from the first spec survived: `run()` still
returns `(rets, stats)` for `dashboard.py`, and the verdict still prints the
literal `LOOKS REAL` / `NOT PROVEN` / `NO EDGE` strings.

**I empirically verified the lookahead tripwire.** I copied the repo to a
scratch directory outside the project, deleted the `.shift(1)` from
`htf_bands()`, ran the suite there, and got:

```
FAILED tests/test_lookahead.py::test_no_lookahead[combo]
FAILED tests/test_lookahead.py::test_no_lookahead[devma]
2 failed, 6 passed
```

The scratch copy has been deleted. Nothing broken was committed. So the
tripwire genuinely bites — but see Task 2 for why it barely does.

---

# The four gaps

## Task 1 — decide what to do about the one out-of-scope edit

The brief said "do not touch ... anything under `adws/`". The builder modified
`adws/adw_modules/quality.py`, replacing the test placeholder:

```python
-        argv=_placeholder("test"),
+        argv=["uv", "run", "--with", "pytest", "--with-requirements",
+              "requirements.txt", "pytest", "-q", "tests"],
```

**This is a genuine judgement call, not a straightforward violation.** That file
carries a banner at the top that literally instructs you to do this: "For each
block you want: swap `_placeholder(...)` for the real argv, e.g.
`argv=["uv", "run", "pytest", "-q"]`". Until now there was no test suite, so the
placeholder was correct; now there is one, and without this edit the factory's
test gate just echoes "PLACEHOLDER test" and passes without running anything.

The edit is also written the way that file asks for: an argv list, not a shell
string, with binaries called by bare name.

**Recommendation: keep it.** Flag it to the user in the PR description as a
deliberate departure from the brief, in one line, so they can say no. If they
want it reverted: `git checkout adws/adw_modules/quality.py`, and the pipeline's
test gate goes back to being a no-op.

Do not make any *further* edits under `adws/`.

## Task 2 — strengthen the lookahead tripwire

This is the most valuable task in this plan.

### The problem

When I removed the `.shift(1)`, the test failed on exactly **1 mismatched
element out of 517**, at index 516 — the very last bar before the truncation
point:

```
Mismatched elements: 1 / 517 (0.193%)
Mismatch at index: [516]: 1.0 (ACTUAL), 0.0 (DESIRED)
```

That is a razor-thin margin. The tripwire currently tests a single truncation
point, `T = 517`. A lookahead bug only shows up when the truncation lands in a
part of a higher-timeframe bucket where the partial bucket's max/min differs
from the complete one. At an unlucky `T` — one that happens to land on or near a
bucket boundary, or where the affected bars produce no signal change — the same
bug would sail through green.

A tripwire that catches a bug at one of many possible offsets is not a tripwire,
it is a coin flip.

### The fix

In `tests/test_lookahead.py`, parametrise over several truncation points instead
of one:

```python
N_BARS = 700
# Several truncation points, not one. A higher-timeframe lookahead bug only
# shows up when the cut lands mid-bucket in the right phase; testing a single
# T means a real bug can pass by luck. These are spread across different
# offsets modulo the 2D and 3D bucket sizes Devma resamples to.
TRUNCATIONS = [431, 517, 588, 634]
```

Turn the test into a double parametrise over `name` and `t`:

```python
@pytest.mark.parametrize("t", TRUNCATIONS)
@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_no_lookahead(name, t, synthetic_frame):
```

and use `t` in place of the module constant `T` throughout the body.

Requirements on the truncation points:

- Every one must comfortably clear the largest `WARMUP` in the registry
  (`Devma.WARMUP = 360`), so pick nothing below ~420.
- They must not all share the same remainder modulo the 2-day and 3-day bucket
  sizes. At 12h bars, a 2D bucket is 4 bars and a 3D bucket is 6 bars, so vary
  `t % 4` and `t % 6` across the list. The four values above give
  `t % 4 = 3, 1, 0, 2` and `t % 6 = 5, 1, 0, 4` — all four phases of the 2D
  bucket and four of the six phases of the 3D bucket.

### Keep the cost down

This multiplies the number of backtests by four. The full-series run is
identical for every `t`, so compute it once per strategy and reuse it. A
module-level cache keyed by strategy name is the simplest thing that works:

```python
_FULL_CACHE = {}

def _full_run(name, df, strat_cls, defaults):
    if name not in _FULL_CACHE:
        _FULL_CACHE[name] = _run(df, strat_cls, defaults)
    return _FULL_CACHE[name]
```

The suite currently runs in 0.97s. After this change it should still be a few
seconds — well inside the "well under a minute" requirement. If it is not,
drop to three truncation points rather than shrinking `N_BARS`.

### One warning to put in the test file as a comment

If this test ever goes red at the last index or two before a truncation point,
**that is the tripwire working**. Do not "stabilise" it by trimming the final
bars from the comparison — the boundary is precisely where a higher-timeframe
lookahead shows up, and trimming it disarms the whole test. Write that in a
comment so a future reader does not helpfully break it.

### Re-verify after changing it

Repeat the scratch-copy check — outside the repo, never committed:

```bash
SCRATCH=$(mktemp -d)
cp -r tests strategies.py permute.py check.py data.py requirements.txt "$SCRATCH"/
cd "$SCRATCH"
# delete the ".shift(1)" from the out = pd.DataFrame({...}).shift(1) line
# at the end of htf_bands() in strategies.py, then:
uv run --with pytest --with-requirements requirements.txt pytest -q tests/test_lookahead.py
# expect: failures for devma and combo, across MULTIPLE truncation points
cd - && rm -rf "$SCRATCH"
```

The bar to clear this time: the broken variant should fail at **more than one**
truncation point. If it still only fails at one, your truncation points are not
spread widely enough — adjust them until at least two catch it.

## Task 3 — close the funding-cost footgun

`check.trade_profit_factor(stats, df=None)` takes `df` optionally, and silently
skips the short funding adjustment when it is omitted:

```python
def trade_profit_factor(stats, df=None):
    ...
    if df is not None:
        # ... apply the short funding charge
```

Every current caller passes `df`, so the behaviour is right today. But the whole
point of Fix 4 is that the charge cannot be skipped by accident, and this
signature makes skipping it the easy mistake — a future caller that forgets the
argument gets silently optimistic numbers with no error.

Make `df` a required positional parameter:

```python
def trade_profit_factor(stats, df):
    """Gross trade profits divided by gross trade losses.

    `df` is required: it sets the bar size for the short funding charge.
    Making it optional would let a caller silently skip the charge, which
    is the exact bias Fix 4 exists to remove.
    """
```

Then drop the `if df is not None:` guard and apply the charge unconditionally.
Check the three call sites still pass it (`optimize()`, `run_holdout()`, and
`tests/test_metrics.py`). Update the tests: any that call it with one argument
now need a small frame with a `DatetimeIndex` — reuse the `tiny_frame` fixture
rather than inventing a new one.

## Task 4 — evidence for the one unproven "done means"

Fix 4's done-condition is "a strategy that shorts frequently scores measurably
worse than before". Nothing on record shows that. The ledger shows different
numbers between direction modes, which is not the same claim — that is the
direction filter, not the funding charge.

Produce the evidence once, by hand. `trend_step` is the right subject: it is
always in the market and stop-and-reverses, so it holds shorts roughly half the
time.

```bash
# with the funding charge as built
uv run --with-requirements requirements.txt python check.py \
    --strategy trend_step --timeframe 1d --quick
```

Then temporarily set `FUNDING_PER_8H = 0.0` at the top of `check.py`, run the
same command again, and compare the stage 3 out-of-sample return and Sharpe.
**Set it back to `0.0001` immediately afterwards** — do not commit the zero.

Expected: the funded run is worse. Record the two numbers in the PR description
as the evidence for that done-condition. If the funded run is *not* worse,
something is wrong with the short mask in `run()` — say so rather than papering
over it.

Note this comparison run will add rows to `trials.csv`. That is fine and
correct; they are real trials.

---

# Verification

Run all of these from the repo root and judge each by exit status.

```bash
# 1. Full suite — must stay well under a minute
uv run --with pytest --with-requirements requirements.txt pytest -q tests

# 2. A normal run still works end to end after the Task 3 signature change
uv run --with-requirements requirements.txt python check.py \
    --strategy diamond_hands --timeframe 1d --quick

# 3. Hold-out mode still works
uv run --with-requirements requirements.txt python check.py \
    --strategy diamond_hands --timeframe 1d --holdout

# 4. The dashboard still starts and parses the reports (it was never touched,
#    but the report format changed underneath it)
uv run --with-requirements requirements.txt python dashboard.py
```

Plus the scratch-copy tripwire check from Task 2, which is the one that matters.

By eye:

- `trials.csv` grew by one row per run, with the header intact.
- The verdict block still prints both the raw and corrected bars.
- The dashboard lists verdicts for each `report_*.txt` and shows no phantom
  timeframe row from a `holdout_*.txt` file (those are named so its regex
  ignores them, and are gitignored).

# Git

Nothing is committed yet. `git status` currently shows five modified files plus
untracked `tests/`, `trials.csv`, and `specs/`.

```bash
git checkout -b statistical-honesty-fixes
git add check.py data.py strategies.py .gitignore tests/ trials.csv specs/
# plus adws/adw_modules/quality.py only if Task 1 lands on "keep"
git commit
gh pr create
```

Two things to get right:

- **`trials.csv` must be committed, not ignored.** It is the record that makes
  the Bonferroni correction meaningful across sessions. Confirm `.gitignore`
  does not exclude it — currently it does not.
- The PR description should carry the two pieces of evidence this plan
  produces: the Task 4 funded-vs-unfunded numbers, and a line confirming the
  tripwire was verified against a scratch copy with `.shift(1)` removed.

Do not commit `report_*.txt` or `holdout_*.txt` — both are gitignored already.

# Out of scope

Unchanged from the original brief: no data hygiene work (cache filenames, gap
detection, exchange source tracking), no new strategies, no dashboard changes,
no git-SHA stamping, no deflated Sharpe, no White's Reality Check. The
permutation algorithm in `permute.py` must not change. No further edits under
`adws/` beyond the Task 1 decision.
