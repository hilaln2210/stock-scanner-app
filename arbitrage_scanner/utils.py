"""
Utilities: JSON loading, logging setup, and shared helpers.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

from .models import BinaryMarket, MultiOutcomeMarket, Outcome


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger for the scanner package."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def load_json(path: Path) -> Any:
    """Load and parse a JSON file. Raises FileNotFoundError or json.JSONDecodeError."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_binary_markets(data: list[dict], source: str = "mock") -> list[BinaryMarket]:
    """Parse list of dicts into BinaryMarket objects. source='mock' for demo data."""
    markets: list[BinaryMarket] = []
    for m in data:
        markets.append(
            BinaryMarket(
                market_id=str(m["market_id"]),
                question=str(m["question"]),
                yes_price=float(m["yes_price"]),
                no_price=float(m["no_price"]),
                liquidity=float(m.get("liquidity", 0)),
                spread_bps=float(m.get("spread_bps", 0)),
                source=source,
            )
        )
    return markets


def parse_multi_outcome_markets(data: list[dict]) -> list[MultiOutcomeMarket]:
    """Parse list of dicts into MultiOutcomeMarket objects."""
    markets: list[MultiOutcomeMarket] = []
    for m in data:
        outcomes = [
            Outcome(
                outcome_id=str(o["outcome_id"]),
                name=str(o["name"]),
                price=float(o["price"]),
                liquidity=float(o.get("liquidity", 0)),
            )
            for o in m["outcomes"]
        ]
        markets.append(
            MultiOutcomeMarket(
                market_id=str(m["market_id"]),
                question=str(m["question"]),
                outcomes=outcomes,
            )
        )
    return markets


def load_binary_markets(path: Path, source: str = "mock") -> list[BinaryMarket]:
    """Load binary markets from a JSON file. source='mock' so UI shows these are demo."""
    raw = load_json(path)
    if isinstance(raw, dict) and "markets" in raw:
        raw = raw["markets"]
    return parse_binary_markets(raw, source=source)


def load_multi_outcome_markets(path: Path) -> list[MultiOutcomeMarket]:
    """Load multi-outcome markets from a JSON file."""
    raw = load_json(path)
    if isinstance(raw, dict) and "markets" in raw:
        raw = raw["markets"]
    return parse_multi_outcome_markets(raw)
