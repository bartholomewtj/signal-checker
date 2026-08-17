"""Vague idea → four questions → a named strategy spec.

No LLM. Named ideas only — they resolve to `strategies.REGISTRY` keys.
Free-form dip/SMA rules are out of this module.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from strategies import REGISTRY

ETF_UNIVERSE = ("SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "GLD")
CRYPTO_UNIVERSE = (
    "BTC/USDT",
    "ETH/USDT",
    "BNB/USDT",
    "XRP/USDT",
    "ADA/USDT",
    "LTC/USDT",
    "DOGE/USDT",
    "SOL/USDT",
)
ALLOWED_SYMBOLS = ETF_UNIVERSE + CRYPTO_UNIVERSE

ALIASES = {
    "diamond hands": "diamond_hands",
    "sweep reversal": "diamond_hands",
    "trend step": "trend_step",
    "trend shifts": "trend_step",
    "hl band": "hl_band_breakout",
    "hl band breakout": "hl_band_breakout",
    "structure break": "structure_break",
    "open rejection": "open_rejection",
    "vwap rejection": "vwap_rejection",
    "devma": "devma",
    "combo": "combo",
}

QUESTION_TEMPLATE = (
    {
        "id": "asset",
        "dimension": "asset/universe",
        "prompt": (
            "Which asset? Crypto: BTC/USDT, ETH/USDT, BNB/USDT, XRP/USDT, "
            "ADA/USDT, LTC/USDT, DOGE/USDT, SOL/USDT. "
            "ETFs: SPY, QQQ, IWM, EFA, EEM, TLT, GLD."
        ),
    },
    {
        "id": "entry",
        "dimension": "entry",
        "prompt": (
            "Which named idea? "
            + ", ".join(sorted(REGISTRY))
            + "."
        ),
    },
    {
        "id": "exit",
        "dimension": "exit or hold",
        "prompt": "Exit rule? Named ideas use their own exits. Answer 'native'.",
    },
    {
        "id": "horizon",
        "dimension": "evaluation horizon",
        "prompt": "Evaluation horizon? Use 'all' unless you have a reason not to.",
    },
)


def questions_for(idea: str) -> list[dict[str, str]]:
    if not str(idea).strip():
        raise ValueError("idea is empty")
    return [dict(q) for q in QUESTION_TEMPLATE]


def resolve_name(text: str) -> str | None:
    key = text.strip().lower().replace("-", " ").replace("_", " ")
    if key in ALIASES:
        return ALIASES[key]
    compact = key.replace(" ", "_")
    if compact in REGISTRY:
        return compact
    for name in REGISTRY:
        if name.replace("_", " ") in key or name in key:
            return name
    return None


def map_symbol(text: str) -> str:
    raw = text.strip().upper().replace(" ", "")
    aliases = {
        "BTC": "BTC/USDT",
        "BTC-USD": "BTC/USDT",
        "BTC-USDT": "BTC/USDT",
        "BTC/USD": "BTC/USDT",
        "BITCOIN": "BTC/USDT",
        "ETH": "ETH/USDT",
        "ETH-USD": "ETH/USDT",
        "ETH-USDT": "ETH/USDT",
        "ETH/USD": "ETH/USDT",
        "ETHEREUM": "ETH/USDT",
    }
    for base in ("BNB", "XRP", "ADA", "LTC", "DOGE", "SOL"):
        aliases[base] = f"{base}/USDT"
        aliases[f"{base}-USD"] = f"{base}/USDT"
        aliases[f"{base}-USDT"] = f"{base}/USDT"
        aliases[f"{base}/USD"] = f"{base}/USDT"
    symbol = aliases.get(raw, raw.replace("-", "/"))
    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError(
            f"Asset {text!r} is not in the closed list {ALLOWED_SYMBOLS}."
        )
    return symbol


def spec_from_answers(idea: str, answers: dict[str, str]) -> dict[str, Any]:
    missing = [q["id"] for q in QUESTION_TEMPLATE if not str(answers.get(q["id"], "")).strip()]
    if missing:
        raise ValueError(f"Missing answers for: {', '.join(missing)}")
    name = resolve_name(answers["entry"]) or resolve_name(idea)
    if not name:
        raise ValueError(
            "Named ideas only. Say one of: "
            + ", ".join(sorted(REGISTRY))
            + "."
        )
    return {
        "strategy": name,
        "symbol": map_symbol(answers["asset"]),
        "horizon": str(answers["horizon"]).strip(),
    }


def load_answers(path: str | Path) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("answers file must be a JSON object")
    return {str(key): str(value) for key, value in data.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vague idea → named strategy spec")
    sub = parser.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("questions", help="print the four clarifying questions")
    q.add_argument("--idea", required=True)
    s = sub.add_parser("spec", help="build a spec from an answers JSON file")
    s.add_argument("--idea", required=True)
    s.add_argument("--answers", required=True)
    args = parser.parse_args(argv)
    if args.cmd == "questions":
        print(json.dumps(questions_for(args.idea), indent=2))
        return 0
    spec = spec_from_answers(args.idea, load_answers(args.answers))
    print(json.dumps(spec, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
