"""HTML visual of a check.py result. No pipeline run, no browser."""

import pandas as pd

import visual


def _result(**overrides):
    base = {
        "strategy": "devma",
        "timeframe": "12h",
        "direction": "both (long+short)",
        "preview": False,
        "window": "5793 12h bars, 2017-09-01 to 2025-08-06",
        "verdict": "LOOKS REAL",
        "checks": [
            {"name": "Made money out of sample",
             "detail": "PF 1.06 > 1.0", "ok": True},
            {"name": "Enough out-of-sample trades",
             "detail": "169 >= 30", "ok": True},
            {"name": "In-sample beats noise",
             "detail": "p 0.040 < 0.05", "ok": True},
            {"name": "Walk-forward beats noise",
             "detail": "p 0.016 < 0.05", "ok": True},
        ],
        "stage1": {
            "return_pct": 505.8, "bh_pct": 2308.2, "pf": 1.061,
            "max_dd": -64.9, "trades": 258,
        },
        "best_params": "{'vol_ma': 10, 'vol_run': 3}",
        "is_pf": 1.167,
        "p_is": 0.0399,
        "perm_is": [0.9, 1.0, 1.05, 0.95, 1.10, 0.88, 1.02],
        "wf_return_pct": 231.7,
        "wf_pf": 1.061,
        "wf_sharpe": 0.44,
        "wf_trades": 169,
        "wf_bh_pct": 767.4,
        "wf_equity": [
            {"t": "2019-09-01", "v": 100000},
            {"t": "2021-03-01", "v": 160000},
            {"t": "2023-01-01", "v": 210000},
            {"t": "2025-02-28", "v": 331700},
        ],
        "bh_equity": [
            {"t": "2019-09-01", "v": 100000},
            {"t": "2021-03-01", "v": 400000},
            {"t": "2023-01-01", "v": 500000},
            {"t": "2025-02-28", "v": 867400},
        ],
        "folds": [
            {"test_start": "2019-09-01",
             "params": {"vol_ma": 20, "vol_run": 3},
             "pf": 1.03, "trades": 21},
            {"test_start": "2024-08-30",
             "params": {"vol_ma": 20, "vol_run": 8},
             "pf": 0.99, "trades": 21},
        ],
        "p_wf": 0.0159,
        "perm_wf": [0.8, 0.9, 1.0, 0.95, 0.85, 1.02],
        "n_trials": 5,
        "n_after": 5,
        "corrected_bar": 0.01,
        "provisional": (
            "Passes at 0.05. With 5 trials the corrected bar is 0.0100. "
            "Treat LOOKS REAL as provisional."
        ),
    }
    base.update(overrides)
    return base


def test_verdict_is_the_you_step():
    html = visual.render(_result())
    assert 'class="verdict you"' in html
    assert "LOOKS REAL" in html
    assert "Worth paper-trading" in html
    assert "provisional" in html


def test_gates_mark_pass_and_fail():
    html = visual.render(_result(verdict="NOT PROVEN", checks=[
        {"name": "Made money out of sample", "detail": "PF 1.17 > 1.0",
         "ok": True},
        {"name": "Enough out-of-sample trades", "detail": "20 >= 30",
         "ok": False},
        {"name": "In-sample beats noise", "detail": "p 0.032 < 0.05",
         "ok": True},
        {"name": "Walk-forward beats noise", "detail": "p 0.636 < 0.05",
         "ok": False},
    ], provisional=None))
    assert html.count('class="gate pass"') == 2
    assert html.count('class="gate fail"') == 2
    assert "NOT PROVEN" in html
    assert "Do not risk money" in html or "would not want to risk" in html


def test_preview_banner_and_no_logged_chip():
    html = visual.render(_result(preview=True, n_trials=None, provisional=None))
    assert "display only" in html
    assert "logged trial" not in html


def test_equity_and_histograms_render():
    html = visual.render(_result())
    assert "<polyline" in html
    assert html.count("<polyline") == 2  # wf + buy-and-hold
    assert "Shuffle scores" in html
    assert "real 1.17" in html or "real 1.167" in html or "real 1.16" in html


def test_folds_table_escapes_and_shows_params():
    html = visual.render(_result())
    assert "vol_ma=20" in html
    assert "2019-09-01" in html


def test_stage1_is_present_and_caged():
    html = visual.render(_result())
    assert "this number proves nothing" in html
    assert "505.8%" in html


def test_html_escapes_injected_text():
    html = visual.render(_result(
        strategy="<script>alert(1)</script>",
        best_params="<img src=x>",
        folds=[{"test_start": "<b>x</b>", "params": {"a": "<y>"},
                "pf": 1.0, "trades": 1}],
    ))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img src=x&gt;" in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html


def test_empty_optional_sections_do_not_crash():
    html = visual.render({
        "strategy": "x", "timeframe": "1d", "verdict": "NO EDGE",
        "preview": True,
    })
    assert "NO EDGE" in html
    assert "consistent with luck" in html
    assert "No walk-forward equity" in html


def test_write_creates_file(tmp_path):
    path = tmp_path / "last_run.html"
    out = visual.write(_result(), path=str(path))
    assert out == str(path)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("<!DOCTYPE html>")
    assert "LOOKS REAL" in text


def test_points_from_series_includes_last_and_skips_nan():
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    s = pd.Series([100.0, 101.0, float("nan"), 103.0, 104.0,
                   105.0, 106.0, 107.0, 108.0, 109.0], index=idx)
    pts = visual.points_from_series(s, n=4)
    assert pts[0]["t"] == "2020-01-01"
    assert pts[-1]["t"] == "2020-01-10"
    assert pts[-1]["v"] == 109.0
    assert all(p["v"] == p["v"] for p in pts)  # no NaN


def test_equity_axis_uses_compact_labels():
    html = visual.render(_result())
    assert "867k" in html or "913k" in html or "100k" in html
    assert "913,444" not in html


def test_main_exits_when_last_run_missing(tmp_path):
    missing = tmp_path / "last_run.html"
    try:
        visual.main(path=str(missing))
    except SystemExit as e:
        assert e.code == 1
    else:
        raise AssertionError("expected SystemExit")


def test_main_opens_existing_file(tmp_path, monkeypatch):
    path = tmp_path / "last_run.html"
    path.write_text("<html></html>", encoding="utf-8")
    opened = []
    monkeypatch.setattr(visual, "open_in_browser", opened.append)
    visual.main(path=str(path))
    assert opened == [str(path)]


def test_inf_scores_do_not_crash():
    html = visual.render(_result(
        is_pf=float("inf"),
        perm_is=[1.0, 1.1, float("inf"), 0.9],
        wf_pf=float("inf"),
    ))
    assert "LOOKS REAL" in html
