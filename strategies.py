"""The strategies under test, extracted from the TVscripts indicators.

Each TradingView indicator in the original repo implies a way of trading.
This file turns each one into explicit entry/exit rules so the pipeline
can judge it. Where the indicator only gave alerts (no exit rule), the
exit is noted as my choice, not the original author's.

Every strategy class carries:
    GRID   - the parameter combinations the optimizer may try (kept small
             on purpose; big grids make overfitting easy)
    WARMUP - bars to keep un-shuffled at the start of permuted data
"""

import numpy as np
import pandas as pd
from backtesting import Strategy


# ---------------------------------------------------------------------------
# Shared building blocks (ported from the Pine Script)

def swing_high(high, n=1):
    """Confirmed swing high: bar n back is higher than its neighbours.

    Matches the Pine `up = high[n+1]<high[n] and high[n]>high`.
    True on the bar where the swing is CONFIRMED (n bars after the peak).
    """
    return (high.shift(n + 1) < high.shift(n)) & (high.shift(n) > high)


def swing_low(low, n=1):
    return (low.shift(n + 1) > low.shift(n)) & (low.shift(n) < low)


def anchored_sma(values, events, n=1):
    """Average of `values` since the last swing event (Pine's
    `Sma(src, barssince(up)+n+1)` - an expanding average that re-anchors
    at every new swing)."""
    vals = np.asarray(values, dtype=float)
    ev = np.asarray(events, dtype=bool)
    idx = np.arange(len(vals))
    last_evt = pd.Series(np.where(ev, idx, np.nan)).ffill().to_numpy()
    csum = np.concatenate([[0.0], np.nancumsum(vals)])
    out = np.full(len(vals), np.nan)
    valid = ~np.isnan(last_evt)
    w = (idx - last_evt + n + 1)
    start = idx + 1 - w
    ok = valid & (start >= 0)
    wi = w[ok].astype(int)
    si = start[ok].astype(int)
    out[ok] = (csum[idx[ok] + 1] - csum[si]) / wi
    return out


def sticky_state(series):
    """+1 while the series was last rising, -1 while last falling.

    Matches the Pine rising/falling switch used in the Trend Shift
    indicators: flat bars keep the previous state.
    """
    diff = np.sign(pd.Series(series).diff())
    return diff.replace(0, np.nan).ffill().to_numpy()


def last_swing_levels(values, events, count):
    """levels[k][i] = value of the (k+1)-th most recent swing at bar i.

    Port of Pine's `valuewhen(up, high[1], k)`.
    """
    vals = np.asarray(values, dtype=float)
    ev_pos = np.flatnonzero(events)
    ev_val = vals[np.maximum(ev_pos - 1, 0)]  # the swing bar's value (high[1])
    idx = np.arange(len(vals))
    # For each bar, how many events have happened so far (index of latest)
    n_seen = np.searchsorted(ev_pos, idx, side="right") - 1
    levels = []
    for k in range(count):
        which = n_seen - k
        lvl = np.where(which >= 0, ev_val[np.clip(which, 0, None)], np.nan)
        levels.append(lvl)
    return levels


def rejection(open_, high, low, close, level):
    """Bull/bear rejection of a level, per the Pine alert conditions:
    bull = opened above, dipped below, closed back above."""
    bull = (open_ > level) & (low < level) & (close > level)
    bear = (open_ < level) & (high > level) & (close < level)
    return bull, bear


# ---------------------------------------------------------------------------
# Shared base: a `direction` filter usable by every strategy below.

class Base(Strategy):
    """Shared base for every strategy in this file.

    `direction` filters which side may be opened:
      both  - unchanged
      long  - sell() is ignored, so a short signal just flattens the position
      short - buy() is ignored
    Strategies already call `self.position.close()` before opening the
    opposite side, so ignoring the open is exactly the behaviour we want.
    """
    direction = "both"

    def buy(self, **kwargs):
        if self.direction == "short":
            return None
        return super().buy(**kwargs)

    def sell(self, **kwargs):
        if self.direction == "long":
            return None
        return super().sell(**kwargs)


# ---------------------------------------------------------------------------
# 1. Diamond Hands - sweep reversal (from "Diamond Hands strategy")

class DiamondHands(Base):
    """Price sweeps the recent low but closes back above it, trend agrees."""
    lookback = 20
    trend_len = 200

    GRID = {"lookback": [12, 20, 30, 48], "trend_len": [100, 200, 300]}
    WARMUP = 301

    def init(self):
        close, low, high = (self.data.Close.s, self.data.Low.s, self.data.High.s)
        lb = self.lookback
        self.prior_low_min = self.I(lambda: low.rolling(lb).min().shift(1), plot=False)
        self.prior_close_min = self.I(lambda: close.rolling(lb).min().shift(1), plot=False)
        self.prior_high_max = self.I(lambda: high.rolling(lb).max().shift(1), plot=False)
        self.prior_close_max = self.I(lambda: close.rolling(lb).max().shift(1), plot=False)
        self.trend = self.I(lambda: close.rolling(self.trend_len).mean(), plot=False)

    def next(self):
        if np.isnan(self.trend[-1]) or np.isnan(self.prior_low_min[-1]):
            return
        close, low, high = self.data.Close[-1], self.data.Low[-1], self.data.High[-1]
        long_sig = (low < self.prior_low_min[-1] and close > self.prior_close_min[-1]
                    and close > self.trend[-1])
        short_sig = (high > self.prior_high_max[-1] and close < self.prior_close_max[-1]
                     and close < self.trend[-1])
        if long_sig and not self.position.is_long:
            self.position.close(); self.buy()
        elif short_sig and not self.position.is_short:
            self.position.close(); self.sell()
        elif self.position.is_long and close < self.trend[-1]:
            self.position.close()
        elif self.position.is_short and close > self.trend[-1]:
            self.position.close()


# ---------------------------------------------------------------------------
# 2. Trend Step - from "Trend Shifts + Alerts" / "Trend Classifier Strategy"

class TrendStep(Base):
    """Long while the swing-anchored midband is rising, short while falling.

    The indicator's midband = average of (SMA of highs since the last
    swing high) and (SMA of lows since the last swing low). The alert
    fires when the band's direction flips; the Trend Classifier strategy
    trades those flips. Always in the market (stop-and-reverse).
    """
    fractal_n = 1

    GRID = {"fractal_n": [1, 2, 3, 5]}
    WARMUP = 60

    def init(self):
        h, l = self.data.High.s, self.data.Low.s
        n = self.fractal_n
        up = swing_high(h, n)
        down = swing_low(l, n)
        upper = anchored_sma(h.to_numpy(), up.to_numpy(), n)
        lower = anchored_sma(l.to_numpy(), down.to_numpy(), n)
        midband = (upper + lower) / 2
        self.state = self.I(lambda: sticky_state(midband), plot=False)

    def next(self):
        s = self.state[-1]
        if np.isnan(s):
            return
        if s > 0 and not self.position.is_long:
            self.position.close(); self.buy()
        elif s < 0 and not self.position.is_short:
            self.position.close(); self.sell()


# ---------------------------------------------------------------------------
# 3. HL Band Breakout - from "HL Bands + Alerts"

class HLBandBreakout(Base):
    """Long when price closes out above the upper band ("exit cloud - H"
    alert), close the long when it re-enters the cloud. Mirror for shorts
    below the lower band. Bands are the swing-anchored SMAs of highs/lows.
    """
    fractal_n = 1

    GRID = {"fractal_n": [1, 2, 3, 5]}
    WARMUP = 60

    def init(self):
        h, l = self.data.High.s, self.data.Low.s
        n = self.fractal_n
        upper = anchored_sma(h.to_numpy(), swing_high(h, n).to_numpy(), n)
        lower = anchored_sma(l.to_numpy(), swing_low(l, n).to_numpy(), n)
        self.upper = self.I(lambda: upper, plot=False)
        self.lower = self.I(lambda: lower, plot=False)

    def next(self):
        if np.isnan(self.upper[-1]) or np.isnan(self.lower[-1]) or len(self.data) < 2:
            return
        c, c1 = self.data.Close[-1], self.data.Close[-2]
        up, up1 = self.upper[-1], self.upper[-2]
        lo, lo1 = self.lower[-1], self.lower[-2]
        crossed_above_upper = c1 <= up1 and c > up
        crossed_below_upper = c1 >= up1 and c < up
        crossed_below_lower = c1 >= lo1 and c < lo
        crossed_above_lower = c1 <= lo1 and c > lo
        if crossed_above_upper and not self.position.is_long:
            self.position.close(); self.buy()
        elif crossed_below_lower and not self.position.is_short:
            self.position.close(); self.sell()
        elif self.position.is_long and crossed_below_upper:
            self.position.close()
        elif self.position.is_short and crossed_above_lower:
            self.position.close()


# ---------------------------------------------------------------------------
# 4. Structure Break - from "Structure break + Alerts"

class StructureBreak(Base):
    """Long when a single bar opens below and closes above a recent swing
    high (and above the prior bar's high) - the indicator's "Bullish SB"
    alert. Short on the mirror image. Stop-and-reverse: hold until the
    opposite break.
    """
    fractal_n = 1
    m_levels = 6  # how many recent swing highs/lows count as "structure"

    GRID = {"fractal_n": [1, 2], "m_levels": [1, 3, 6]}
    WARMUP = 60

    def init(self):
        o, h, l, c = (self.data.Open.s, self.data.High.s,
                      self.data.Low.s, self.data.Close.s)
        n = self.fractal_n
        up = swing_high(h, n).to_numpy()
        down = swing_low(l, n).to_numpy()
        hi_levels = last_swing_levels(h.to_numpy(), up, self.m_levels)
        lo_levels = last_swing_levels(l.to_numpy(), down, self.m_levels)
        on, hn, ln, cn = o.to_numpy(), h.to_numpy(), l.to_numpy(), c.to_numpy()
        h1 = np.concatenate([[np.nan], hn[:-1]])
        l1 = np.concatenate([[np.nan], ln[:-1]])
        bull = np.zeros(len(cn), dtype=bool)
        bear = np.zeros(len(cn), dtype=bool)
        # Break of the max of the last m swing highs, for m = 1..m_levels
        run_max = np.full(len(cn), -np.inf)
        for lvl in hi_levels:
            run_max = np.fmax(run_max, lvl)
            bull |= (on < run_max) & (cn > run_max) & (cn > h1)
        run_min = np.full(len(cn), np.inf)
        for lvl in lo_levels:
            run_min = np.fmin(run_min, lvl)
            bear |= (on > run_min) & (cn < run_min) & (cn < l1)
        self.bull = self.I(lambda: bull.astype(float), plot=False)
        self.bear = self.I(lambda: bear.astype(float), plot=False)

    def next(self):
        if self.bull[-1] > 0 and not self.position.is_long:
            self.position.close(); self.buy()
        elif self.bear[-1] > 0 and not self.position.is_short:
            self.position.close(); self.sell()


# ---------------------------------------------------------------------------
# 5. Open Rejection - from "Killzones + Opens + Rejection alerts"

class OpenRejection(Base):
    """The indicator draws yesterday's daily close (its "daily open" line)
    and the weekly equivalent, and alerts when a bar dips through the
    level but closes back on its original side (a rejection).

    Trade: long on a bullish rejection, short on a bearish one.
    Exit after `hold` bars - the indicator gives no exit, so the hold
    time is this port's choice, exposed as a parameter.
    """
    level_tf = "D"  # 'D' = prior daily close, 'W' = prior weekly close
    hold = 24

    GRID = {"level_tf": ["D", "W"], "hold": [12, 24, 48]}
    WARMUP = 200

    def init(self):
        o, h, l, c = (self.data.Open.s, self.data.High.s,
                      self.data.Low.s, self.data.Close.s)
        rule = "1D" if self.level_tf == "D" else "W-MON"
        prev = c.resample(rule).last().shift(1)
        level = prev.reindex(c.index, method="ffill")
        bull, bear = rejection(o, h, l, c, level)
        self.bull = self.I(lambda: bull.astype(float), plot=False)
        self.bear = self.I(lambda: bear.astype(float), plot=False)
        self.bars_held = 0

    def next(self):
        if self.position:
            self.bars_held += 1
            if self.bars_held >= self.hold:
                self.position.close()
        if self.bull[-1] > 0 and not self.position.is_long:
            self.position.close(); self.buy(); self.bars_held = 0
        elif self.bear[-1] > 0 and not self.position.is_short:
            self.position.close(); self.sell(); self.bars_held = 0


# ---------------------------------------------------------------------------
# 6. VWAP Rejection - from "VWAP daily anchor"

class VWAPRejection(Base):
    """The indicator anchors VWAP (volume-weighted average price) to each
    day and alerts on rejections of the VWAP line. Trade: long on a
    bullish rejection, short on bearish, exit after `hold` bars (exit is
    this port's choice, as above).
    """
    hold = 24

    GRID = {"hold": [12, 24, 48]}
    WARMUP = 200

    def init(self):
        o, h, l, c = (self.data.Open.s, self.data.High.s,
                      self.data.Low.s, self.data.Close.s)
        v = self.data.Volume.s
        tp = (h + l + c) / 3
        day = c.index.normalize()
        pv = (tp * v).groupby(day).cumsum()
        vv = v.groupby(day).cumsum()
        vwap = pv / vv
        bull, bear = rejection(o, h, l, c, vwap)
        self.bull = self.I(lambda: bull.astype(float), plot=False)
        self.bear = self.I(lambda: bear.astype(float), plot=False)
        self.bars_held = 0

    def next(self):
        if self.position:
            self.bars_held += 1
            if self.bars_held >= self.hold:
                self.position.close()
        if self.bull[-1] > 0 and not self.position.is_long:
            self.position.close(); self.buy(); self.bars_held = 0
        elif self.bear[-1] > 0 and not self.position.is_short:
            self.position.close(); self.sell(); self.bars_held = 0


# ---------------------------------------------------------------------------
# 7. DEVMA - from the v6 "DEVMA strat NR 18/03" script

def htf_bands(high, low, close, rule, n=1):
    """Swing-anchored high/low bands computed on a higher timeframe and
    mapped back to the chart with a one-full-bar delay (no lookahead),
    matching the original script's no-repaint f_security wrapper.

    Returns a DataFrame indexed like `close` with columns
    upper, lower, mid, state (+1 mid rising / -1 mid falling).
    """
    ohlc = pd.DataFrame({"High": high, "Low": low, "Close": close})
    htf = ohlc.resample(rule).agg({"High": "max", "Low": "min",
                                   "Close": "last"}).dropna()
    up = swing_high(htf.High, n)
    down = swing_low(htf.Low, n)
    upper = pd.Series(anchored_sma(htf.High.to_numpy(), up.to_numpy(), n),
                      index=htf.index)
    lower = pd.Series(anchored_sma(htf.Low.to_numpy(), down.to_numpy(), n),
                      index=htf.index)
    mid = (upper + lower) / 2
    state = pd.Series(sticky_state(mid), index=htf.index)
    out = pd.DataFrame({"upper": upper, "lower": lower,
                        "mid": mid, "state": state}).shift(1)
    return out.reindex(close.index, method="ffill")


def structure_break_signals(o, h, l, c, n=1, m=6, lookback=48):
    """Bull/bear structure breaks as in the original scripts: a single bar
    engulfing one of the last `m` swing highs/lows, or the highest/lowest
    swing of the last `lookback` bars."""
    up = swing_high(h, n).to_numpy()
    down = swing_low(l, n).to_numpy()
    hn, ln, cn, on = h.to_numpy(), l.to_numpy(), c.to_numpy(), o.to_numpy()
    h1 = np.concatenate([[np.nan], hn[:-1]])
    l1 = np.concatenate([[np.nan], ln[:-1]])
    bull = np.zeros(len(cn), dtype=bool)
    bear = np.zeros(len(cn), dtype=bool)
    hi_levels = last_swing_levels(hn, up, m)
    lo_levels = last_swing_levels(ln, down, m)
    run_max = np.full(len(cn), -np.inf)
    for lvl in hi_levels:
        run_max = np.fmax(run_max, lvl)
        bull |= (on < run_max) & (cn > run_max) & (cn > h1)
    run_min = np.full(len(cn), np.inf)
    for lvl in lo_levels:
        run_min = np.fmin(run_min, lvl)
        bear |= (on > run_min) & (cn < run_min) & (cn < l1)
    # the "lowest/highest swing in `lookback` bars" variant
    hi48 = pd.Series(hi_levels[0]).rolling(lookback, min_periods=1).max().to_numpy()
    lo48 = pd.Series(lo_levels[0]).rolling(lookback, min_periods=1).min().to_numpy()
    bull |= (on < hi48) & (cn > hi48) & (cn > h1)
    bear |= (on > lo48) & (cn < lo48) & (cn < l1)
    return bull, bear


class Devma(Base):
    """Port of "DEVMA strat NR 18/03" (Pine v6).

    Long when either:
      - a single bar closes out above the 3D upper band (band breakout,
        not on a bearish structure-break bar), or
      - a bullish structure break while the 2D trend-step midband sits
        above the 3D upper band, with the volatility EMA rising.
    Shorts are the mirror image. Exits (price or midband crossing back
    into the bands, or a midband rejection against the trend state) only
    fire while the volatility EMA is falling. Initial stop at the signal
    bar's low/high.

    Port notes: BitMEX BVOL7D replaced with realized 7-day volatility
    of the traded asset (same quantity, computed locally); position size
    capped at 100% equity (original could lever up unboundedly); the
    plot-only HMA/DEVMA lines are omitted from logic, as in the source.
    """
    vol_ma = 20    # EMA length on the volatility series (original: 20)
    vol_run = 5    # bars the EMA must rise/fall (original: 5)

    # Robustness-test knobs (not optimized; defaults match the original)
    band1 = "2D"        # trend step timeframe
    band2 = "3D"        # HL band timeframe
    vol_mode = "normal"  # 'normal' | 'off' | 'inverted'
    direction = "both"   # 'both' | 'long' | 'short'
    delay = 0            # act on signals this many bars late

    GRID = {"vol_ma": [10, 20, 40], "vol_run": [3, 5, 8]}
    WARMUP = 360

    def init(self):
        o, h, l, c = (self.data.Open.s, self.data.High.s,
                      self.data.Low.s, self.data.Close.s)

        b1 = htf_bands(h, l, c, self.band1)
        b2 = htf_bands(h, l, c, self.band2)
        bull, bear = structure_break_signals(o, h, l, c)

        # Volatility filter (stand-in for BITMEX:BVOL7D)
        bars_per_day = max(1, int(round(pd.Timedelta("1D") /
                                        (c.index[1] - c.index[0]))))
        rv = np.log(c / c.shift(1)).rolling(7 * bars_per_day).std()
        vma = rv.ewm(span=self.vol_ma, adjust=False).mean()
        d = vma.diff()
        vol_rising = ((d > 0).rolling(self.vol_run).min() == 1)
        vol_falling = ((d < 0).rolling(self.vol_run).min() == 1)

        on, cn = o.to_numpy(), c.to_numpy()
        up2, lo2 = b2.upper.to_numpy(), b2.lower.to_numpy()
        mid1, st1 = b1.mid.to_numpy(), b1.state.to_numpy()
        vr, vf = vol_rising.to_numpy(), vol_falling.to_numpy()
        if self.vol_mode == "off":
            vr = np.ones(len(cn), dtype=bool)
            vf = np.ones(len(cn), dtype=bool)
        elif self.vol_mode == "inverted":
            vr, vf = vf, vr

        long_breakout = (on < up2) & (cn > up2) & (cn > lo2) & ~bear
        long_trend = bull & (mid1 > up2) & vr
        short_breakout = (on > lo2) & (cn < lo2) & (cn < up2) & ~bull
        short_trend = bear & (mid1 < lo2) & vr

        def cross_under(a, b):
            a1 = np.concatenate([[np.nan], a[:-1]])
            b1_ = np.concatenate([[np.nan], b[:-1]])
            return (a1 >= b1_) & (a < b)

        def cross_over(a, b):
            a1 = np.concatenate([[np.nan], a[:-1]])
            b1_ = np.concatenate([[np.nan], b[:-1]])
            return (a1 <= b1_) & (a > b)

        hn, ln = h.to_numpy(), l.to_numpy()
        bear_rej_mid = (on < mid1) & (hn > mid1) & (cn < mid1)
        bull_rej_mid = (on > mid1) & (ln < mid1) & (cn > mid1)
        bear_cross = cross_under(cn, up2) | cross_under(cn, lo2)
        bull_cross = cross_over(cn, lo2) | cross_over(cn, up2)
        ma_bear_cross = cross_under(mid1, up2) | cross_under(mid1, lo2)
        ma_bull_cross = cross_over(mid1, lo2) | cross_over(mid1, up2)

        long_close = (((st1 < 0) & bear_rej_mid) | ma_bear_cross | bear_cross) & vf
        short_close = (((st1 > 0) & bull_rej_mid) | ma_bull_cross | bull_cross) & vf

        def f(x):
            x = x.astype(float)
            if self.delay:
                x = np.concatenate([np.zeros(self.delay), x[:-self.delay]])
            return x
        self.sig_long = self.I(lambda: f(long_breakout | long_trend), plot=False)
        self.sig_short = self.I(lambda: f(short_breakout | short_trend), plot=False)
        self.sig_long_close = self.I(lambda: f(long_close), plot=False)
        self.sig_short_close = self.I(lambda: f(short_close), plot=False)

    def next(self):
        if (self.sig_long[-1] > 0 and self.direction != "short"
                and not self.position.is_long):
            self.position.close()
            self.buy(sl=min(self.data.Low[-1], self.data.Close[-1] * 0.999))
        elif (self.sig_short[-1] > 0 and self.direction != "long"
                and not self.position.is_short):
            self.position.close()
            self.sell(sl=max(self.data.High[-1], self.data.Close[-1] * 1.001))
        elif self.position.is_long and self.sig_long_close[-1] > 0:
            self.position.close()
        elif self.position.is_short and self.sig_short_close[-1] > 0:
            self.position.close()


# ---------------------------------------------------------------------------
# 8. Combo - DEVMA chassis plus the Diamond Hands sweep as a second entry

class Combo(Devma):
    """DEVMA unchanged, with one addition: a sweep-reversal entry
    (Diamond Hands' trigger) taken in the direction of DEVMA's 2D
    trend-step. Breakout entries buy strength; sweep entries buy the
    pullback within the same regime. Exits and stops are DEVMA's.
    """
    lookback = 20   # sweep lookback (from Diamond Hands)

    GRID = {"vol_ma": [10, 20, 40], "vol_run": [3, 5, 8],
            "lookback": [20, 48]}

    def init(self):
        super().init()
        c, l, h = self.data.Close.s, self.data.Low.s, self.data.High.s
        lb = self.lookback
        prior_low_min = l.rolling(lb).min().shift(1)
        prior_close_min = c.rolling(lb).min().shift(1)
        prior_high_max = h.rolling(lb).max().shift(1)
        prior_close_max = c.rolling(lb).max().shift(1)
        sweep_long = ((l < prior_low_min) & (c > prior_close_min)).to_numpy()
        sweep_short = ((h > prior_high_max) & (c < prior_close_max)).to_numpy()

        # Recompute the trend-step state to gate sweeps by regime
        b1 = htf_bands(h, l, c, self.band1)
        st1 = b1.state.to_numpy()

        base_long = self.sig_long.s.to_numpy()
        base_short = self.sig_short.s.to_numpy()
        long_all = (base_long > 0) | (sweep_long & (st1 > 0))
        short_all = (base_short > 0) | (sweep_short & (st1 < 0))
        f = lambda x: x.astype(float)
        self.sig_long = self.I(lambda: f(long_all), plot=False)
        self.sig_short = self.I(lambda: f(short_all), plot=False)


REGISTRY = {
    "diamond_hands": DiamondHands,
    "trend_step": TrendStep,
    "hl_band_breakout": HLBandBreakout,
    "structure_break": StructureBreak,
    "open_rejection": OpenRejection,
    "vwap_rejection": VWAPRejection,
    "devma": Devma,
    "combo": Combo,
}


# ---------------------------------------------------------------------------
# Template for a new idea. Copy, rename, fill, then add to REGISTRY.
# Not registered — do not run check.py on this class.
# See ADDING-AN-IDEA.md.


class NewIdea(Base):
    """Copy, rename, fill init/next, then add the new name to REGISTRY."""
    period = 20
    GRID = {"period": [10, 20, 40]}
    WARMUP = 50

    def init(self):
        close = self.data.Close.s
        self.ma = self.I(lambda: close.rolling(self.period).mean(), plot=False)

    def next(self):
        if np.isnan(self.ma[-1]):
            return
        close = self.data.Close[-1]
        if close > self.ma[-1] and not self.position.is_long:
            self.position.close()
            self.buy()
        elif close < self.ma[-1] and not self.position.is_short:
            self.position.close()
            self.sell()
