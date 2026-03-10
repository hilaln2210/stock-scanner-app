"""Unit tests for utils."""

import json
import tempfile
from pathlib import Path

import pytest

from arbitrage_scanner.utils import (
    load_json,
    parse_binary_markets,
    parse_multi_outcome_markets,
    load_binary_markets,
    load_multi_outcome_markets,
)


def test_load_json() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"a": 1, "b": [2, 3]}, f)
        path = Path(f.name)
    try:
        data = load_json(path)
        assert data["a"] == 1
        assert data["b"] == [2, 3]
    finally:
        path.unlink(missing_ok=True)


def test_load_json_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_json(Path("/nonexistent/path/file.json"))


def test_parse_binary_markets() -> None:
    data = [
        {
            "market_id": "m1",
            "question": "Q?",
            "yes_price": 0.45,
            "no_price": 0.52,
            "liquidity": 1000,
            "spread_bps": 100,
        }
    ]
    markets = parse_binary_markets(data)
    assert len(markets) == 1
    assert markets[0].market_id == "m1"
    assert markets[0].yes_price == 0.45
    assert markets[0].no_price == 0.52
    assert markets[0].liquidity == 1000


def test_parse_binary_markets_defaults() -> None:
    data = [{"market_id": "m1", "question": "Q?", "yes_price": 0.5, "no_price": 0.5}]
    markets = parse_binary_markets(data)
    assert markets[0].liquidity == 0
    assert markets[0].spread_bps == 0


def test_parse_multi_outcome_markets() -> None:
    data = [
        {
            "market_id": "multi1",
            "question": "Q?",
            "outcomes": [
                {"outcome_id": "A", "name": "A", "price": 0.33, "liquidity": 500},
                {"outcome_id": "B", "name": "B", "price": 0.67, "liquidity": 500},
            ],
        }
    ]
    markets = parse_multi_outcome_markets(data)
    assert len(markets) == 1
    assert len(markets[0].outcomes) == 2
    assert markets[0].outcomes[0].price == 0.33
    assert markets[0].total_price() == 1.0


def test_load_binary_markets_from_list(tmp_path: Path) -> None:
    j = [
        {"market_id": "x", "question": "Q?", "yes_price": 0.4, "no_price": 0.55, "liquidity": 100},
    ]
    path = tmp_path / "binary.json"
    path.write_text(json.dumps(j), encoding="utf-8")
    markets = load_binary_markets(path)
    assert len(markets) == 1
    assert markets[0].market_id == "x"


def test_load_binary_markets_from_dict_with_markets_key(tmp_path: Path) -> None:
    j = {"markets": [{"market_id": "y", "question": "Q?", "yes_price": 0.5, "no_price": 0.5}]}
    path = tmp_path / "binary2.json"
    path.write_text(json.dumps(j), encoding="utf-8")
    markets = load_binary_markets(path)
    assert len(markets) == 1
    assert markets[0].market_id == "y"
