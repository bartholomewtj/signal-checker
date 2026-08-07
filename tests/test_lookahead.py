"""The lookahead tripwire.

A strategy that accidentally reads a future bar will show a *different*
precomputed signal at bar t depending on whether the data ends at bar t
or goes on further. A causal strategy cannot. This is the test that
catches the worst bug class in backtesting.

If this test ever goes red at the last index or two before a truncation
point, THAT IS THE TRIPWIRE WORKING. Do not "stabilise" it by trimming
the final bars from the comparison - the boundary is precisely where a
higher-timeframe lookahead shows up (a partial resampled bucket differs
from the completed one), and trimming it disarms the whole test.
"""

import os
import warnings

os.environ.setdefault("TQDM_DISABLE", "1")

import numpy as np
import pytest
from backtesting.lib import FractionalBacktest

from strategies import REGISTRY

warnings.filterwarnings(
    "ignore", message=".*insufficient margin.*", category=UserWarning)

CASH = 100_000
COMMISSION = 0.0015
SPREAD = 0.0005

# 700 bars clears the largest WARMUP in the registry (Devma.WARMUP = 360)
# with room to spare, for every truncation point below.
N_BARS = 700

# Several truncation points, not one. A higher-timeframe lookahead bug only
# shows up when the cut lands mid-bucket in the right phase; testing a
# single T means a real bug can pass by luck. These are spread across
# different offsets modulo the 2D and 3D bucket sizes Devma resamples to
# (12h bars -> 2D bucket = 4 bars, 3D bucket = 6 bars):
#   t=433: t%4=1, t%6=1
#   t=530: t%4=2, t%6=2
#   t=555: t%4=3, t%6=3
#   t=616: t%4=0, t%6=4
# Verified empirically (scratch copy, .shift(1) removed from htf_bands):
# each of these four points independently catches the missing-shift bug
# in both devma and combo (as does every other value in a swept range of
# 420-690 tried during that verification, so this is not a lucky pick -
# most phases catch it; the ones that were removed from an earlier
# revision of this list simply happened not to).
TRUNCATIONS = [433, 530, 555, 616]


def signal_arrays(stats, n):
    """Every precomputed indicator array on the strategy instance whose
    last axis has length n."""
    strat_obj = stats["_strategy"]
    out = {}
    for attr in dir(strat_obj):
        if attr.startswith("_"):
            continue
        val = getattr(strat_obj, attr, None)
        if isinstance(val, np.ndarray) and val.shape[-1] == n:
            out[attr] = np.asarray(val)
    return out


def _run(df, strat_cls, params):
    bt = FractionalBacktest(df, strat_cls, fractional_unit=1e-6,
                            cash=CASH, commission=COMMISSION,
                            spread=SPREAD, finalize_trades=True)
    return bt.run(**params)


# The full-series run is identical for every truncation point t, so it is
# computed once per strategy and reused across the TRUNCATIONS parametrize.
_FULL_CACHE = {}


def _full_run(name, df, strat_cls, defaults):
    if name not in _FULL_CACHE:
        _FULL_CACHE[name] = _run(df, strat_cls, defaults)
    return _FULL_CACHE[name]


@pytest.mark.parametrize("t", TRUNCATIONS)
@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_no_lookahead(name, t, synthetic_frame):
    strat_cls = REGISTRY[name]
    df = synthetic_frame(n=N_BARS, freq="12h", seed=0)
    defaults = {k: getattr(strat_cls, k) for k in strat_cls.GRID}

    trunc_stats = _run(df.iloc[:t], strat_cls, defaults)
    full_stats = _full_run(name, df, strat_cls, defaults)

    trunc_arrays = signal_arrays(trunc_stats, t)
    full_arrays = signal_arrays(full_stats, N_BARS)

    assert trunc_arrays, "no precomputed signal arrays found - refactor renamed them?"

    shared = set(trunc_arrays) & set(full_arrays)
    assert shared == set(trunc_arrays), (
        "some precomputed arrays only exist in one run - refactor renamed them?")

    for key in shared:
        np.testing.assert_allclose(
            trunc_arrays[key], full_arrays[key][..., :t],
            equal_nan=True,
            err_msg=f"{name}.{key} differs between truncated and full runs "
                    f"- looks like it is reading future bars",
        )
