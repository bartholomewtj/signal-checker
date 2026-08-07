"""Unit tests for the indicator building blocks in strategies.py.

Expected values below are derived by hand from each function's definition
and the `tiny_frame` fixture's bars - never by calling the function and
pasting its output back in.
"""

import numpy as np
import pandas as pd

from strategies import (
    anchored_sma,
    last_swing_levels,
    rejection,
    sticky_state,
    swing_high,
    swing_low,
)


def test_swing_high_confirms_one_bar_after_the_peak(tiny_frame):
    # High: [102,104,107,112,108,101,93,98,100,101]
    # Peak is bar 3 (112). swing_high(high, n=1) is True n=1 bars after
    # the peak is confirmed, i.e. at bar 4 - not at the peak itself.
    result = swing_high(tiny_frame["High"], n=1).to_numpy()
    expected = np.array([False, False, False, False, True,
                          False, False, False, False, False])
    np.testing.assert_array_equal(result, expected)


def test_swing_low_confirms_one_bar_after_the_trough(tiny_frame):
    # Low: [99,100,102,106,103,92,88,93,95,97]
    # Trough is bar 6 (88). Confirmed at bar 7.
    result = swing_low(tiny_frame["Low"], n=1).to_numpy()
    expected = np.array([False, False, False, False, False,
                          False, False, True, False, False])
    np.testing.assert_array_equal(result, expected)


def test_anchored_sma_reanchors_and_is_nan_before_first_event(tiny_frame):
    high = tiny_frame["High"].to_numpy()
    events = swing_high(tiny_frame["High"], n=1).to_numpy()  # True at index 4 only
    out = anchored_sma(high, events, n=1)

    # No event has happened yet at bars 0-3 -> NaN.
    assert np.isnan(out[:4]).all()

    # At the event bar (4) the window widens with n+1=2 anchored at the
    # peak bar (index 3): mean(High[3:5]) = (112+108)/2 = 110.
    assert out[4] == 110.0
    # Expanding from the same anchor (index 3) as bars pass, no new event:
    assert np.isclose(out[5], (112 + 108 + 101) / 3)
    assert np.isclose(out[6], (112 + 108 + 101 + 93) / 4)
    assert np.isclose(out[7], (112 + 108 + 101 + 93 + 98) / 5)
    assert np.isclose(out[8], (112 + 108 + 101 + 93 + 98 + 100) / 6)
    assert np.isclose(out[9], (112 + 108 + 101 + 93 + 98 + 100 + 101) / 7)


def test_last_swing_levels_uses_value_before_event_bar_and_nan_until_seen(tiny_frame):
    high = tiny_frame["High"].to_numpy()
    events = swing_high(tiny_frame["High"], n=1).to_numpy()  # True at index 4 only

    levels = last_swing_levels(high, events, count=2)

    # k=0: the most recent swing's value is High[event_bar - 1] = High[3] = 112,
    # visible from the event bar (4) onward; NaN before it.
    expected_k0 = np.array([np.nan, np.nan, np.nan, np.nan,
                             112, 112, 112, 112, 112, 112])
    np.testing.assert_array_equal(np.isnan(levels[0]), np.isnan(expected_k0))
    np.testing.assert_allclose(
        levels[0][~np.isnan(expected_k0)], expected_k0[~np.isnan(expected_k0)])

    # k=1: a second-most-recent swing has never happened in this frame -> all NaN.
    assert np.isnan(levels[1]).all()


def test_sticky_state_holds_previous_state_through_flat_bars():
    series = [1, 2, 2, 1, 1, 3, 3, 2]
    # diff:        [nan, 1, 0, -1, 0, 2, 0, -1]
    # sign:        [nan, 1, 0, -1, 0, 1, 0, -1]
    # 0 -> NaN, ffill flat bars to hold the previous non-zero state:
    expected = [np.nan, 1, 1, -1, -1, 1, 1, -1]
    out = sticky_state(pd.Series(series))
    assert np.isnan(out[0])
    np.testing.assert_allclose(out[1:], expected[1:])


def test_rejection_bull_and_bear_and_touch_without_cross():
    open_ = pd.Series([105.0, 105.0, 95.0])
    high = pd.Series([106.0, 106.0, 101.0])
    low = pd.Series([95.0, 104.0, 94.0])
    close = pd.Series([107.0, 103.0, 90.0])
    level = pd.Series([100.0, 100.0, 100.0])

    bull, bear = rejection(open_, high, low, close, level)

    # Bar 0: opened above (105>100), dipped below (95<100), closed back above
    # (107>100) -> bullish rejection.
    assert bull.iloc[0] and not bear.iloc[0]

    # Bar 1: opened above, but low (104) never crosses below the level ->
    # "touches but does not cross" -> no rejection either way.
    assert not bull.iloc[1] and not bear.iloc[1]

    # Bar 2: opened below (95<100), poked above (101>100), closed back below
    # (90<100) -> bearish rejection.
    assert bear.iloc[2] and not bull.iloc[2]
