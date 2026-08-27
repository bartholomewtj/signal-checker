"""Append today's DEVMA long-only 1d position to the forward log.

Not a ledger row. Does not run check.py, does not shuffle, does not
touch the holdout year. Same snapshot the dashboard uses.

    python log_devma.py
    just log-devma

A second run on the same last candle is a no-op.
"""

import csv
import os
from datetime import datetime, timezone

import dashboard

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "forward", "devma_lo_1d.csv")
FIELDS = ["logged_at_utc", "last_candle", "position", "strategy",
          "symbol", "timeframe"]


def _rows():
    if not os.path.exists(LOG):
        return []
    with open(LOG, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def append_if_new(snapshot):
    """Write one row unless this last_candle is already logged. Return the row."""
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    existing = _rows()
    if any(r.get("last_candle") == snapshot["last_candle"] for r in existing):
        return None
    row = {
        "logged_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_candle": snapshot["last_candle"],
        "position": snapshot["position"],
        "strategy": snapshot["strategy"],
        "symbol": snapshot["symbol"],
        "timeframe": snapshot["timeframe"],
    }
    new_file = not os.path.exists(LOG) or os.path.getsize(LOG) == 0
    with open(LOG, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(row)
    return row


def main():
    snap = dashboard.position_snapshot("devma_lo", "BTC/USDT", "1d")
    row = append_if_new(snap)
    if row is None:
        print(f"already logged {snap['last_candle']} {snap['position']}")
        return
    print(f"logged {row['last_candle']} {row['position']}")


if __name__ == "__main__":
    main()
