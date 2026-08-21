"""HTML visual of a check.py run.

After stages 1-4 finish, check.py writes last_run.html and opens it.
The page leads with the verdict. Walk-forward equity and shuffle
histograms are evidence. Stage 1 numbers sit at the bottom, muted,
because that curve is the one that lies.

No extra dependencies. The file is self-contained (inline SVG).
"""

from __future__ import annotations

import html
import math
import os
import sys
import webbrowser
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATH = os.path.join(HERE, "last_run.html")

# data recipe from style/tokens.md
_CSS = """
:root {
  --paper: #0e1821;
  --ink: #f0f7fc;
  --muted: #8ba2b8;
  --accent: #2dd4bf;
  --warn: #fb7185;
  --ok: #4ade80;
  --navy: #818cf8;
  --accent-soft: #143a3d;
  --warn-soft: #392833;
  --ok-soft: #193c32;
  --navy-soft: #232d48;
  --card: #162533;
  --cage: #111d28;
  --line: #374048;
  --boxline: #465665;
}
* { box-sizing: border-box; margin: 0; }
body {
  background: var(--paper);
  color: var(--ink);
  font: 13px/1.45 "Segoe UI", system-ui, sans-serif;
  padding: 24px 20px 48px;
}
.page { max-width: 1120px; margin: 0 auto; }
.meta {
  color: var(--muted);
  font-size: 13px;
  margin-bottom: 14px;
}
.meta strong { color: var(--ink); font-weight: 650; }
.flag {
  display: inline-block;
  margin-left: 8px;
  padding: 1px 8px;
  border-radius: 99px;
  border: 1px solid var(--boxline);
  color: var(--muted);
  font-size: 12px;
}
.verdict.you {
  background: var(--accent-soft);
  border: 2px solid var(--accent);
  border-radius: 12px;
  padding: 20px 24px 18px;
  margin-bottom: 16px;
}
.verdict .word {
  font: 700 34px/1.1 "Segoe UI", system-ui, sans-serif;
  color: var(--ink);
  letter-spacing: -0.02em;
}
.verdict .blurb {
  color: var(--muted);
  margin-top: 8px;
  max-width: 52em;
}
.chip {
  display: inline-block;
  margin-top: 10px;
  padding: 2px 10px;
  border-radius: 99px;
  font: 12px/1.4 "Segoe UI", sans-serif;
  background: var(--warn-soft);
  color: var(--warn);
  border: 1px solid var(--warn);
}
.gates {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}
.gate {
  background: var(--card);
  border: 2px solid var(--line);
  border-radius: 12px;
  padding: 12px 14px;
}
.gate.pass { border-color: var(--ok); background: var(--ok-soft); }
.gate.fail { border-color: var(--warn); background: var(--warn-soft); }
.gate .stamp {
  font: 650 11px/1 "Segoe UI", sans-serif;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
}
.gate.pass .stamp { color: var(--ok); }
.gate.fail .stamp { color: var(--warn); }
.gate .name { margin-top: 6px; color: var(--ink); }
.gate .val {
  margin-top: 4px;
  font: 12px/1.3 Consolas, "Courier New", monospace;
  color: var(--muted);
}
.row {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 10px;
  margin-bottom: 16px;
}
.panel {
  background: var(--card);
  border: 2px solid var(--ink);
  border-radius: 12px;
  padding: 12px 14px 8px;
}
.panel h2 {
  font: 650 13px/1.3 "Segoe UI", sans-serif;
  color: var(--muted);
  margin: 0 0 8px;
}
svg { width: 100%; height: auto; display: block; }
.legend {
  display: flex;
  gap: 14px;
  color: var(--muted);
  font-size: 12px;
  margin: 4px 0 6px;
}
.swatch {
  display: inline-block;
  width: 12px; height: 2px;
  vertical-align: middle;
  margin-right: 5px;
}
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td {
  text-align: right;
  padding: 6px 8px;
  border-top: 1px solid var(--line);
  font-variant-numeric: tabular-nums;
}
th {
  color: var(--muted);
  font-weight: 500;
  border-top: none;
  text-align: right;
}
th:first-child, td:first-child { text-align: left; }
td.mono, .mono { font-family: Consolas, "Courier New", monospace; font-size: 12px; }
td.pos { color: var(--ok); } td.neg { color: var(--warn); }
.stage1 {
  background: var(--cage);
  border: 1.5px dashed var(--boxline);
  border-radius: 12px;
  padding: 12px 14px;
  color: var(--muted);
}
.stage1 h2 { color: var(--muted); font: 650 13px/1.3 "Segoe UI", sans-serif; margin-bottom: 8px; }
.stage1 .nums {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
}
.stage1 .k { font-size: 12px; }
.stage1 .v { font: 12px/1.3 Consolas, "Courier New", monospace; color: var(--ink); }
.footnote { color: var(--muted); font-size: 12px; margin-top: 14px; }
@media (max-width: 800px) {
  .gates, .row { grid-template-columns: 1fr 1fr; }
  .verdict .word { font-size: 26px; }
}
@media (max-width: 520px) {
  .gates, .row { grid-template-columns: 1fr; }
}
"""


_BLURB = {
    "LOOKS REAL": (
        "All four gates passed. Worth paper-trading. Still not a guarantee "
        "— markets change."
    ),
    "NOT PROVEN": (
        "Some evidence, but you would not want to risk money on this. "
        "Treat it as an idea, not an edge."
    ),
    "NO EDGE": (
        "The backtest result is consistent with luck."
    ),
}


def _esc(x):
    return html.escape("" if x is None else str(x), quote=True)


def _finite(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def _fmt(x, digits=2, pct=False):
    v = _finite(x)
    if v is None:
        if isinstance(x, float) and math.isinf(x):
            return "inf"
        return "–"
    if pct:
        return f"{v:.{digits}f}%"
    return f"{v:.{digits}f}"


def _axis_num(v):
    """Short y-axis label. Keep it inside a ~48px left gutter."""
    av = abs(v)
    if av >= 1_000_000:
        return f"{v / 1e6:.1f}m"
    if av >= 10_000:
        return f"{v / 1000:.0f}k"
    if av >= 1000:
        return f"{v:,.0f}"
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _parse_t(t):
    s = str(t)[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").timestamp()
    except ValueError:
        return None


def _line_svg(series, w=640, h=220, pad_l=44, pad_t=16, pad_r=16, pad_b=28):
    """One or more named polylines sharing a time axis.

    series: list of {name, color, points: [{t, v}, ...]}
    """
    pts_all = []
    parsed = []
    for s in series:
        pts = []
        for p in s.get("points") or []:
            ts = _parse_t(p.get("t"))
            v = _finite(p.get("v"))
            if ts is None or v is None:
                continue
            pts.append((ts, v))
        parsed.append((s, pts))
        pts_all.extend(pts)
    if not pts_all:
        return '<p class="footnote">No walk-forward equity to plot.</p>'
    xs = [p[0] for p in pts_all]
    ys = [p[1] for p in pts_all]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if xmax <= xmin:
        xmax = xmin + 1
    if ymax <= ymin:
        ymax = ymin + 1
    ymax += (ymax - ymin) * 0.06
    iw = w - pad_l - pad_r
    ih = h - pad_t - pad_b

    def xy(ts, v):
        x = pad_l + (ts - xmin) / (xmax - xmin) * iw
        y = pad_t + (1 - (v - ymin) / (ymax - ymin)) * ih
        return x, y

    parts = [
        f'<svg viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="Walk-forward equity versus buy and hold">'
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="#162533"/>'
    ]
    for frac in (0.25, 0.5, 0.75):
        y = pad_t + frac * ih
        parts.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w - pad_r}" y2="{y:.1f}" '
            f'stroke="#374048" stroke-width="1"/>'
        )
    for s, pts in parsed:
        if len(pts) < 2:
            continue
        d = " ".join(f"{xy(ts, v)[0]:.1f},{xy(ts, v)[1]:.1f}" for ts, v in pts)
        parts.append(
            f'<polyline fill="none" stroke="{s["color"]}" '
            f'stroke-width="2" points="{d}"/>'
        )
    parts.append(
        f'<text x="{pad_l - 6}" y="{pad_t + 4}" fill="#8ba2b8" '
        f'font-family="Consolas,monospace" font-size="11" '
        f'text-anchor="end">{_esc(_axis_num(ymax))}</text>'
    )
    parts.append(
        f'<text x="{pad_l - 6}" y="{h - pad_b}" fill="#8ba2b8" '
        f'font-family="Consolas,monospace" font-size="11" '
        f'text-anchor="end">{_esc(_axis_num(ymin))}</text>'
    )
    t0 = datetime.fromtimestamp(xmin).strftime("%Y-%m-%d")
    t1 = datetime.fromtimestamp(xmax).strftime("%Y-%m-%d")
    parts.append(
        f'<text x="{pad_l}" y="{h - 8}" fill="#8ba2b8" '
        f'font-family="Consolas,monospace" font-size="11">{t0}</text>'
    )
    parts.append(
        f'<text x="{w - pad_r}" y="{h - 8}" fill="#8ba2b8" '
        f'font-family="Consolas,monospace" font-size="11" '
        f'text-anchor="end">{t1}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def _hist_svg(scores, real, label, w=640, h=180, pad_l=16, pad_t=22, pad_r=16, pad_b=22):
    finite = [_finite(s) for s in (scores or [])]
    finite = [s for s in finite if s is not None]
    real_v = _finite(real)
    if not finite and real_v is None:
        return f'<p class="footnote">No shuffle scores for {_esc(label)}.</p>'
    lo = min(finite) if finite else (real_v or 0)
    hi = max(finite) if finite else (real_v or 1)
    if real_v is not None:
        lo = min(lo, real_v)
        hi = max(hi, real_v)
    if hi <= lo:
        hi = lo + 1
    span = hi - lo
    lo -= span * 0.06
    hi += span * 0.06
    n = len(finite)
    bins = 6 if n < 15 else 10 if n < 40 else 16
    counts = [0] * bins
    for s in finite:
        i = int((s - lo) / (hi - lo) * bins)
        i = min(max(i, 0), bins - 1)
        counts[i] += 1
    peak = max(counts) if max(counts) else 1
    iw = w - pad_l - pad_r
    ih = h - pad_t - pad_b
    bw = iw / bins
    parts = [
        f'<svg viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="Shuffle scores for {html.escape(label)}">'
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="#162533"/>'
    ]
    for i, c in enumerate(counts):
        bh = (c / peak) * ih
        x = pad_l + i * bw
        y = pad_t + ih - bh
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(bw - 1.5, 0.5):.1f}" '
            f'height="{bh:.1f}" fill="#3e497b"/>'
        )
    if real_v is not None:
        x = pad_l + (real_v - lo) / (hi - lo) * iw
        parts.append(
            f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{pad_t + ih}" '
            f'stroke="#2dd4bf" stroke-width="2"/>'
        )
        anchor = "end" if x > w * 0.75 else "start" if x < w * 0.25 else "middle"
        parts.append(
            f'<text x="{x:.1f}" y="{pad_t - 6}" fill="#2dd4bf" '
            f'font-family="Consolas,monospace" font-size="11" '
            f'text-anchor="{anchor}">real {_fmt(real_v, 2)}</text>'
        )
    parts.append(
        f'<text x="{pad_l}" y="{h - 6}" fill="#8ba2b8" '
        f'font-family="Consolas,monospace" font-size="11">{_fmt(lo, 2)}</text>'
    )
    parts.append(
        f'<text x="{w - pad_r}" y="{h - 6}" fill="#8ba2b8" '
        f'font-family="Consolas,monospace" font-size="11" '
        f'text-anchor="end">{_fmt(hi, 2)}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def _gates_html(checks):
    if not checks:
        return ""
    cells = []
    for c in checks:
        ok = bool(c.get("ok"))
        cls = "pass" if ok else "fail"
        stamp = "Pass" if ok else "Fail"
        cells.append(
            f'<div class="gate {cls}">'
            f'<div class="stamp">{stamp}</div>'
            f'<div class="name">{_esc(c.get("name") or c.get("label"))}</div>'
            f'<div class="val">{_esc(c.get("detail") or "")}</div>'
            f"</div>"
        )
    return f'<div class="gates">{"".join(cells)}</div>'


def _folds_html(folds):
    if not folds:
        return ""
    rows = []
    for f in folds:
        pf = _finite(f.get("pf"))
        pf_cls = "pos" if pf is not None and pf > 1 else "neg"
        params = f.get("params") or {}
        if isinstance(params, dict):
            param_s = ", ".join(f"{k}={v}" for k, v in params.items())
        else:
            param_s = str(params)
        rows.append(
            f'<tr>'
            f'<td class="mono">{_esc(f.get("test_start"))}</td>'
            f'<td class="mono">{_esc(param_s)}</td>'
            f'<td class="mono {pf_cls}">{_fmt(f.get("pf"), 2)}</td>'
            f'<td class="mono">{_esc(f.get("trades"))}</td>'
            f"</tr>"
        )
    return (
        '<div class="panel" style="margin-bottom:16px">'
        "<h2>Walk-forward folds</h2>"
        "<table><thead><tr>"
        "<th>Test from</th><th>Params</th><th>PF</th><th>Trades</th>"
        "</tr></thead><tbody>"
        f"{''.join(rows)}</tbody></table></div>"
    )


def render(result):
    """Return a full HTML document for one check.py result dict."""
    strategy = _esc(result.get("strategy", "?"))
    timeframe = _esc(result.get("timeframe", "?"))
    direction = _esc(result.get("direction", ""))
    verdict = result.get("verdict") or "?"
    preview = bool(result.get("preview"))
    flag = (
        '<span class="flag">display only — not on the ledger</span>'
        if preview
        else '<span class="flag">logged trial</span>'
    )
    window = _esc(result.get("window") or "")
    blurb = _BLURB.get(verdict, "")
    provisional = result.get("provisional")
    chip = (
        f'<div class="chip">{_esc(provisional)}</div>' if provisional else ""
    )

    wf_pts = result.get("wf_equity") or []
    bh_pts = result.get("bh_equity") or []
    equity_svg = _line_svg([
        {"name": "walk-forward", "color": "#818cf8", "points": wf_pts},
        {"name": "buy and hold", "color": "#8ba2b8", "points": bh_pts},
    ])

    hist_is = _hist_svg(
        result.get("perm_is") or [], result.get("is_pf"),
        "in-sample profit factor",
    )
    hist_wf = _hist_svg(
        result.get("perm_wf") or [], result.get("wf_pf"),
        "walk-forward profit factor",
    )

    s1 = result.get("stage1") or {}
    footnote_bits = []
    if preview:
        n_after = result.get("n_after")
        bar = result.get("corrected_bar")
        if n_after and bar:
            footnote_bits.append(
                f"If you log this pair, N becomes {n_after} and the "
                f"Bonferroni bar becomes {_fmt(bar, 4)}."
            )
    else:
        n_trials = result.get("n_trials")
        bar = result.get("corrected_bar")
        if n_trials and bar:
            footnote_bits.append(
                f"N = {n_trials} distinct pairs. Bonferroni bar = "
                f"{_fmt(bar, 4)} (0.05 / {n_trials}). "
                f"In-sample p={_fmt(result.get('p_is'), 4)}; "
                f"walk-forward p={_fmt(result.get('p_wf'), 4)}."
            )
    footnote = (
        f'<p class="footnote">{_esc(" ".join(footnote_bits))}</p>'
        if footnote_bits else ""
    )

    wf_stats = (
        f'<span class="mono">OOS {_fmt(result.get("wf_return_pct"), 1, pct=True)}'
        f' · PF {_fmt(result.get("wf_pf"), 3)}'
        f' · Sharpe {_fmt(result.get("wf_sharpe"), 2)}'
        f' · {result.get("wf_trades", "–")} trades'
        f' · buy and hold {_fmt(result.get("wf_bh_pct"), 1, pct=True)}</span>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>signal-check · {strategy} {timeframe}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="page">
  <p class="meta">
    <strong>signal-check</strong>
    · {strategy} {timeframe} · {direction}
    {flag}
    <br>{window}
  </p>

  <div class="verdict you">
    <div class="word">{_esc(verdict)}</div>
    <p class="blurb">{_esc(blurb)}</p>
    {chip}
  </div>

  {_gates_html(result.get("checks") or [])}

  <div class="row">
    <div class="panel">
      <h2>Walk-forward equity vs buy and hold</h2>
      <div class="legend">
        <span><span class="swatch" style="background:#818cf8"></span>walk-forward</span>
        <span><span class="swatch" style="background:#8ba2b8"></span>buy and hold</span>
      </div>
      {equity_svg}
      <p class="footnote">{wf_stats}</p>
    </div>
    <div class="panel">
      <h2>Shuffle scores. The line is this idea. Bars are noise.</h2>
      <p class="footnote">In-sample · p={_fmt(result.get("p_is"), 3)}</p>
      {hist_is}
      <p class="footnote">Walk-forward · p={_fmt(result.get("p_wf"), 3)}</p>
      {hist_wf}
    </div>
  </div>

  {_folds_html(result.get("folds") or [])}

  <div class="stage1">
    <h2>Stage 1 — this number proves nothing</h2>
    <div class="nums">
      <div><div class="k">Return</div>
        <div class="v">{_fmt(s1.get("return_pct"), 1, pct=True)}</div></div>
      <div><div class="k">Buy and hold</div>
        <div class="v">{_fmt(s1.get("bh_pct"), 1, pct=True)}</div></div>
      <div><div class="k">Profit factor</div>
        <div class="v">{_fmt(s1.get("pf"), 3)}</div></div>
      <div><div class="k">Max drawdown</div>
        <div class="v">{_fmt(s1.get("max_dd"), 1, pct=True)}</div></div>
      <div><div class="k">Trades</div>
        <div class="v">{_esc(s1.get("trades"))}</div></div>
      <div><div class="k">Best in-sample params</div>
        <div class="v">{_esc(result.get("best_params"))}</div></div>
    </div>
  </div>
  {footnote}
</div>
</body>
</html>
"""


def write(result, path=None):
    """Write last_run.html (or `path`) and return the path."""
    path = path or DEFAULT_PATH
    html_out = render(result)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html_out)
    return path


def open_in_browser(path):
    """Open a local HTML file. Failures are silent — the path is enough."""
    try:
        uri = "file:///" + os.path.abspath(path).replace("\\", "/")
        webbrowser.open(uri)
    except Exception:
        pass


def points_from_series(series, n=400):
    """Downsample a pandas Series of equity (or any values) to [{t, v}]."""
    if series is None or len(series) == 0:
        return []
    step = max(1, len(series) // n)
    idxs = list(range(0, len(series), step))
    if idxs[-1] != len(series) - 1:
        idxs.append(len(series) - 1)
    out = []
    for i in idxs:
        ts = series.index[i]
        fv = _finite(series.iloc[i])
        if fv is None:
            continue
        t = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        out.append({"t": t, "v": fv})
    return out


def main(path=None):
    """Reopen last_run.html. Exit 1 if check.py has not written one yet."""
    path = path or DEFAULT_PATH
    if not os.path.exists(path):
        print(
            "No last_run.html yet. Run: just check <strategy> <timeframe>",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(path)
    open_in_browser(path)


if __name__ == "__main__":
    main()
