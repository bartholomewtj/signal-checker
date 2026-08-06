"""The signal under test: "Diamond Hands" sweep reversal.

Ported from the original TradingView Pine Script, simplified and with the
backtest-inflating bugs removed:

- Trend filter is a plain moving average of close (the original used a
  SuperTrend built on Heikin Ashi candles — smoothed synthetic prices).
- Position size is capped at 100% of equity, no hidden leverage
  (the original could size up to hundreds of times equity when the
  stop was close to the entry).
- Fills happen at the NEXT bar's open, with commission and spread.

The idea being tested: when price sweeps below the recent low but closes
back above it (a "stop run"), and the broader trend agrees, price tends
to keep going in the trend direction.
"""

from backtesting import Strategy
from backtesting.lib import crossover


def rolling_min(series, window):
    return series.rolling(window).min()


def rolling_max(series, window):
    return series.rolling(window).max()


def sma(series, window):
    return series.rolling(window).mean()


class DiamondHands(Strategy):
    # Default parameters (the walk-forward re-picks these on each fold)
    lookback = 20    # how many bars define the "recent" low/high
    trend_len = 200  # moving-average length for the trend filter

    def init(self):
        close = self.data.Close.s
        low = self.data.Low.s
        high = self.data.High.s

        # All windows end at the PREVIOUS bar (shift(1)) so the current
        # bar is compared against history it hasn't touched.
        self.prior_low_min = self.I(
            lambda: rolling_min(low, self.lookback).shift(1), name="prior_low_min", plot=False)
        self.prior_close_min = self.I(
            lambda: rolling_min(close, self.lookback).shift(1), name="prior_close_min", plot=False)
        self.prior_high_max = self.I(
            lambda: rolling_max(high, self.lookback).shift(1), name="prior_high_max", plot=False)
        self.prior_close_max = self.I(
            lambda: rolling_max(close, self.lookback).shift(1), name="prior_close_max", plot=False)
        self.trend = self.I(
            lambda: sma(close, self.trend_len), name="trend", plot=False)

    def next(self):
        import math
        if math.isnan(self.trend[-1]) or math.isnan(self.prior_low_min[-1]):
            return

        close = self.data.Close[-1]
        low = self.data.Low[-1]
        high = self.data.High[-1]

        # Sweep below recent lows, but close back above the lowest prior
        # close, with the trend pointing up -> long.
        long_signal = (
            low < self.prior_low_min[-1]
            and close > self.prior_close_min[-1]
            and close > self.trend[-1]
        )
        # Mirror image for shorts.
        short_signal = (
            high > self.prior_high_max[-1]
            and close < self.prior_close_max[-1]
            and close < self.trend[-1]
        )

        if long_signal and not self.position.is_long:
            self.position.close()
            self.buy()
        elif short_signal and not self.position.is_short:
            self.position.close()
            self.sell()
        # Exit when price crosses the trend line against the position.
        elif self.position.is_long and close < self.trend[-1]:
            self.position.close()
        elif self.position.is_short and close > self.trend[-1]:
            self.position.close()


# The parameter grid the optimizer is allowed to search. Small on purpose:
# a big grid makes overfitting easier and the honesty test slower.
PARAM_GRID = {
    "lookback": [12, 20, 30, 48],
    "trend_len": [100, 200, 300],
}

# Bars needed before indicators are fully formed.
WARMUP = max(PARAM_GRID["trend_len"]) + 1
