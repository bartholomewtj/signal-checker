"""Render last_run.json into a presentable one-page report."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import matplotlib.dates as mdates

HERE = Path(__file__).resolve().parent
OUT = HERE / "reports"
OUT.mkdir(exist_ok=True)

VERDICT_COLOR = {
    "LOOKS REAL": "#15803d",
    "NOT PROVEN": "#b45309",
    "NO EDGE": "#b91c1c",
    "NO EDGE FOUND": "#b91c1c",
}

CAPTION = (
    "Blue is the idea traded blind: settings are picked on past data, then "
    "the next stretch is traded without peeking. Grey is just holding Bitcoin "
    "over the same window. If blue finishes under grey, sitting still won."
)


def _ok(c):
    v = c.get("ok")
    return v is True or str(v).lower() == "true"


def _series(points):
    xs, ys = [], []
    for p in points or []:
        try:
            xs.append(datetime.strptime(str(p["t"])[:10], "%Y-%m-%d"))
            ys.append(float(p["v"]))
        except (KeyError, ValueError, TypeError):
            continue
    return xs, ys


def _idx100(ys):
    if not ys:
        return ys
    return [100.0 * y / ys[0] for y in ys]


def _fmt(v, nd=2, pct=False, signed=False):
    if v is None:
        return "—"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    if pct:
        s = f"{x:+.{nd}f}%" if signed else f"{x:.{nd}f}%"
        return s
    return f"{x:.{nd}f}"


def main():
    data = json.loads((HERE / "last_run.json").read_text(encoding="utf-8"))
    name = f"{data.get('strategy', '?')}  ·  BTC {data.get('timeframe', '?')}"
    verdict = (data.get("verdict") or "?").replace(" FOUND", "")
    vcol = VERDICT_COLOR.get(data.get("verdict") or verdict, "#334155")
    direction = data.get("direction") or ""
    preview = "Preview, not on the ledger" if data.get("preview") else "Logged trial"

    xw, yw = _series(data.get("wf_equity"))
    xb, yb = _series(data.get("bh_equity"))
    yw100, yb100 = _idx100(yw), _idx100(yb)

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.spines.top": False,
        "axes.spines.right": False,
    })
    fig = plt.figure(figsize=(12.2, 8.6), facecolor="#ffffff")
    gs = fig.add_gridspec(
        5, 4, height_ratios=[0.42, 2.55, 0.38, 0.55, 1.15],
        hspace=0.22, wspace=0.18,
        left=0.07, right=0.97, top=0.93, bottom=0.06,
    )

    ax_head = fig.add_subplot(gs[0, :])
    ax_head.set_axis_off()
    ax_head.set_xlim(0, 1)
    ax_head.set_ylim(0, 1)
    ax_head.text(0, 0.72, name, fontsize=18, fontweight="bold", color="#0f172a", va="center")
    ax_head.text(0, 0.18, f"{direction}   ·   {preview}", fontsize=11, color="#64748b", va="center")
    pill = FancyBboxPatch((0.78, 0.22), 0.20, 0.58, boxstyle="round,pad=0.02,rounding_size=0.08",
                          facecolor=vcol, edgecolor="none", transform=ax_head.transAxes)
    ax_head.add_patch(pill)
    ax_head.text(0.88, 0.51, verdict, fontsize=12, fontweight="bold", color="white",
                 ha="center", va="center", transform=ax_head.transAxes)

    ax = fig.add_subplot(gs[1, :])
    ax.set_facecolor("#f8fafc")
    if xb:
        ax.plot(xb, yb100, color="#94a3b8", lw=2.0, label="Buy and hold Bitcoin")
        ax.annotate(f"{yb100[-1]:.0f}", xy=(xb[-1], yb100[-1]), xytext=(6, 0),
                    textcoords="offset points", color="#64748b", fontsize=10, va="center")
    if xw:
        ax.plot(xw, yw100, color="#4f46e5", lw=2.4, label="This idea, walk-forward")
        ax.annotate(f"{yw100[-1]:.0f}", xy=(xw[-1], yw100[-1]), xytext=(6, 0),
                    textcoords="offset points", color="#4f46e5", fontsize=10, fontweight="bold", va="center")
    ax.axhline(100, color="#cbd5e1", lw=1, ls="--")
    ax.set_ylabel("Growth of $100")
    ax.legend(frameon=False, loc="upper left", fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.grid(True, axis="y", color="#e2e8f0", lw=1)
    ax.tick_params(colors="#475569", labelsize=9)
    for sp in ax.spines.values():
        sp.set_color("#e2e8f0")

    ax_cap = fig.add_subplot(gs[2, :])
    ax_cap.set_axis_off()
    ax_cap.text(0, 0.55, CAPTION, fontsize=10.5, color="#334155", va="center", wrap=True)

    metrics = [
        ("Walk-forward return", _fmt(data.get("wf_return_pct"), 1, pct=True, signed=True)),
        ("Profit factor", _fmt(data.get("wf_pf"), 2)),
        ("Sharpe", _fmt(data.get("wf_sharpe"), 2)),
        ("Trades", str(data.get("wf_trades") if data.get("wf_trades") is not None else "—")),
        ("Buy & hold", _fmt(data.get("wf_bh_pct"), 1, pct=True, signed=True)),
    ]
    for i, (lab, val) in enumerate(metrics):
        axm = fig.add_subplot(gs[3, i] if i < 4 else gs[3, 3])
        if i == 4:
            # fifth metric shares last cell — skip extra axes, put 5 in a row via gs[3,:]
            axm.set_axis_off()
            continue
        axm.set_axis_off()

    ax_row = fig.add_subplot(gs[3, :])
    ax_row.set_axis_off()
    ax_row.set_xlim(0, 5)
    ax_row.set_ylim(0, 1)
    for i, (lab, val) in enumerate(metrics):
        ax_row.text(i + 0.08, 0.68, lab.upper(), fontsize=8, color="#64748b", va="center")
        ax_row.text(i + 0.08, 0.22, val, fontsize=16, fontweight="bold", color="#0f172a", va="center")

    ax_bot = fig.add_subplot(gs[4, :])
    ax_bot.set_axis_off()
    ax_bot.set_xlim(0, 1)
    ax_bot.set_ylim(0, 1)

    checks = data.get("checks") or []
    ax_bot.text(0, 0.92, "HONESTY GATES", fontsize=8, color="#64748b", fontweight="bold")
    x = 0.0
    for c in checks:
        passed = _ok(c)
        col = "#15803d" if passed else "#b91c1c"
        label = ("Pass  " if passed else "Fail  ") + (c.get("name") or "")
        ax_bot.text(x, 0.72, label, fontsize=9, color=col, fontweight="medium")
        x += 0.25

    p_is, p_wf = data.get("p_is"), data.get("p_wf")
    ax_bot.text(
        0, 0.52,
        f"Shuffle tests  ·  in-sample p = {_fmt(p_is, 3)}    walk-forward p = {_fmt(p_wf, 3)}"
        "    (needs p < 0.05 to beat noise)",
        fontsize=9.5, color="#334155",
    )

    folds = data.get("folds") or []
    if folds:
        ax_bot.text(0, 0.32, "WALK-FORWARD FOLDS", fontsize=8, color="#64748b", fontweight="bold")
        parts = []
        for f in folds:
            start = f.get("test_start") or f.get("from") or ""
            pf = _fmt(f.get("pf"), 2)
            tr = f.get("trades")
            parts.append(f"{start}   PF {pf}   {tr} trades")
        ax_bot.text(0, 0.14, "    ·    ".join(parts), fontsize=9.5, color="#0f172a")

    s1 = data.get("stage1") or {}
    ax_bot.text(
        0, -0.02,
        "Stage 1 (ignore this number): "
        f"ret {_fmt(s1.get('return_pct'), 1, pct=True, signed=True)}   "
        f"BH {_fmt(s1.get('bh_pct'), 0, pct=True)}   "
        f"PF {_fmt(s1.get('pf'), 2)}   "
        f"max DD {_fmt(s1.get('max_dd'), 1, pct=True)}   "
        f"{s1.get('trades')} trades   "
        f"best in-sample {data.get('best_params')}",
        fontsize=8.5, color="#94a3b8",
    )

    out = OUT / "last_report.png"
    named = OUT / f"{data.get('strategy','idea')}_{data.get('timeframe','tf')}.png"
    fig.savefig(out, dpi=160, facecolor=fig.get_facecolor())
    fig.savefig(named, dpi=160, facecolor=fig.get_facecolor())
    print(out)
    print(named)


if __name__ == "__main__":
    main()
