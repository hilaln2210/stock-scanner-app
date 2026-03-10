"""
Manifold Markets data source: fetch binary markets from Manifold API.
https://docs.manifold.markets/api – no auth for read. Uses play money (mana).
"""

import json
import logging
from typing import List
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from .models import BinaryMarket

logger = logging.getLogger(__name__)

MANIFOLD_BASE = "https://api.manifold.markets/v0"
USER_AGENT = "Mozilla/5.0 (compatible; ArbitrageScanner/1.0)"


def _get(url: str) -> list | dict:
    req = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_binary_markets(limit: int = 500) -> List[BinaryMarket]:
    """
    Fetch binary markets from Manifold. Uses probability as YES price and
    1 - probability as NO price (approximation; real cost depends on AMM).
    """
    markets: List[BinaryMarket] = []
    try:
        data = _get(f"{MANIFOLD_BASE}/markets?limit={limit}")
    except (URLError, HTTPError, json.JSONDecodeError) as e:
        logger.warning("Manifold API error: %s", e)
        return markets
    if not isinstance(data, list):
        return markets
    for m in data:
        if m.get("outcomeType") != "BINARY" or m.get("isResolved"):
            continue
        prob = float(m.get("probability") or 0.5)
        yes_price = prob
        no_price = 1.0 - prob
        mid = m.get("id") or ""
        question = (m.get("question") or "")[:500]
        pool = m.get("pool") or {}
        liq = float(pool.get("YES") or 0) + float(pool.get("NO") or 0)
        if liq <= 0:
            liq = float(m.get("totalLiquidity") or 0)
        markets.append(
            BinaryMarket(
                market_id=mid,
                question=question,
                yes_price=yes_price,
                no_price=no_price,
                liquidity=liq,
                spread_bps=0,
                source="manifold",
            )
        )
    logger.info("Manifold: loaded %d binary markets", len(markets))
    return markets
