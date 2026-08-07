"""Unit tests for permute_bars (permute.py's shuffle algorithm - the
algorithm itself must not change; these tests only check its output)."""

import numpy as np
import pandas as pd

from permute import permute_bars


def test_ohlc_integrity(synthetic_frame):
    df = synthetic_frame(n=200, seed=1)
    perm = permute_bars(df, start_index=20, rng=np.random.default_rng(3))

    highs_ok = perm["High"] >= perm[["Open", "Close"]].max(axis=1) - 1e-9
    lows_ok = perm["Low"] <= perm[["Open", "Close"]].min(axis=1) + 1e-9
    assert highs_ok.all()
    assert lows_ok.all()


def test_prefix_preserved(synthetic_frame):
    df = synthetic_frame(n=200, seed=1)
    start_index = 20
    perm = permute_bars(df, start_index=start_index, rng=np.random.default_rng(3))

    pd.testing.assert_frame_equal(
        perm.iloc[: start_index + 1][["Open", "High", "Low", "Close"]],
        df.iloc[: start_index + 1][["Open", "High", "Low", "Close"]],
    )


def test_determinism_for_fixed_seed(synthetic_frame):
    df = synthetic_frame(n=200, seed=1)
    p1 = permute_bars(df, start_index=20, rng=np.random.default_rng(7))
    p2 = permute_bars(df, start_index=20, rng=np.random.default_rng(7))
    pd.testing.assert_frame_equal(p1, p2)

    p3 = permute_bars(df, start_index=20, rng=np.random.default_rng(8))
    assert not p1.equals(p3)


def test_return_distribution_moments_preserved(synthetic_frame):
    """The permuted region's close-to-close return is gap[gi] + r_c[bi],
    drawn from *two independent* shuffles of the gaps and the intrabar
    moves. So the multiset of close-to-close returns (and hence its std)
    is NOT preserved - only the sum (and therefore the mean), and the
    separate multisets of gaps and intrabar moves, are. Do not "fix" this
    into a std comparison; it would be wrong.
    """
    df = synthetic_frame(n=300, seed=2)
    start_index = 30
    perm = permute_bars(df, start_index=start_index, rng=np.random.default_rng(5))

    real = df.iloc[start_index:]
    perm_region = perm.iloc[start_index:]

    real_log = np.log(real[["Open", "High", "Low", "Close"]].to_numpy())
    perm_log = np.log(perm_region[["Open", "High", "Low", "Close"]].to_numpy())

    # Sum (hence mean) of close-to-close log returns over the permuted
    # region is exactly preserved.
    real_cc = np.diff(np.log(df["Close"].to_numpy()))[start_index:]
    perm_cc = np.diff(np.log(perm["Close"].to_numpy()))[start_index:]
    assert np.isclose(real_cc.sum(), perm_cc.sum(), atol=1e-9)

    # Multiset of intrabar moves (relative to that bar's own open) preserved.
    real_r_h = real_log[:, 1] - real_log[:, 0]
    real_r_l = real_log[:, 2] - real_log[:, 0]
    real_r_c = real_log[:, 3] - real_log[:, 0]
    perm_r_h = perm_log[:, 1] - perm_log[:, 0]
    perm_r_l = perm_log[:, 2] - perm_log[:, 0]
    perm_r_c = perm_log[:, 3] - perm_log[:, 0]
    np.testing.assert_allclose(np.sort(real_r_h), np.sort(perm_r_h), atol=1e-9)
    np.testing.assert_allclose(np.sort(real_r_l), np.sort(perm_r_l), atol=1e-9)
    np.testing.assert_allclose(np.sort(real_r_c), np.sort(perm_r_c), atol=1e-9)

    # Multiset of gaps (open[i] vs close[i-1]) preserved.
    real_close_all = np.log(df["Close"].to_numpy())
    real_open_all = np.log(df["Open"].to_numpy())
    perm_close_all = np.log(perm["Close"].to_numpy())
    perm_open_all = np.log(perm["Open"].to_numpy())

    real_gap = real_open_all[start_index + 1:] - real_close_all[start_index:-1]
    perm_gap = perm_open_all[start_index + 1:] - perm_close_all[start_index:-1]
    np.testing.assert_allclose(np.sort(real_gap), np.sort(perm_gap), atol=1e-9)
