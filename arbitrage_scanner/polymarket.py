"""
Polymarket data source: fetch real events and markets from Gamma API.
Read-only; no trading, no API keys required for public data.

הנתונים זהים לאתר Polymarket: Gamma API הוא מקור הנתונים של polymarket.com.
אימות: אירוע "MicroStrategy sells any Bitcoin by ___ ?" – שוק "December 31, 2026"
מציג באתר 16% Yes / 85% No; ב-Gamma outcomePrices ["0.155","0.845"] (תואם).

Connection details:
- Endpoint: GET https://gamma-api.polymarket.com/events
- Query params: active=true, closed=false, limit=N, offset=N (pagination)
- No authentication; public API. The server returns 403 without a browser-like
  User-Agent, so we send a standard Firefox User-Agent header.
- Uses stdlib only: urllib.request (no requests library).
"""

import json
import logging
from typing import List
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from .config import Config
from .models import BinaryMarket

logger = logging.getLogger(__name__)

GAMMA_BASE = "https://gamma-api.polymarket.com"
DEFAULT_LIMIT = 100
MAX_PAGES = 5  # cap pages to avoid rate limits

# Required: Gamma API blocks default Python User-Agent (403). Use browser-like header.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0"


def _get(url: str) -> list | dict:
    """Fetch JSON from URL. GET request with Accept + User-Agent. Raises on HTTP/connection errors."""
    req = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_events(
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    base_url: str = GAMMA_BASE,
) -> list[dict]:
    """Fetch one page of active, non-closed events from Gamma API."""
    params = {
        "active": "true",
        "closed": "false",
        "limit": limit,
        "offset": offset,
    }
    url = f"{base_url.rstrip('/')}/events?{urlencode(params)}"
    try:
        data = _get(url)
        return data if isinstance(data, list) else []
    except (URLError, HTTPError, json.JSONDecodeError) as e:
        logger.exception("Polymarket Gamma API request failed: %s", e)
        raise


def parse_outcome_prices(outcome_prices: str | list) -> list[float]:
    """Parse outcomePrices to list of floats. Returns [] on error."""
    if isinstance(outcome_prices, list):
        return [float(x) for x in outcome_prices[:2]]
    if isinstance(outcome_prices, str):
        try:
            arr = json.loads(outcome_prices)
            return [float(x) for x in arr[:2]]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return []


def market_to_binary(m: dict, event_title: str = "") -> BinaryMarket | None:
    """
    Convert a Polymarket market dict to BinaryMarket if it's active binary Yes/No.
    Returns None if closed, inactive, or not binary.
    """
    if m.get("closed") or not m.get("active", True):
        return None
    outcomes = m.get("outcomes")
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except json.JSONDecodeError:
            return None
    if not outcomes or len(outcomes) != 2:
        return None
    prices = parse_outcome_prices(m.get("outcomePrices", "[]"))
    if len(prices) != 2:
        return None
    # Map by outcome name (Polymarket usually has ["Yes", "No"] or ["No", "Yes"])
    labels = [str(o).strip().lower() for o in outcomes]
    yes_idx = next((i for i, l in enumerate(labels) if l == "yes"), None)
    no_idx = next((i for i, l in enumerate(labels) if l == "no"), None)
    if yes_idx is None or no_idx is None:
        return None
    yes_price, no_price = prices[yes_idx], prices[no_idx]
    liquidity = float(
        m.get("liquidityNum")
        or m.get("liquidityClob")
        or m.get("liquidity")
        or 0
    )
    spread = float(m.get("spread") or 0)
    spread_bps = round(spread * 10000)
    question = m.get("question") or event_title or m.get("id", "")
    return BinaryMarket(
        market_id=str(m.get("id", "")),
        question=question,
        yes_price=yes_price,
        no_price=no_price,
        liquidity=liquidity,
        spread_bps=spread_bps,
    )


def fetch_binary_markets(config: Config | None = None) -> List[BinaryMarket]:
    """
    Fetch active binary markets from Polymarket Gamma API.
    Paginates through events and flattens markets. No API key required.
    """
    limit = getattr(config, "polymarket_limit", DEFAULT_LIMIT) if config else DEFAULT_LIMIT
    base = getattr(config, "polymarket_gamma_url", GAMMA_BASE) if config else GAMMA_BASE
    seen_ids: set[str] = set()
    markets: List[BinaryMarket] = []
    offset = 0
    for page in range(MAX_PAGES):
        events = fetch_events(limit=limit, offset=offset, base_url=base)
        if not events:
            break
        for event in events:
            event_title = event.get("title") or ""
            for m in event.get("markets") or []:
                b = market_to_binary(m, event_title)
                if b and b.market_id and b.market_id not in seen_ids:
                    seen_ids.add(b.market_id)
                    markets.append(b)
        if len(events) < limit:
            break
        offset += limit
    logger.info("Polymarket: loaded %d binary markets", len(markets))
    return markets
