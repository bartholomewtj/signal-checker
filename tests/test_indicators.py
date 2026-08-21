"""Unit tests for the indicator building blocks in strategies.py.

Expected values below are derived by hand from each function's definition
and the `tiny_frame` fixture's bars - never by calling the function and
pasting its output back in.
"""

import numpy as np
import pandas as pd

from strategies import (
    anchored_sma,
    break_retest_long,
    last_swing_levels,
    rejection,
    sticky_state,
    swing_high,
    swing_low,
    swing_low_break,
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


# ---------------------------------------------------------------------------
# break_retest_long
#
# Shared prefix: bar 3 is the peak (High=110), confirmed at bar 4, so the
# swing-high level is 110 from bar 4 onward until a later swing confirms.


def _ohlc(rows):
    o, h, l, c = zip(*rows)
    return (
        np.array(o, dtype=float),
        np.array(h, dtype=float),
        np.array(l, dtype=float),
        np.array(c, dtype=float),
    )


_PREFIX = (
    (100, 102, 99, 101),   # 0
    (101, 104, 100, 103),  # 1
    (103, 105, 102, 104),  # 2
    (104, 110, 103, 108),  # 3 peak
    (108, 108, 104, 105),  # 4 swing high confirms, level=110
    (105, 107, 100, 102),  # 5
    (102, 106, 101, 104),  # 6
    (104, 107, 103, 105),  # 7
    (105, 108, 104, 106),  # 8
    (106, 109, 105, 108),  # 9 close 108 <= 110
)

# Break of 110. High=116 is the take-profit for exit_mode=break_high.
_BREAK = (108, 116, 107, 114)

# Stays well above 110, no wick into the level.
_ABOVE = (114, 118, 112, 116)

# Opens above 110, wicks through (low 109), closes back above.
_RETEST = (112, 115, 109, 113)


def test_break_retest_enters_on_later_rejection_not_on_the_break_bar():
    # Bar 10 gaps up through 110 and wicks back into it - that is the
    # break, and would look like a rejection if we allowed the break bar.
    rows = _PREFIX + (
        (112, 116, 109, 114),  # 10 break + wick; must not enter
        _ABOVE,                # 11 no wick (low 112 > 110)
        _RETEST,               # 12 retest
        _ABOVE,
    )
    entry, armed, peak = break_retest_long(*_ohlc(rows), window=5)
    assert entry[10] == 0.0
    assert entry[12] == 1.0
    assert entry.sum() == 1.0
    assert armed[10] == 110.0
    assert armed[11] == 110.0
    assert armed[12] == 110.0
    assert np.isnan(armed[13])
    assert peak[12] == 116.0


def test_break_retest_records_the_break_bar_high():
    rows = _PREFIX + (_BREAK, _ABOVE, _RETEST, _ABOVE)
    entry, _, peak = break_retest_long(*_ohlc(rows), window=5)
    assert entry[12] == 1.0
    assert peak[10] == 116.0
    assert peak[12] == 116.0
    assert np.isnan(peak[13])


def test_break_retest_freezes_the_broken_level_not_a_newer_swing_high():
    # Bar 11 makes a higher high (118). That swing confirms at bar 12,
    # so live last_swing_levels at bar 12 is 118. The retest is of 110.
    rows = _PREFIX + (
        _BREAK,
        (114, 118, 112, 116),  # 11 peak 118
        _RETEST,               # 12 SH=118 confirms; retest of frozen 110
    )
    entry, armed, peak = break_retest_long(*_ohlc(rows), window=5)
    assert entry[12] == 1.0
    assert armed[12] == 110.0
    assert peak[12] == 116.0


def test_break_retest_window_allows_bar_plus_5_not_plus_6():
    rows_ok = _PREFIX + (_BREAK,) + (_ABOVE,) * 4 + (_RETEST,)
    entry_ok, _, _ = break_retest_long(*_ohlc(rows_ok), window=5)
    assert entry_ok[15] == 1.0

    rows_late = _PREFIX + (_BREAK,) + (_ABOVE,) * 5 + (_RETEST,)
    entry_late, armed_late, _ = break_retest_long(*_ohlc(rows_late), window=5)
    assert entry_late[16] == 0.0
    assert entry_late.sum() == 0.0
    assert np.isnan(armed_late[16])


def test_break_retest_close_back_below_the_level_disarms():
    rows = _PREFIX + (
        _BREAK,
        (114, 115, 108, 109),  # 11 close 109 < 110 -> fail
        _RETEST,
    )
    entry, armed, _ = break_retest_long(*_ohlc(rows), window=5)
    assert entry.sum() == 0.0
    assert np.isnan(armed[11])
    assert np.isnan(armed[12])


def test_break_retest_first_retest_consumes_the_setup():
    rows = _PREFIX + (_BREAK, _RETEST, _RETEST)
    entry, _, _ = break_retest_long(*_ohlc(rows), window=5)
    assert entry[11] == 1.0
    assert entry[12] == 0.0
    assert entry.sum() == 1.0


def test_swing_low_break_crosses_down_through_confirmed_trough():
    # Mirror of the swing-high prefix: trough at bar 3 (Low=90), confirmed
    # at bar 4. Close then crosses down through 90 at bar 6.
    rows = (
        (100, 102, 99, 101),
        (101, 103, 98, 100),
        (100, 102, 97, 99),
        (99, 100, 90, 92),    # 3 trough
        (92, 94, 91, 93),     # 4 swing low confirms, level=90
        (93, 95, 91, 92),     # 5 close 92 >= 90
        (92, 93, 88, 89),     # 6 close 89 < 90
        (89, 91, 87, 90),
    )
    o, h, l, c = _ohlc(rows)
    brk = swing_low_break(l, c, n=1)
    assert not brk[5]
    assert brk[6]
    assert brk.sum() == 1
