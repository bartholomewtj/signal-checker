"""Create shuffled ("permuted") copies of a price series.

This is the heart of the honesty test. A permuted series keeps every
individual bar's shape (its gap from the prior close, and where its high,
low and close sit relative to its open) but shuffles the *order* of those
movements. The result: same overall drift and volatility, but any real
repeating pattern is destroyed.

If a strategy makes as much money on shuffled prices as on real prices,
its "edge" was noise.

Method follows Timothy Masters' bar-permutation approach, as implemented
in github.com/neurotrader888/mcpt.
"""

import numpy as np
import pandas as pd


def permute_bars(df, start_index=0, rng=None):
    """Return a shuffled copy of an OHLC DataFrame.

    Bars up to and including `start_index` are kept as-is (real data).
    Everything after is rebuilt from shuffled movements.
    """
    if rng is None:
        rng = np.random.default_rng()

    n = len(df)
    log_prices = np.log(df[["Open", "High", "Low", "Close"]].to_numpy())
    o, h, l, c = log_prices[:, 0], log_prices[:, 1], log_prices[:, 2], log_prices[:, 3]

    # Decompose each bar into independent movements (in log space):
    #   gap    = open minus previous close  (the jump between bars)
    #   r_h/l/c = high/low/close relative to that bar's own open
    gap = np.empty(n)
    gap[0] = 0.0
    gap[1:] = o[1:] - c[:-1]
    r_h = h - o
    r_l = l - o
    r_c = c - o

    # Shuffle the movements after start_index. Two independent shuffles:
    # one for the intrabar shape (h/l/c together, so bars stay coherent),
    # one for the gaps.
    idx = np.arange(start_index + 1, n)
    perm_bars = rng.permutation(idx)
    perm_gaps = rng.permutation(idx)

    new = np.empty((n, 4))
    new[: start_index + 1] = log_prices[: start_index + 1]

    prev_close = c[start_index]
    for i, (bi, gi) in enumerate(zip(perm_bars, perm_gaps)):
        row = start_index + 1 + i
        new_open = prev_close + gap[gi]
        new[row, 0] = new_open
        new[row, 1] = new_open + r_h[bi]
        new[row, 2] = new_open + r_l[bi]
        new[row, 3] = new_open + r_c[bi]
        prev_close = new[row, 3]

    out = pd.DataFrame(
        np.exp(new), index=df.index, columns=["Open", "High", "Low", "Close"]
    )
    # Every non-OHLC column (Volume, and any extra series a strategy needs
    # such as a liquidation reading) travels with the bar whose shape it
    # belonged to. Without this the shuffled data would keep those columns
    # in real time order, leaving a genuine signal intact and making the
    # honesty test far too easy to pass.
    for col in df.columns:
        if col in ("Open", "High", "Low", "Close"):
            continue
        vals = df[col].to_numpy().copy()
        vals[start_index + 1 :] = df[col].to_numpy()[perm_bars]
        out[col] = vals
    return out


if __name__ == "__main__":
    # Quick sanity check: shuffled series should have identical return
    # distribution but a different path.
    import data

    df = data.load()
    p = permute_bars(df, start_index=100, rng=np.random.default_rng(1))
    real_ret = np.log(df["Close"]).diff().dropna()
    perm_ret = np.log(p["Close"]).diff().dropna()
    print("real  mean/std: %.6f / %.4f" % (real_ret.mean(), real_ret.std()))
    print("perm  mean/std: %.6f / %.4f" % (perm_ret.mean(), perm_ret.std()))
    print("final real close: %.0f   final perm close: %.0f"
          % (df["Close"].iloc[-1], p["Close"].iloc[-1]))
    assert (p["High"] >= p[["Open", "Close"]].max(axis=1) - 1e-9).all()
    assert (p["Low"] <= p[["Open", "Close"]].min(axis=1) + 1e-9).all()
    print("OHLC integrity OK")
