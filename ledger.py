"""Read-only view of trials.csv.

    python ledger.py status   # N, Bonferroni bar, last full verdict per pair
    python ledger.py list     # every row
"""

from __future__ import annotations

import argparse
import csv
import sys

from check import LEDGER, count_trials


def _rows(path=None):
    path = path or LEDGER
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except FileNotFoundError:
        return []


def last_full_by_pair(rows):
    """Last mode=full row per (strategy, timeframe), in first-seen order."""
    last = {}
    order = []
    for row in rows:
        if row.get("mode") != "full":
            continue
        key = (row.get("strategy"), row.get("timeframe"))
        if key not in last:
            order.append(key)
        last[key] = row
    return [(key, last[key]) for key in order]


def format_status(rows, path=None):
    n = count_trials(path)
    bar = 0.05 / n if n else 0.05
    lines = [
        f"N = {n} distinct (strategy, timeframe) pairs with mode=full",
        f"Bonferroni bar = {bar:.4f}   (0.05 / {n or 1})",
        "",
        "Last full verdict per pair:",
    ]
    pairs = last_full_by_pair(rows)
    if not pairs:
        lines.append("  (none)")
        return "\n".join(lines)
    for (strategy, timeframe), row in pairs:
        lines.append(
            f"  {strategy} {timeframe}  {row.get('verdict', '')}  "
            f"p_is={row.get('p_insample', '')}  "
            f"p_wf={row.get('p_walkforward', '')}  "
            f"PF={row.get('wf_pf', '')}"
        )
    return "\n".join(lines)


def format_list(rows):
    if not rows:
        return "(empty ledger)"
    cols = ["timestamp", "mode", "strategy", "timeframe", "direction", "verdict"]
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    body = [
        "  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols)
        for r in rows
    ]
    return "\n".join([header, *body])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only trials.csv viewer")
    parser.add_argument("cmd", choices=["status", "list"])
    parser.add_argument("--ledger", default=None, help="path to trials.csv")
    args = parser.parse_args(argv)
    path = args.ledger or LEDGER
    rows = _rows(path)
    if args.cmd == "status":
        print(format_status(rows, path))
    else:
        print(format_list(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
