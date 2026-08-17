"""Named-idea refine path. No VectorBT, no pipeline, no planted-edge runner."""

import json

import pytest

from refine import (
    questions_for,
    spec_from_answers,
    resolve_name,
    map_symbol,
    main,
)
from strategies import REGISTRY


def test_vague_idea_yields_questions_on_testable_dimensions():
    questions = questions_for("buy the dip")
    blob = " ".join(
        f"{q['id']} {q['dimension']} {q['prompt']}".lower() for q in questions
    )
    assert "asset" in blob or "universe" in blob
    assert "entry" in blob
    assert "exit" in blob or "hold" in blob
    assert "horizon" in blob or "evaluation" in blob


def test_empty_idea_is_rejected():
    with pytest.raises(ValueError):
        questions_for("   ")


def test_named_ideas_resolve_to_registry():
    assert resolve_name("DEVMA") == "devma"
    assert resolve_name("sweep reversal") == "diamond_hands"
    assert resolve_name("hl band breakout") == "hl_band_breakout"
    for name in REGISTRY:
        assert resolve_name(name) == name


def test_unknown_idea_is_rejected():
    with pytest.raises(ValueError, match="Named ideas only"):
        spec_from_answers(
            "buy the dip",
            {"asset": "BTC", "entry": "buy a 5% dip", "exit": "native", "horizon": "all"},
        )


def test_spec_maps_asset_and_named_entry():
    spec = spec_from_answers(
        "try DEVMA on bitcoin",
        {"asset": "BTC", "entry": "devma", "exit": "native", "horizon": "all"},
    )
    assert spec == {"strategy": "devma", "symbol": "BTC/USDT", "horizon": "all"}


def test_eth_and_etf_mapping():
    assert map_symbol("ETH-USD") == "ETH/USDT"
    assert map_symbol("SPY") == "SPY"
    with pytest.raises(ValueError, match="closed list"):
        map_symbol("AAPL")


def test_missing_answers_rejected():
    with pytest.raises(ValueError, match="Missing"):
        spec_from_answers("devma", {"asset": "BTC"})


def test_questions_cli(capsys):
    assert main(["questions", "--idea", "devma"]) == 0
    out = capsys.readouterr().out.lower()
    assert "asset" in out
    assert "entry" in out
    assert "exit" in out or "hold" in out
    assert "horizon" in out


def test_spec_cli(tmp_path, capsys):
    answers = tmp_path / "answers.json"
    answers.write_text(
        json.dumps(
            {"asset": "ETH-USD", "entry": "diamond hands", "exit": "native", "horizon": "all"}
        ),
        encoding="utf-8",
    )
    assert main(["spec", "--idea", "sweep reversal", "--answers", str(answers)]) == 0
    spec = json.loads(capsys.readouterr().out)
    assert spec["strategy"] == "diamond_hands"
    assert spec["symbol"] == "ETH/USDT"
