"""Shared fixtures for the signal-check test suite.

No network, no downloads, no full pipeline runs - every test builds its
own small synthetic OHLCV frame here or inline.
"""

import os
import sys

# With no __init__.py in tests/, pytest puts tests/ on sys.path, not the
# repo root. Put the repo root on the path so `import strategies` etc. work.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def tiny_frame():
    """A ~10-bar OHLCV frame with hand-chosen values.

    Built so a swing high is obvious at bar 3 (High=112) and a swing low
    is obvious at bar 6 (Low=88). Values chosen for easy hand-computation,
    not realism.
    """
    idx = pd.date_range("2021-01-01", periods=10, freq="12h")
    data = {
        # bar:      0    1    2    3    4    5    6    7    8    9
        "Open":  [100, 101, 103, 108, 106, 100,  92,  95,  97,  99],
        "High":  [102, 104, 107, 112, 108, 101,  93,  98, 100, 101],
        "Low":   [ 99, 100, 102, 106, 103,  92,  88,  93,  95,  97],
        "Close": [101, 103, 105, 109, 104,  93,  90,  97,  99, 100],
        "Volume": [10] * 10,
    }
    return pd.DataFrame(data, index=idx)


@pytest.fixture
def synthetic_frame():
    """Factory fixture: build a seeded geometric random walk OHLCV frame.

    Usage: synthetic_frame(n=700, freq="12h", seed=0)
    """
    def _make(n=700, freq="12h", seed=0):
        rng = np.random.default_rng(seed)
        idx = pd.date_range("2018-01-01", periods=n, freq=freq)
        log_rets = rng.normal(loc=0.0002, scale=0.02, size=n)
        close = 100.0 * np.exp(np.cumsum(log_rets))
        open_ = np.empty(n)
        open_[0] = 100.0
        open_[1:] = close[:-1]
        noise = np.abs(rng.normal(loc=0.001, scale=0.003, size=n)) * close
        high = np.maximum(open_, close) + noise
        low = np.minimum(open_, close) - noise
        volume = rng.uniform(100, 1000, size=n)
        return pd.DataFrame({
            "Open": open_, "High": high, "Low": low, "Close": close,
            "Volume": volume,
        }, index=idx)
    return _make
