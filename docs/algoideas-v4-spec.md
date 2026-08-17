# Algo Idea Validation Pipeline — Specification (v4)

A system to honestly test trading ideas. You give it a vague idea in plain English. An AI agent turns it into a precise, testable rule spec. The pipeline backtests the rule, runs leak-free cross-validation, applies realistic costs to the out-of-sample results, deflates the statistics for every trial you've ever run, and returns a pass/fail audit report.

**Design stance:** the gates are strict on purpose. Most ideas are false. A machine that says "REJECTED" most of the time is working correctly.

---

## Scope decisions (locked)

These are not up for silent re-expansion:

- **Rule-testing only, no ML.** Ideas are expressed as explicit entry/exit rules over indicators. No classifiers, no triple-barrier labeling, no fractional differentiation. If an idea can't be written as a rule, the translator rejects it.
- **Universe restricted to assets that don't delist.** Major index ETFs and major crypto (BTC, ETH, plus a small fixed list). This deletes the survivorship-bias problem instead of solving it. See "Universe & data" for the residual bias we disclose.
- **FX is out of scope for v4.** yfinance FX daily bars are indicative mid quotes: opens are often fictional (equal to prior close), volume is zero, and day boundaries are ambiguous — every fill and every volume rule would be arithmetic on made-up numbers. FX may return later, but only with a broker-consistent data source (e.g. Dukascopy, TrueFX, or the broker's own bars).
- **Simple, honest cost model.** Spread + exchange fees + carry (for shorts) + square-root market impact. The Almgren-Chriss model is removed — it's an institutional order-scheduling model needing calibration data we don't have.
- **Reuse before build.** Published, tested libraries cover CPCV and the deflation statistics. We wrap them, we don't reimplement them (see "Build vs reuse").
- **The AI translator stays.** Vague idea in, structured `HypothesisSpec` out. It is a convenience layer only — the pipeline runs identically from a hand-written spec file.

---

## The 6-stage validation framework

Every hypothesis passes through all six stages in order. Each stage has explicit gates; failing any gate fails the hypothesis, but the pipeline still runs to completion so the report shows *everything* that failed.

| Stage | Name | What it does |
|---|---|---|
| 1 | Translation | Vague idea → structured `HypothesisSpec` (rules, universe, parameter grid). Human confirms the interpretation before anything runs. |
| 2 | Data | Load daily bars for the spec's universe from an immutable local snapshot. Integrity checks (see "Universe & data"): calendar-aware gap checks, OHLC coherence, enough history, timezone-aligned, no partial bars. |
| 3 | Backtest | Rule engine turns signals into a return series per parameter combination — a per-bar state loop, since exits like `holding_days` and profit targets are path-dependent. Next-bar-open execution with conservative intrabar fill rules, no look-ahead. Output contract: per-combo (returns series, positions series, trade log with entry/exit dates and sizes) — Stages 4 and 5 both consume the trade log. |
| 4 | Validation | Combinatorial Purged Cross-Validation (CPCV) over the parameter grid. Purge windows derive from the trade span (entry to exit, up to `max_hold` bars); the embargo sits on top of purging, not instead of it. OOS returns come only from trades whose entry bar lies inside the test block — positions are forced flat at each test-block start, and trades straddling a boundary are excluded from the OOS series and the trade count (a straddling trade carries in-sample state like `entry_price` and `holding_days` into the test data). **Selection rule (pre-registered):** within each CPCV split, the combination with the best in-sample (training) Sharpe is selected; its out-of-sample returns, concatenated across splits, form the series the gates are applied to. This is the PBO-consistent choice — you gate the strategy you would actually have picked, judged on data it never saw. |
| 5 | Costs | Apply spread, fees, carry, and square-root impact to the out-of-sample CPCV paths. Everything downstream is post-cost. |
| 6 | Deflation & verdict | Log all trials to the global ledger. Compute clustered effective trial count, then Deflated Sharpe Ratio (DSR) and Probability of Backtest Overfitting (PBO) — all on post-cost out-of-sample returns of the selected combination. Check every gate. Emit the audit report, including the live power line (the minimum Sharpe that would pass today's ledger). |

---

## Component workflow

1. **Idea ingestion** — free-form text: `"buy BTC when weekend volume dries up and it's above the 200-day"`.
2. **AI Hypothesis Translator** — one API call that returns a `HypothesisSpec` JSON plus a plain-English restatement ("I understood your idea as: ..."). **The signal preview is then computed locally** — the validated spec is executed against cached data by our own code; the LLM never produces or sees preview numbers. The preview shows: how often the rule fired, ~5 example dates/prices, **and 2–3 simulated full trades** (entry date → exit date, exit reason, holding period, indicator values at the fire dates) — **with no P&L**: sample-trade returns shown before confirmation would invite previewing ten phrasings of an idea and ledgering only the flattering one, which is unlogged multiple testing run by the pipeline's own code. For the same reason, **every generated preview — confirmed or declined — appends a coarse row to the ledger**, so preview churn shows up in the completeness disclosure instead of leaving zero footprint. The preview matters more than the restatement: restatement and JSON come from the same API call, so a mistranslation reads fluently, but firing *and exit* behaviour is checkable without reading the DSL. Before confirmation the translator also **checks the ledger for similar prior hypotheses** ("You tested a close variant in March; REJECTED at the DSR gate"). If the idea needs ML or an unsupported asset class, the translator says so and stops.
3. **Pipeline runner** — executes Stages 2–6 from the spec. Deterministic: same spec + same data snapshot + same ledger state = same report. Every report records the ledger snapshot (row count + content hash) and the data snapshot digest it was computed against. At invocation the runner asks: *"Any off-pipeline experiments (TradingView, notebooks) since your last run? [y/N]"* — yes drops straight into `add_manual`. After each run it writes a timestamped backup copy of `trials.db` to a synced folder.
4. **Audit reporter** — markdown report with the gate table, the CPCV path distribution, the deflation audit, per-year and stress-window Sharpe slices, and a plain-language "why this failed / passed" section.
5. **Post-verdict protocol** — see "After ACCEPT" and "After REJECT" below. The pipeline's job doesn't end at the report.

---

## Universe & data

**Allowed asset classes (fixed, closed lists in `config/universe.yaml`):**

- **Index ETFs:** SPY, QQQ, IWM, EFA, EEM, TLT, GLD. This list is closed — no "and similar" clause. Adding a ticker is a config diff, visible in git history.
- **Crypto majors:** BTC-USD, ETH-USD, and at most 3–4 others with ≥5 years of continuous history. **One exchange, one quote currency per asset, named in the config** (default: Coinbase, USD quotes). Mixing sources for the same asset is forbidden — it fragments trial identity. Crypto bars are fetched **from the named venue itself via ccxt — never from yfinance**: Yahoo's BTC-USD/ETH-USD are multi-exchange composite indexes, so a fill at their "open" is a price that never traded anywhere, and the fee schedule, volume, and ADV must belong to the same venue as the prints.
- **FX: removed in v4** (see scope decisions). May return with a broker-consistent source.

**Price basis (pinned, never defaulted):**

- **Raw prices plus the dividend and split event tables** (dates + amounts) are stored for every ETF; the adjusted series is derived deterministically in code from them, never stored as a source of truth. yfinance's `auto_adjust` flag is set explicitly in code, never left to the library default (it has changed across versions). One honesty caveat on "raw": Yahoo's unadjusted prices are themselves retroactively **split**-adjusted, so the stored basis is precisely *split-adjusted, dividend-unadjusted*. The split-factor series is stored alongside prices, and a new split forces a full snapshot refresh with a new digest.
- **Indicator expressions and level rules evaluate on raw OHLCV** — the closest available basis to the prices observable on the day (see the split caveat above). **P&L uses total-return (adjusted) returns** — otherwise every ex-dividend date prints a fake loss (~1.5–4%/yr on TLT-class funds) and long strategies are systematically penalised. **The boundary between the two spaces is pinned:** entries, exits, targets, and stops are evaluated and filled in raw space; each fill price is then mapped through that bar's adjustment factor (adj_close / raw_close), and the total-return P&L series is built from the mapped fills. Disclosed consequence: an ex-dividend raw price drop can trigger a raw-space stop or delay a raw-space target — a Phase-2 fixture with an ex-div gap verifies this accounting.
- This split also keeps the look-ahead audit honest: adjusted history is rewritten retroactively at every distribution, so a signal computed on adjusted prices embeds information unknown at the time. The truncation-invariance test (Stage 3 gate) runs on the raw series, where bit-identity is meaningful.

**Data snapshots and the data digest:**

- Data is cached locally as parquet in `data/`; the pipeline never hits the network mid-run.
- The trial ledger's data hash is **not** a file hash — parquet bytes vary with library versions and compression, and Yahoo revises history retroactively. Instead: a **canonical content digest** per asset — SHA-256 over (sorted date index, raw OHLCV values rounded to fixed precision, and the dividend/split event tables at the same fixed precision). Adjusted prices are never digested — they are derived in code from exactly these inputs — so a retroactive rewrite of Yahoo's adjusted history cannot churn trial identity, while everything P&L depends on stays pinned by the digest.
- Each digested snapshot is **immutable on disk**. Refreshing data is an explicit, versioned event that creates a new snapshot with a new digest — not a silent overwrite. Old reports stay reproducible because the data behind their digest still exists.
- At first cache build, a **documented manual spot check**: eyeball ~5 closes per asset against a second source (TradingView/CoinGecko-class) and record the result in the snapshot metadata. Close prices only, with per-asset-class tolerance bands — a few bps for ETFs, ~1% for crypto, because composite indexes legitimately differ from venue bars; volume is excluded for crypto (global aggregates differ from venue volume by orders of magnitude). Not automated: a second fetch path to sanity-check SPY and BTC is machinery a manual step covers, and it only gets automated if the universe grows beyond majors.

**Integrity checks (Stage 2, all must pass):**

- **Calendar-aware gap check**, per asset class: ETFs checked against the exchange calendar (via `pandas-market-calendars` — new dependency, confirm before adding at build time); crypto checked against every UTC day. A blanket "no gaps" rule is wrong for both.
- **Outage policy** (crypto): a gap ≤ 3 bars is flagged in the report and excluded from returns; a longer gap fails the gate.
- **OHLC coherence:** low ≤ open, close ≤ high on every bar.
- **No duplicate or non-monotonic timestamps.**
- **Stale-bar screen:** runs of identical consecutive OHLC flagged.
- **Outlier screen:** any single-bar |return| > 8σ flagged for review — one bad tick corrupts a 90-day rolling mean for 90 bars.
- **No zero/negative prices; explicit NaN policy** (no silent forward-fill).
- **Drop the incomplete current bar at fetch time**, keyed to each asset's day boundary (UTC close for crypto, exchange close for ETFs). A partial bar is look-ahead contamination in the data itself — the engine's audit can't catch it.
- **Enough history:** ≥ 8 years (ETF) or ≥ 5 years (crypto).

**Annualisation** comes from the asset class, never hardcoded: 252 for ETFs, 365 for crypto (24/7 trading).

**`is_weekend` is crypto-only.** ETF daily data contains no weekend bars, so the flag would be constant-False and a rule using it would silently never fire. The schema rejects `is_weekend` for non-crypto universes. Weekend is defined in UTC.

**Disclosed residual bias:** picking today's major cryptos — and, more mildly, today's mega-AUM ETFs — is itself selection bias (assets that made it to 2026). Every report carries a fixed disclosure line about this, for all asset classes. We accept it; we don't hide it.

---

## The HypothesisSpec (rule DSL)

Pydantic model in `schema/hypothesis.py`. A spec is a small JSON file:

```json
{
  "id": "BTC-WEEKEND-VOL-001",
  "idea_text": "buy BTC when weekend volume dries up and it's above the 200-day",
  "universe": ["BTC-USD"],
  "indicators": {
    "vol_ratio": "volume.rolling(w_vol).mean() / volume.rolling(90).mean()",
    "trend": "close > close.rolling(200).mean()"
  },
  "entry": "(vol_ratio < vol_thresh) & trend & is_weekend",
  "exit": "holding_days >= max_hold",
  "profit_target": 0.08,
  "stop_loss": null,
  "direction": "long",
  "position_sizing": {"method": "fixed_fraction", "fraction": 0.10},
  "parameter_grid": {
    "w_vol": [5, 7, 10],
    "vol_thresh": [0.5, 0.6, 0.7],
    "max_hold": [3, 5, 10]
  },
  "cv": {"n_blocks": 8, "n_test_blocks": 2}
}
```

The human-readable `id` is a **label only** — trial identity in the ledger is a content hash (see "Trial ledger").

Constraints enforced by the schema:

- Indicator expressions are a whitelisted subset of pandas operations: rolling mean/std/min/max/rank, `ewm` (for EMA/RSI/MACD-style rules), `shift`, `diff`, `pct_change`, `abs`, `clip`, element-wise `maximum`/`minimum` (RSI needs `clip` to split gains from losses; ATR needs a three-way element-wise max — without these the whitelist can't express the rule classes it claims to support), arithmetic, comparisons. Implementation is **AST-validate then restricted eval**: parse with `ast.parse`, walk the tree against a whitelist of node types, methods, and identifiers, then evaluate in a namespace containing only the declared columns and parameters. Do not hand-roll an expression interpreter — weeks of work for zero benefit in a single-user tool.
- Entry/exit are boolean expressions over declared indicators and built-ins: `holding_days`, `bars_since_entry`, `entry_price`, `ret_since_entry` (signed return since entry), and `is_weekend` (crypto universes only; rejected otherwise). **Exit expressions evaluate on closed bars only and fill at the next bar's open.** Intrabar fills exist solely for the structured `profit_target` / `stop_loss` fields (signed fractions of entry price, raw space) — a trigger price can be extracted from a declared number, not from an arbitrary boolean, so free-form expressions never intrabar-fill. A `ret_since_entry >= x` clause in an exit expression is rejected by the schema with a pointer to `profit_target`, which tests the same idea under the conservative gap-fill rules instead of at the close.
- `parameter_grid` is explicit and finite. The grid size is printed to the user *before* the run, because every combination is a logged trial. **Grid norms:** the translator warns above 50 combinations and requires an explicit override flag above 200 — two careless 500-combo grids in week one would permanently tax every future DSR.
- **Multi-asset specs produce one return series per asset, each its own ledger row. No pooling in v1** — pooling changes the Sharpe, the trial count, and N_eff, and an ambiguity there lets an implementation choice flatter results.
- Position sizing v1 is fixed-fraction only. Volatility targeting is a later option, not in v1.
- `direction: short` on crypto is flagged by the translator: shorting spot crypto isn't a thing — it needs perpetual futures, with funding costs and access constraints. The pipeline can test it, but the report carries a "perp-only, verify you can actually execute this" warning.

---

## Backtest engine contract

The engine (`core/backtest/engine.py`) has two layers:

- **An expression-free core API** (built in Phase 2): takes precomputed indicator columns, a boolean entry series, and exit parameters; returns the output contract below. This makes Phase 2 testable before the DSL exists — the DSL becomes a thin layer on top in Phase 3.
- **Output contract, per parameter combination:** `(returns series, positions series, trade log)` where the trade log holds entry/exit dates, direction, and sizes. Stage 4 needs the trade spans for purging; Stage 5 needs the trade events for per-round-trip costs. This is the most load-bearing interface in the system, so it's written down here, not left to drift.

**Fill rules (conservative by construction):**

- Signals computed on closed bars fill at the **next bar's open**.
- Profit targets and stops — the structured `profit_target`/`stop_loss` fields only — fill at the **worse** of (trigger level, next bar open) — never at an untraded touch price. Filling at the touch when price gapped through it is a top-3 source of fake backtest alpha.
- Free-form exit expressions evaluate on the closed bar and fill at the **next bar's open** — a boolean has no trigger level to fill at.
- A bar that touches both the target and an adverse level resolves conservatively (adverse first).

---

## Directory & module structure

| Module path | Core functionality | Build or reuse |
|---|---|---|
| `config/` | Universe list, gate thresholds, cost parameters, account equity, data paths. | Build (YAML) |
| `schema/hypothesis.py` | `HypothesisSpec` Pydantic model + expression whitelist parser. | Build |
| `core/agent/translator.py` | Prompt template + API call + spec validation + **local** signal preview + ledger similarity check + human confirmation step. Stamps each spec with model id + prompt version. | Build |
| `core/data/loader.py` | Download, snapshot (immutable parquet + content digest), and integrity-check daily bars. | Build (thin wrapper on yfinance/ccxt) |
| `core/backtest/engine.py` | Rule → returns engine: vectorised indicator/entry evaluation, then a per-bar state loop for path-dependent exits. Next-bar-open fills with conservative intrabar rules, long/short/flat, fixed-fraction sizing. | Build (~300–400 lines; the most care-demanding module, with the project's hardest tests. Daily data keeps the loop fast — 2,500 bars × 27 combos is nothing) |
| `core/validation/` | CPCV splits, purging, embargoing, path reconstruction, best-IS selection rule. | **Reuse: `purgedcv`** (after the Phase-1 API spike) |
| `core/statistics/` | PSR, DSR, expected-max-SR: **reuse `purgedcv`**. PBO and MinTRL: build (small, well-specified in the papers) with tests against published examples. | Mixed |
| `core/costs/model.py` | Spread + fees + carry + square-root impact. | Build (~40 lines) |
| `core/ledger/trials.py` | SQLite trial ledger (content-hash identity) + clustered N_eff estimator + `add_manual`. | Build |
| `core/ledger/cli.py` | `ledger list`, `ledger similar "<idea text>"`, `status` — browse what you've tried, find near-duplicates, resume after weeks off without raw SQL. | Build |
| `reporting/generator.py` | Markdown audit report. | Build |
| `pipeline_runner.py` | Orchestrates Stages 2–6, off-pipeline prompt, ledger backup. | Build |
| `trials.db` | Global SQLite ledger — every trial ever run, across all hypotheses. Backed up after every run. | — |

---

## Build vs reuse — existing public repos

Verified public projects that already implement pieces of this (checked Aug 2026):

| Repo / package | What it covers | How we use it |
|---|---|---|
| [`eslazarev/purged-cross-validation`](https://github.com/eslazarev/purged-cross-validation) (`pip install purgedcv`) | Purged k-fold, embargo, walk-forward, CPCV with backtest-path reconstruction, **plus PSR and DSR**. On PyPI/conda-forge, CI, test coverage. | **Primary dependency — pending the Phase-1 API spike.** The spec needs *span-aware* purging (per-trade event ends) and an *externally supplied* trial count for DSR; generic purged-CV libraries often only take a fixed purge width. The spike confirms both before anything is built on it. Pin the version and vendor its paper-example tests into our own suite, so an upstream change can't silently move our DSR numbers. |
| [`esvhd/pypbo`](https://github.com/esvhd/pypbo) | PBO, PSR, DSR, MinTRL, MinBTL. | Reference implementation — we validate our PBO/MinTRL code against it rather than depending on it (older, thin test suite). |
| [`mnemox-ai/deflated-sharpe`](https://github.com/mnemox-ai/deflated-sharpe) (`pip install deflated-sharpe`) | DSR + related gates, zero dependencies, tested. | Fallback/cross-check for DSR numbers. |
| [`skfolio/skfolio`](https://github.com/skfolio/skfolio) | Maintained sklearn-style lib with `CombinatorialPurgedCV`. | **The named fallback if the purgedcv spike fails.** Heavier dependency; not the default. |
| `vectorbt` | Full vectorised backtesting framework. | Not used in v1 — our rule engine is deliberately thin. Escape hatch if the engine outgrows ~500 lines. |

Rule of thumb: reuse the maths that's easy to get subtly wrong (CPCV, DSR); build the parts that are the point of the project (engine, ledger, translator, report).

---

## Trial ledger & effective trials

**The ledger is the honesty mechanism.** Every parameter combination ever evaluated — including from abandoned hypotheses — is a row in `trials.db`: spec hash, human id (label), parameters, per-path post-cost out-of-sample Sharpe ratios, timestamp. Nothing is ever deleted. The DSR benchmark is computed from the *whole ledger's* effective trial count, not just the current run.

**Trial identity is a content hash, not a human label.** Identity is (SHA-256 of the canonical spec form — indicators, entry, exit, targets/stops, direction, sizing, universe — plus parameters, plus the data snapshot digest). **Canonical form is defined before Phase 1, because every ledger row depends on it:** sorted-key JSON; indicator/entry/exit expressions AST-parsed and re-unparsed so whitespace and formatting vanish; indicator names alpha-renamed to positional tokens so renaming `vol_ratio` to `vr` is the same trial; parameter grids sorted; floats in fixed format. Semantically identical specs must hash identically — otherwise formatting churn mints phantom trials and breaks the supersede mechanic exactly during the debugging phase it was built for. The human-readable id is a label only. This matters: with id-based identity, editing a spec's entry rule while keeping its id would silently *overwrite* history — a genuinely new trial replacing an old one, under-counting N and inflating DSR. Content-hash identity makes that impossible.

**Re-runs don't inflate the count.** Re-running a byte-identical spec on the same data snapshot — say, while debugging the pipeline — *supersedes* the existing rows instead of appending new ones, so iterating on the pipeline itself doesn't poison N_eff. Superseded rows are kept, flagged with `superseded_at`, never deleted — so "nothing is ever deleted" is literally true and debugging history survives. Change the rules, the parameters, or the data and it's a new trial. Every report records the ledger snapshot (row count + content hash) it was computed against.

**Effective trials: cluster, then count.** 27 near-identical parameter combos are not 27 independent tries — but a flat average correlation across a heterogeneous ledger fails in the *lenient* direction exactly when it matters most: two tight clusters of 50 near-identical trials each (uncorrelated across clusters) average out to a modest ρ̄ and a large N_eff, when the honest count is ~2. So:

1. Each trial's out-of-sample return series is stored alongside its ledger row, in a fixed format: date-indexed, daily frequency. This format is a day-one schema decision — retrofitting it after a few hundred rows is miserable.
2. Pairwise correlations are computed on **active-period returns** (bars where the strategy holds a position) — raw series are flat zeros most bars, so raw correlation measures accidental overlap of active windows, not strategy similarity. Pairs align on their date intersection; below 60 shared active bars the pair is treated as ρ = 0.
3. Trials are **hierarchically clustered** on the correlation matrix (average linkage, distance 1−ρ, cut at ρ = 0.5 — ~30 lines of scipy). Within each cluster of n_c trials with mean within-cluster correlation ρ̄_c, the effective count is 1 + (n_c − 1)(1 − ρ̄_c). **N_eff is the sum over clusters**, clamped to [1, N].

Three worked cases are pinned here so Phase-1 tests have ground truth that predates the code: (a) 100 mutually uncorrelated trials → N_eff = 100; (b) two clusters of 50 with within-cluster ρ̄ = 0.95, uncorrelated across clusters → per cluster 1 + 49×0.05 = 3.45, N_eff = 6.9; (c) one cluster of 27 with ρ̄ = 0.6 → N_eff = 1 + 26×0.4 = 11.4.

**Var[SR] is pinned too.** The E[max SR] benchmark inside DSR needs the cross-trial variance of Sharpe estimates, not just N_eff — left undefined over a ledger that mixes assets, annualisation bases, and coarse entries, it would drift silently inside the wrapped library. Definition: the variance of pipeline trials' annualised post-cost OOS Sharpes, computed on a common annualisation basis; coarse manual entries (which carry no return series) are assigned the pooled variance. The value is printed in the deflation audit.

The report shows raw N, the cluster count, and N_eff, and which one fed the DSR.

**The discipline rule (human, not code) — built to slip gracefully:** if you evaluate an idea *anywhere* — a notebook, TradingView, a spreadsheet — it goes in the ledger. The pipeline can't see what you do outside it, and unlogged trials bias every DSR in the system upward. Because per-trial manual logging *will* slip, the workflow prompts for it instead of relying on memory: the runner asks about off-pipeline experiments at every invocation, and the ledger accepts coarse entries at near-zero friction: `python -m core.ledger.add_manual "tried ~10 RSI variants on ETH"` records an estimated trial count with no return series (coarse trials count toward raw N as their own uncorrelated clusters — the strict direction). Every report carries a completeness disclosure (pipeline trials vs manually logged) and a sensitivity line ("if your true trial count were 2× the ledger, this DSR would be X") so a leaky ledger degrades the numbers visibly instead of silently.

**Backup:** `trials.db` is irreplaceable and lives in one SQLite file — a disk failure would silently reset N to zero and inflate every future DSR. The runner writes a timestamped copy to a synced folder after every run.

---

## Cost model (Stage 5)

Per round-trip, per asset. The modelled **order size is `fraction × account_equity`** (`account_equity` in `config/costs.yaml`, default $100k → $10k orders at the default 0.10 fraction), so costs and sizing describe the same trade instead of two different ones.

- **Spread cost:** half-spread × 2, from a per-asset-class table in `config/costs.yaml`. ETF spreads use **opening-auction** estimates, not day-average — next-bar-open fills happen exactly when spreads are widest (SPY/QQQ ~1 bps; IWM/EEM-class ~2–3 bps). BTC/ETH ~2–5 bps; smaller crypto ~10+ bps.
- **Fees:** flat per-side bps, priced at retail tiers on the named USD venue, not VIP tiers. **Crypto fees are a maker/taker blend, not taker-only:** a next-bar-open daily strategy is exactly the style where resting limit (maker) orders are practical, and taker-only pricing (25–60 bps/side at Coinbase/Kraken-class retail volume) would tax every crypto idea roughly double what a patient fill pays (maker 16–40 bps/side on the same venues). The blend assumes maker fills with a configurable taker-fallback fraction for gapped opens (`config/costs.yaml`). The cost-attribution section of every report prints net Sharpe at pure-maker and pure-taker, so a crypto REJECT is distinguishable from a fee-tier artifact. The tier still matters either way: a crypto idea that passes at 7 bps loses several times that live. ETF commissions ~0 at mainstream brokers.
- **Carry:** short ETF positions pay borrow fees (~25–50 bps/yr for majors); crypto shorts via perpetuals pay funding (and are flagged perp-only at translation). Long spot positions carry nothing. Per-asset-class daily carry rates live in `config/costs.yaml`. (FX rollover — the largest carry effect — left with FX in v4.)
- **Market impact:** square-root law — impact (bps) = k × σ_daily × √(order_size / ADV), with k ≈ 1, σ_daily the trailing 30-day daily volatility, ADV the 30-day average dollar volume. Impact ≈ 0 for majors at retail size — but the term exists so the model doesn't silently bless illiquid ideas.

Costs are applied to the out-of-sample CPCV paths (not just the full-sample backtest) **before Stage 6 runs**, so DSR, PBO, and the gated Sharpe are all post-cost and out-of-sample. Deflating gross returns and bolting a net-Sharpe gate on afterwards would let a high-turnover grid pass DSR on returns it can't keep after fees.

---

## Verification gates

All gates must pass. Thresholds live in `config/gates.yaml` — changing them is a config diff, visible in git history, not a silent edit. All Sharpe-based gates apply to the **selected combination's** (best-in-sample, judged out-of-sample — see Stage 4) post-cost OOS returns.

**Sharpe definition (pinned):** computed on all-bars returns (flat bars included as zeros), as the Sharpe of the **pooled** OOS path returns — not the mean of per-path Sharpes, which differs materially for sparse strategies. Per-path Sharpes are still reported, and the worst-path gate uses them. **Track length for PSR/DSR is the number of distinct calendar bars in the OOS set, never the concatenated path length** — the φ paths reuse the same blocks, so each calendar bar appears ~φ times in the pooled series, and using the concatenated length as T understates the Sharpe estimator's variance by ~√φ and inflates DSR toward false ACCEPTs.

| Stage | Gate | Threshold |
|---|---|---|
| 2: Data | Integrity checks | All pass; ≥ 8 years history (ETF) or ≥ 5 years (crypto) |
| 3: Backtest | Look-ahead audit | Truncation invariance on the raw (point-in-time-observable) series: for randomly sampled dates t, signal at t computed from data ≤ t is bit-identical to signal at t computed from the full history |
| 4: Validation | OOS trade count | ≥ 30 **unique calendar round trips** (a trade appearing in several CPCV paths counts once) — a Sharpe from 14 trades passes or fails by noise alone |
| 5: Costs | Post-cost OOS Sharpe | Pooled ≥ 1.00 |
| 5: Costs | Worst path | Minimum post-cost path Sharpe > 0 |
| 6: Deflation | Deflated Sharpe Ratio | DSR ≥ 0.95, computed on post-cost OOS returns (clustered N_eff from the full ledger) |
| 6: Deflation | Prob. of Backtest Overfitting | PBO < 0.20 |

**Reported but not gated:**

- **φ (number of OOS paths)** is derived from the CPCV config (n_blocks = 8, k = 2 → φ = 7) and reported. The old φ ≥ 5 gate was vacuous — the default config produced exactly 5.
- **MinTRL** is reported and repurposed: it is redundant as a gate (DSR ≥ 0.95 at track length T *is* T ≥ MinTRL against the same benchmark — a gate that can never independently fail is false comfort). Its natural use is as the **required paper-trading horizon before real capital** — see "After ACCEPT".
- **The live power line:** every report states "given today's ledger, the minimum post-cost OOS Sharpe that would pass all gates is X." The DSR bar rises as the ledger grows; this line makes the rising bar visible instead of silent, so a long stream of REJECTED stays interpretable — "no edge found" and "the test has no power left" are different situations and the report must distinguish them.
- **Per-year and stress-window Sharpe slices** (e.g. 2020-Q1, 2022): CPCV reshuffles blocks but can't manufacture regimes absent from the sample; the slices are the only way a long-bull artifact becomes visible before it's traded. No new gate — ~20 lines of reporting.
- **Embargo** is derived by the pipeline from `max_hold` plus a serial-correlation floor — it is not a user-editable field in the hypothesis file, where a spec author could quietly zero it out while the gate config stayed clean in git. The derived value is additionally **floored at the longest declared indicator lookback**: a 200-day MA means training features shortly after a test block are computed from test-block prices, and embargoing less than the lookback lets best-IS selection partially see the test data. If that floor consumes too much training data at the configured block count, a shorter embargo is permitted only when the planted-leak purging fixture (Phase 3) shows selection is unmoved — and the report records that justification.

These are deliberately brutal. Expected outcome for most ideas: REJECTED. That is the product working.

**Calibration probes:** once the pipeline is complete, 2–3 published benchmark rules (e.g. 12-month time-series momentum on the ETF set, 200-day MA timing on SPY) are run through it and logged as ordinary trials. The synthetic ACCEPT fixture proves the *software* can accept; the probes show where the achievable frontier of real, known strategies sits relative to the gates — which the fixture cannot. Neither touches the locked thresholds.

---

## After ACCEPT

An ACCEPT is the highest-stakes human moment the system produces — maximal temptation to bet big immediately. The protocol:

1. **Paper-trade first, for the MinTRL horizon.** The reported MinTRL is the minimum track record at which the observed edge is statistically distinguishable from zero — that is the paper-trading period, not a suggestion.
2. **Shadow log:** one markdown file per accepted idea, comparing live-forward signals and hypothetical fills against backtest expectation, updated on each signal.
3. **Pre-registered kill rule:** written into the shadow log on day one — e.g. rolling Sharpe below the MinTRL-consistent confidence band, or realised costs > 1.5× modelled. Hitting it means stop, not renegotiate.
4. **Sizing:** start at a fraction of the spec's `fraction`, scale up only after the paper period confirms fills and costs.

Edge decay is invisible until it's a drawdown unless something is watching for it. The shadow log is that something.

## After REJECT — the sanctioned iteration path

The near-miss warning (see report skeleton) forbids the obvious move — re-running variants until one clears the bar. That prohibition only works if the legitimate moves are named beside it:

- **Pre-register the family.** If you believe in the idea, write the *full* variant grid you'd ever want to try as one hypothesis, once, now. One honest trial count, no salami-slicing.
- **Re-test on genuinely new data.** The same spec, unchanged, after ~12 months of fresh out-of-sample data is a valid re-test — new data is the one thing that can't be overfit retroactively.
- **Test on an independent asset.** The same rule on an uncorrelated asset is new evidence, not a variant.

A rejection with no sanctioned next move produces either disengagement or quiet off-ledger probing — the exact corruption the ledger exists to prevent.

---

## Implementation phases

**Phase 1 — Statistics you can trust (standalone, finishable, useful alone):**
- **First task: the `purgedcv` API spike.** Confirm it accepts per-observation event-end times (trade spans) for purging and an externally supplied trial count for DSR. If either fails, switch to `skfolio` or wrap — before anything is built on it.
- Confirm its CPCV, PSR, DSR against the López de Prado paper examples; pin the version and vendor those tests.
- Build PBO and MinTRL in `core/statistics/`, unit-tested against `pypbo` and published worked examples.
- Build the trial ledger (content-hash identity, superseded rows) + clustered N_eff estimator, with tests.

**Phase 2 — Data + backtest engine:**
- `core/data/loader.py` with immutable parquet snapshots, canonical content digests, the full integrity-check list, and the documented manual spot check.
- `core/backtest/engine.py` with the **expression-free core API** (precomputed columns + boolean entry series + exit params in; returns/positions/trade-log out), so it's testable before the DSL exists.
- The look-ahead audit: a **truncation-invariance test** on raw series and a **synthetic-leak fixture** (a signal built to peek at bar t+1's return must be destroyed by next-bar-open execution). The old one-bar shift test survives only as a smoke test — slow rules like a 200-day MA barely degrade when shifted, so it can't be the gate.
- One **hand-computed golden fixture**: a ~20-bar toy series with known trades where fills, holding days, and compounded returns are verified by hand. A leak-free engine can still compute wrong returns; the leak tests can't catch accounting bugs. One fixture contains an **ex-dividend gap**, verifying the raw-space trigger / adjusted-P&L accounting at the fill boundary.
- **Wire engine runs into the ledger now, not in Phase 3.** The window where the engine works but the ledger doesn't is peak temptation for unlogged exploration — the builder's own Phase-2 tinkering must land in `trials.db` from the engine's first real run.

**Phase 3 — Orchestration:**
- `schema/hypothesis.py` with the expression whitelist parser (a thin layer over the Phase-2 engine API).
- `pipeline_runner.py`: spec → data → grid backtest → CPCV + selection rule → costs → ledger → deflation → gates. Plus the off-pipeline prompt and the ledger backup step.
- `reporting/generator.py` and `core/ledger/cli.py` (list / similar / status).
- One **planted-leak purging fixture**: a generated dataset with a leak near fold boundaries that measurably inflates OOS Sharpe when purging/embargo are disabled and disappears when they're enabled. The Stage-4 glue — span-aware purging, straddling-trade exclusion, best-IS selection, path concatenation — is bespoke wiring whose failure is silent (wrong output looks identical to right output), so the wiring gets its own fixture, not just the library.
- One **synthetic ACCEPT fixture**: a rule with a known planted edge in generated data, run end-to-end **against its own pinned, seeded ledger** — so it stays deterministic forever instead of rotting as the real ledger grows. Without it, "everything is REJECTED" is indistinguishable from a gate wired wrong.
- A scheduled variant of the fixture runs against a **copy of the current live ledger** and the report notes the last date it still passed — the honest, ongoing version of "the pipeline can still accept."
- Run the **calibration probes** (published benchmark rules) once the pipeline is complete; they're logged as ordinary trials.

**Phase 4 — The translator (last, because everything works without it):**
- `core/agent/translator.py`: idea text → spec JSON → plain-English restatement → **locally computed** signal preview (fire count, ~5 example dates/prices, 2–3 simulated full trades with exit reasons, no P&L; every preview appends a coarse ledger row) → ledger similarity check → grid-size norms (warn > 50, flag > 200) → user confirms → saved to `hypotheses/`, stamped with model id + prompt version.
- 5–10 **golden idea→spec fixtures**, so model drift on an upgrade is detectable before a bad spec gets confirmed.

Each phase ends runnable and tested. If the project pauses for a month after any phase, what exists still works and is still useful on its own.

---

## End-to-end example

```bash
# 1. Translate a vague idea (Phase 4; before that, write the JSON by hand)
python -m core.agent.translator --idea "Buy BTC after 3 consecutive down days if it's above the 200-day MA, sell after 5 days or +8%."
# → prints interpretation + locally computed signal preview:
#   "Fired 14 times in 8 years. Examples: 2023-08-17 ($26,600), 2024-04-19 ($63,900), ...
#    Sample trades: 2023-08-17 → 2023-08-22 (max_hold, 5 days); 2024-04-19 → 2024-04-21 (profit_target, 2 days), ..."
# → coarse ledger row appended for this preview (confirmed or not)
# → "No similar prior hypotheses in the ledger."
# → asks to confirm, writes hypotheses/BTC-DIP-001.json
# → prints: "Grid size: 36 combinations. These will be logged as 36 trials. Proceed?"

# 2. Run the pipeline
python pipeline_runner.py --spec hypotheses/BTC-DIP-001.json
# → "Any off-pipeline experiments since your last run? [y/N]"

# 3. Read the verdict
cat reports/BTC-DIP-001_audit.md

# Anytime: where am I?
python -m core.ledger.cli status
```

### Example report skeleton (`BTC-DIP-001_audit.md`)

- **Hypothesis:** plain-English restatement + the exact rules tested + translator model/prompt version.
- **Verdict:** ACCEPTED / REJECTED, with the first failed gate named. Near-miss rejections (any gate failed by a hair) carry an explicit warning: *re-running variants of this idea until it clears the bar is exactly the overfitting the ledger will penalise* — followed immediately by the **sanctioned alternatives** (pre-register the family; re-test on new data in 12 months; try an independent asset). The most engaged user must not be steered toward the most dangerous behaviour, and must not be left with no legitimate move.
- **Gate table:** all 7 gates, threshold vs observed, PASS/FAIL, plus the selected combination and how it was selected.
- **CPCV path distribution:** pooled and per-path post-cost Sharpe (mean/min/max across φ = 7 paths), max drawdown distribution.
- **Regime slices:** per-calendar-year Sharpe and stress windows (2020-Q1, 2022).
- **Deflation audit:** raw N, cluster count, N_eff, ledger-wide trial count, ledger snapshot (rows + hash), data snapshot digest, the pinned Var[SR], E[max SR] under the null, DSR, PBO, MinTRL (reported; = required paper-trade horizon), the sensitivity line ("if your true trial count were 2× the ledger, this DSR would be X"), and the **live power line** ("the minimum post-cost OOS Sharpe that would pass today's ledger is X").
- **Cost attribution:** gross vs net Sharpe, bps lost to spread/fees/carry/impact, and (crypto) net Sharpe at pure-maker vs pure-taker fees.
- **Trajectory:** metrics that move every run — cumulative hypotheses tested and killed, total trials and N_eff, best DSR so far, and an estimated "capital not lost to a false edge" line. A clean rejection is the deliverable (an idea killed cheaply, money saved); best-DSR-alone flatlines for months and reads as futility, so the counters that visibly increment carry the progress framing.
- **ACCEPT-fixture health:** last date the planted-edge fixture still passed against a copy of the live ledger.
- **Ledger completeness disclosure:** pipeline trials vs manually logged entries; unlogged experiments bias DSR upward.
- **Disclosure line:** fixed selection-bias note (all universes — today's crypto majors and mega-AUM ETFs are survivors).
- **If ACCEPTED:** the post-ACCEPT protocol, pre-filled — paper-trade horizon (= MinTRL), shadow-log path, kill rule template.


**Deliberate owner decisions (do not "fix" these when reviewing):**
- The gates are brutal on purpose (DSR ≥ 0.95, PBO < 0.20, post-cost OOS Sharpe ≥ 1.0). Most ideas are false; frequent REJECTED verdicts are the product working, not a calibration error. The live power line and calibration probes exist to keep that interpretable, not to soften it.
- The AI translator stays despite being a convenience layer, because the owner wants to feed in vague ideas. It is last in the build order and everything runs without it.
- FX is out until a broker-consistent data source justifies re-adding it.
- This is a personal trading-research project, built by a capable beginner

