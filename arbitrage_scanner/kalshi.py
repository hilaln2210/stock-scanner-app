"""
Kalshi data source: fetch binary markets from Kalshi Trade API.
https://docs.kalshi.com/ – no auth required for public market data.
"""

import logging
from typing import List
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from .config import Config
from .models import BinaryMarket

logger = logging.getLogger(__name__)

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
USER_AGENT = "Mozilla/5.0 (compatible; ArbitrageScanner/1.0)"


def _get(url: str) -> dict:
    req = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urlopen(req, timeout=20) as resp:
        import json
        return json.loads(resp.read().decode("utf-8"))


def fetch_binary_markets(config: Config | None = None) -> List[BinaryMarket]:
    """
    Fetch open binary markets from Kalshi. Uses yes_ask_dollars + no_ask_dollars
    (cost to buy YES and NO). Paginates until no more cursor.
    """
    markets: List[BinaryMarket] = []
    cursor = None
    limit = 200
    max_pages = 30
    for _ in range(max_pages):
        params = {"status": "open", "limit": limit}
        if cursor:
            params["cursor"] = cursor
        url = f"{KALSHI_BASE}/markets?{urlencode(params)}"
        try:
            data = _get(url)
        except (URLError, HTTPError, Exception) as e:
            logger.warning("Kalshi API error: %s", e)
            break
        raw = data.get("markets") or []
        for m in raw:
            if m.get("market_type") != "binary":
                continue
            yes_ask = float(m.get("yes_ask_dollars") or m.get("yes_ask") or 0)
            no_ask = float(m.get("no_ask_dollars") or m.get("no_ask") or 0)
            if yes_ask <= 0 and no_ask <= 0:
                continue
            ticker = m.get("ticker") or ""
            title = m.get("title") or m.get("yes_sub_title") or ticker
            liq = float(m.get("liquidity_dollars") or m.get("liquidity") or 0)
            spread_bps = 0
            markets.append(
                BinaryMarket(
                    market_id=ticker,
                    question=title[:500],
                    yes_price=yes_ask,
                    no_price=no_ask,
                    liquidity=liq,
                    spread_bps=spread_bps,
                    source="kalshi",
                )
            )
        cursor = data.get("cursor") or ""
        if not cursor or len(raw) < limit:
            break
    logger.info("Kalshi: loaded %d binary markets", len(markets))
    return markets
