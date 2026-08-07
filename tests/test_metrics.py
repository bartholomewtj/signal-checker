"""Edge-case tests for check.profit_factor, check.trade_profit_factor and
check.pvalue."""

import numpy as np
import pandas as pd
import pytest

from check import profit_factor, pvalue, trade_profit_factor


# ---------------------------------------------------------------------------
# profit_factor (per-bar returns)

def test_profit_factor_all_gains_is_inf():
    rets = pd.Series([0.01, 0.02, 0.03])
    assert profit_factor(rets) == np.inf


def test_profit_factor_all_losses_is_zero():
    rets = pd.Series([-0.01, -0.02, -0.03])
    assert profit_factor(rets) == 0.0


def test_profit_factor_empty_is_zero():
    rets = pd.Series([], dtype=float)
    assert profit_factor(rets) == 0.0


def test_profit_factor_mixed_matches_hand_computation():
    rets = pd.Series([0.02, -0.01, 0.03, -0.02, 0.0])
    # gains = 0.02 + 0.03 = 0.05; losses = 0.01 + 0.02 = 0.03
    expected = 0.05 / 0.03
    assert profit_factor(rets) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# trade_profit_factor (trade-level PnL)

def _fake_stats(rows):
    """A minimal stand-in for backtesting's stats dict: just `_trades`
    with the columns trade_profit_factor reads."""
    return {"_trades": pd.DataFrame(rows)}


def test_trade_profit_factor_no_trades_is_zero(tiny_frame):
    stats = _fake_stats([])
    assert trade_profit_factor(stats, tiny_frame) == 0.0


def test_trade_profit_factor_all_winning_is_inf(tiny_frame):
    stats = _fake_stats([
        {"Size": 1, "EntryBar": 0, "ExitBar": 2, "EntryPrice": 100.0, "PnL": 50.0},
        {"Size": 1, "EntryBar": 3, "ExitBar": 5, "EntryPrice": 100.0, "PnL": 20.0},
    ])
    assert trade_profit_factor(stats, tiny_frame) == np.inf


def test_trade_profit_factor_all_losing_is_zero(tiny_frame):
    stats = _fake_stats([
        {"Size": 1, "EntryBar": 0, "ExitBar": 2, "EntryPrice": 100.0, "PnL": -50.0},
        {"Size": 1, "EntryBar": 3, "ExitBar": 5, "EntryPrice": 100.0, "PnL": -20.0},
    ])
    assert trade_profit_factor(stats, tiny_frame) == 0.0


def test_trade_profit_factor_mixed_matches_hand_computation(tiny_frame):
    stats = _fake_stats([
        {"Size": 1, "EntryBar": 0, "ExitBar": 2, "EntryPrice": 100.0, "PnL": 30.0},
        {"Size": 1, "EntryBar": 3, "ExitBar": 5, "EntryPrice": 100.0, "PnL": -10.0},
    ])
    assert trade_profit_factor(stats, tiny_frame) == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# pvalue

def test_pvalue_no_shuffle_beats_real():
    perm_scores = [0.1, 0.2, 0.3]
    # (1 + 0) / (1 + 3) = 0.25
    assert pvalue(1.0, perm_scores) == pytest.approx(0.25)


def test_pvalue_every_shuffle_beats_real():
    perm_scores = [2.0, 3.0, 4.0]
    # (1 + 3) / (1 + 3) = 1.0
    assert pvalue(1.0, perm_scores) == pytest.approx(1.0)


def test_pvalue_empty_perm_scores_is_one():
    assert pvalue(1.0, []) == pytest.approx(1.0)
