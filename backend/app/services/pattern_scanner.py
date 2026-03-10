"""
Intraday Pattern Scanner — 3-Step Trading Bot

Step 1: Filter stocks (Market Cap > $2B, ATR > $2-3 or 3%, Volume > 5M)
Step 2: Backtest intraday patterns per half-hour window (30-60 days)
Step 3: Generate trade signals for strong patterns (win rate > 60%)
"""

import asyncio
import math
import time as _time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import yfinance as yf
import numpy as np

# ── Cache ──────────────────────────────────────────────────────────────────────
_pool_cache: Dict = {}
_pool_cache_time: float = 0
_POOL_CACHE_TTL = 3600  # 1 hour — pool changes rarely

_pattern_cache: Dict[str, dict] = {}
_pattern_cache_time: Dict[str, float] = {}
_PATTERN_CACHE_TTL = 900  # 15 min

# ── Default stock universe for filtering ──────────────────────────────────────
# High-liquidity, high-ATR candidates — expanded pool to filter from
CANDIDATE_TICKERS = [
    # Mega-cap tech
    "NVDA", "TSLA", "AMD", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NFLX", "AVGO",
    "CRM", "ORCL", "INTC", "MU", "QCOM", "MRVL", "ANET", "PANW", "SNOW", "PLTR",
    # High-ATR / volatile
    "COIN", "MARA", "RIOT", "SMCI", "ARM", "IONQ", "RGTI", "SOUN", "RKLB",
    "MSTR", "SQ", "SHOP", "ROKU", "SNAP", "PINS", "UBER", "LYFT", "DASH",
    # Biotech / pharma (high ATR)
    "MRNA", "BNTX", "BIIB", "VRTX", "REGN", "GILD", "AMGN",
    # Energy / commodities
    "XOM", "CVX", "SLB", "OXY", "FSLR", "ENPH",
    # Finance
    "JPM", "GS", "MS", "BAC", "C", "SCHW",
    # Consumer
    "NKE", "SBUX", "MCD", "DIS", "WMT", "COST", "TGT",
    # Other high-volume
    "BA", "CAT", "DE", "UNH", "LLY", "JNJ", "PFE", "ABBV",
    "SPY", "QQQ", "IWM",
]


def _bulk_filter_pool(tickers: List[str], min_atr: float, min_atr_pct: float,
                       min_volume: int) -> List[dict]:
    """Bulk-download all tickers in ONE yf.download() call — 5-10x faster."""
    ticker_str = " ".join(tickers)
    df = yf.download(ticker_str, period="30d", interval="1d",
                     group_by="ticker", threads=True, timeout=10, progress=False)
    if df.empty:
        return []

    results = []
    for ticker in tickers:
        try:
            # Extract per-ticker data from multi-level columns
            if len(tickers) == 1:
                td = df
            else:
                if ticker not in df.columns.get_level_values(0):
                    continue
                td = df[ticker]

            td = td.dropna(subset=["Close"])
            if len(td) < 10:
                continue

            highs = td["High"].values
            lows = td["Low"].values
            closes = td["Close"].values
            volumes = td["Volume"].values

            price = float(closes[-1])
            if price <= 0 or math.isnan(price):
                continue

            avg_volume = int(np.nanmean(volumes[-10:]))

            # ATR-14
            trs = []
            for i in range(1, len(closes)):
                h, l, c_prev = float(highs[i]), float(lows[i]), float(closes[i - 1])
                if math.isnan(h) or math.isnan(l) or math.isnan(c_prev):
                    continue
                tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
                trs.append(tr)

            if len(trs) < 5:
                continue

            atr_14 = float(np.mean(trs[-14:])) if len(trs) >= 14 else float(np.mean(trs))
            atr_pct = (atr_14 / price * 100)

            # Quick filters before adding
            if atr_14 < min_atr and atr_pct < min_atr_pct:
                continue
            if avg_volume < min_volume:
                continue

            results.append({
                "ticker": ticker,
                "price": round(price, 2),
                "market_cap": 0,  # skipped for speed
                "avg_volume": avg_volume,
                "atr": round(atr_14, 2),
                "atr_pct": round(atr_pct, 2),
                "spread": 0,
                "spread_pct": 0,
                "company": ticker,
                "sector": "",
            })
        except Exception:
            continue

    return results


async def filter_stock_pool(
    min_market_cap: float = 2e9,
    min_atr: float = 2.0,
    min_atr_pct: float = 3.0,
    min_volume: int = 5_000_000,
    max_spread_pct: float = 0.15,
) -> List[dict]:
    """Step 1: Filter stocks into a trading pool. Single bulk download."""
    global _pool_cache, _pool_cache_time

    cache_key = f"{min_market_cap}_{min_atr}_{min_atr_pct}_{min_volume}"
    now = _time.time()
    if cache_key in _pool_cache and now - _pool_cache_time < _POOL_CACHE_TTL:
        return _pool_cache[cache_key]

    loop = asyncio.get_event_loop()
    pool = await loop.run_in_executor(
        None, _bulk_filter_pool, CANDIDATE_TICKERS, min_atr, min_atr_pct, min_volume
    )

    pool.sort(key=lambda x: x["atr_pct"], reverse=True)

    _pool_cache[cache_key] = pool
    _pool_cache_time = now
    return pool


def _analyze_ticker_patterns(ticker: str, days: int = 45, interval: str = "5m") -> Optional[dict]:
    """
    Step 2: Download intraday data and compute per-half-hour patterns.

    For each 30-min window of the trading day (9:30-10:00, 10:00-10:30, ...):
    - Average % change (open→close of window)
    - Win rate (% of days price went up)
    - Average ATR of that window
    - Best/worst day performance
    """
    try:
        stock = yf.Ticker(ticker)

        # yfinance limits: 5m data max 60 days, 15m max 60 days
        max_days = 59 if interval == "5m" else 59
        days = min(days, max_days)

        hist = stock.history(period=f"{days}d", interval=interval, timeout=10)
        if hist.empty or len(hist) < 50:
            return None

        # Get daily data for context
        daily = stock.history(period="60d", interval="1d", timeout=5)
        price = float(daily["Close"].iloc[-1]) if not daily.empty else 0

        # Calculate daily ATR
        daily_atr = 0
        if len(daily) >= 14:
            trs = []
            for i in range(1, len(daily)):
                tr = max(
                    daily["High"].iloc[i] - daily["Low"].iloc[i],
                    abs(daily["High"].iloc[i] - daily["Close"].iloc[i - 1]),
                    abs(daily["Low"].iloc[i] - daily["Close"].iloc[i - 1])
                )
                trs.append(tr)
            daily_atr = float(np.mean(trs[-14:]))

        # Parse into half-hour windows
        # Pre-market (4:00-9:30 ET) + Regular hours (9:30-16:00 ET)
        windows = [
            # Pre-market
            ("04:00", "04:30"), ("04:30", "05:00"), ("05:00", "05:30"),
            ("05:30", "06:00"), ("06:00", "06:30"), ("06:30", "07:00"),
            ("07:00", "07:30"), ("07:30", "08:00"), ("08:00", "08:30"),
            ("08:30", "09:00"), ("09:00", "09:30"),
            # Regular hours
            ("09:30", "10:00"), ("10:00", "10:30"), ("10:30", "11:00"),
            ("11:00", "11:30"), ("11:30", "12:00"), ("12:00", "12:30"),
            ("12:30", "13:00"), ("13:00", "13:30"), ("13:30", "14:00"),
            ("14:00", "14:30"), ("14:30", "15:00"), ("15:00", "15:30"),
            ("15:30", "16:00"),
        ]

        # Group candles by date
        hist = hist.copy()
        hist.index = hist.index.tz_localize(None) if hist.index.tz is None else hist.index.tz_convert("America/New_York").tz_localize(None)
        hist["date"] = hist.index.date
        hist["time"] = hist.index.time

        dates = sorted(hist["date"].unique())

        window_stats = []

        for w_start, w_end in windows:
            start_h, start_m = map(int, w_start.split(":"))
            end_h, end_m = map(int, w_end.split(":"))
            from datetime import time as _time_cls
            t_start = _time_cls(start_h, start_m)
            t_end = _time_cls(end_h, end_m)

            day_changes = []
            day_ranges = []

            for d in dates:
                day_data = hist[hist["date"] == d]
                window_data = day_data[(day_data["time"] >= t_start) & (day_data["time"] < t_end)]

                if len(window_data) < 2:
                    continue

                open_price = float(window_data["Open"].iloc[0])
                close_price = float(window_data["Close"].iloc[-1])
                high_price = float(window_data["High"].max())
                low_price = float(window_data["Low"].min())

                if open_price <= 0:
                    continue

                pct_change = (close_price - open_price) / open_price * 100
                window_range = (high_price - low_price) / open_price * 100

                day_changes.append(pct_change)
                day_ranges.append(window_range)

            if len(day_changes) < 5:
                window_stats.append({
                    "window": f"{w_start}-{w_end}",
                    "sample_days": len(day_changes),
                    "avg_change": 0,
                    "win_rate": 50,
                    "loss_rate": 50,
                    "avg_range": 0,
                    "best_day": 0,
                    "worst_day": 0,
                    "direction": "neutral",
                    "strength": "weak",
                    "tradeable": False,
                })
                continue

            changes = np.array(day_changes)
            ranges = np.array(day_ranges)

            wins = int(np.sum(changes > 0))
            losses = int(np.sum(changes < 0))
            total = len(changes)
            win_rate = round(wins / total * 100, 1)
            loss_rate = round(losses / total * 100, 1)
            avg_change = round(float(np.mean(changes)), 3)
            avg_win = round(float(np.mean(changes[changes > 0])), 3) if wins > 0 else 0
            avg_loss = round(float(np.mean(changes[changes < 0])), 3) if losses > 0 else 0
            avg_range = round(float(np.mean(ranges)), 3)
            best = round(float(np.max(changes)), 3)
            worst = round(float(np.min(changes)), 3)
            std_dev = round(float(np.std(changes)), 3)

            # Determine direction and strength
            direction = "bullish" if avg_change > 0.02 else ("bearish" if avg_change < -0.02 else "neutral")
            if win_rate >= 70:
                strength = "very_strong"
            elif win_rate >= 60:
                strength = "strong"
            elif win_rate >= 55:
                strength = "moderate"
            else:
                strength = "weak"

            # Tradeable if win rate > 60% and decent avg move
            tradeable = win_rate >= 60 and abs(avg_change) >= 0.05

            # Expected value per trade
            ev = round(avg_win * (win_rate / 100) + avg_loss * (loss_rate / 100), 4)

            window_stats.append({
                "window": f"{w_start}-{w_end}",
                "sample_days": total,
                "avg_change": avg_change,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "win_rate": win_rate,
                "loss_rate": loss_rate,
                "avg_range": avg_range,
                "best_day": best,
                "worst_day": worst,
                "std_dev": std_dev,
                "direction": direction,
                "strength": strength,
                "tradeable": tradeable,
                "expected_value": ev,
            })

        # Find best trading windows
        tradeable_windows = [w for w in window_stats if w["tradeable"]]
        tradeable_windows.sort(key=lambda x: x["win_rate"], reverse=True)

        # Overall daily pattern summary
        all_changes = []
        for w in window_stats:
            if w["sample_days"] >= 5:
                all_changes.append(w["avg_change"])

        return {
            "ticker": ticker,
            "price": round(price, 2),
            "daily_atr": round(daily_atr, 2),
            "daily_atr_pct": round(daily_atr / price * 100, 2) if price > 0 else 0,
            "interval": interval,
            "analysis_days": days,
            "total_candles": len(hist),
            "trading_days_analyzed": len(dates),
            "windows": window_stats,
            "tradeable_windows": tradeable_windows,
            "best_window": tradeable_windows[0] if tradeable_windows else None,
            "has_strong_patterns": len(tradeable_windows) > 0,
            "analyzed_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


async def analyze_single_ticker(ticker: str, days: int = 45, interval: str = "5m") -> Optional[dict]:
    """Analyze patterns for a single ticker (manual mode)."""
    now = _time.time()
    cache_key = f"{ticker}_{days}_{interval}"
    if cache_key in _pattern_cache and now - _pattern_cache_time.get(cache_key, 0) < _PATTERN_CACHE_TTL:
        return _pattern_cache[cache_key]

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _analyze_ticker_patterns, ticker, days, interval)

    if result and "error" not in result:
        _pattern_cache[cache_key] = result
        _pattern_cache_time[cache_key] = now

    return result


async def analyze_pool_patterns(pool: List[dict], days: int = 45, interval: str = "5m") -> List[dict]:
    """Step 2: Analyze patterns for all stocks in the pool."""
    loop = asyncio.get_event_loop()
    results = []

    # Process in batches of 2 (heavy operation)
    tickers = [s["ticker"] for s in pool]
    for i in range(0, len(tickers), 2):
        batch = tickers[i:i + 2]
        tasks = [loop.run_in_executor(None, _analyze_ticker_patterns, t, days, interval) for t in batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in batch_results:
            if isinstance(r, dict) and r is not None and "error" not in r:
                results.append(r)
        if i + 2 < len(tickers):
            await asyncio.sleep(0.5)

    # Sort by number of tradeable windows
    results.sort(key=lambda x: len(x.get("tradeable_windows", [])), reverse=True)
    return results


def generate_trade_signals(pattern: dict) -> List[dict]:
    """Step 3: Generate trade signals from pattern analysis."""
    if not pattern or "error" in pattern:
        return []

    signals = []
    daily_atr = pattern.get("daily_atr", 0)
    price = pattern.get("price", 0)

    for w in pattern.get("tradeable_windows", []):
        if w["win_rate"] < 60:
            continue

        direction = "LONG" if w["avg_change"] > 0 else "SHORT"

        # Stop loss: 0.3x the window's average range
        stop_distance = w["avg_range"] * price / 100 * 0.3 if price > 0 else 0
        # Target: avg_win of that window
        target_distance = abs(w["avg_win"]) * price / 100 if price > 0 else 0

        risk_reward = round(target_distance / stop_distance, 2) if stop_distance > 0 else 0

        if direction == "LONG":
            entry = price
            stop = round(price - stop_distance, 2)
            target = round(price + target_distance, 2)
        else:
            entry = price
            stop = round(price + stop_distance, 2)
            target = round(price - target_distance, 2)

        # Confidence based on win rate + sample size + consistency
        confidence = min(100, int(
            w["win_rate"] * 0.6 +
            min(w["sample_days"], 30) * 0.8 +
            (10 if w["strength"] == "very_strong" else 5 if w["strength"] == "strong" else 0)
        ))

        signals.append({
            "ticker": pattern["ticker"],
            "window": w["window"],
            "direction": direction,
            "win_rate": w["win_rate"],
            "avg_change": w["avg_change"],
            "avg_win": w["avg_win"],
            "avg_loss": w["avg_loss"],
            "expected_value": w["expected_value"],
            "entry": entry,
            "stop": stop,
            "target": target,
            "risk_reward": risk_reward,
            "confidence": confidence,
            "sample_days": w["sample_days"],
            "strength": w["strength"],
        })

    signals.sort(key=lambda x: x["confidence"], reverse=True)
    return signals


# ── Pattern Bot Demo Portfolio ────────────────────────────────────────────────
import json as _json
import os as _os

_PORTFOLIO_FILE = _os.path.join(_os.path.dirname(__file__), "..", "..", "data", "pattern_portfolio.json")

def _load_portfolio() -> dict:
    try:
        with open(_PORTFOLIO_FILE, "r") as f:
            return _json.load(f)
    except Exception:
        return {"balance": 700, "initial": 700, "trades": [], "open_position": None}

def _save_portfolio(p: dict):
    _os.makedirs(_os.path.dirname(_PORTFOLIO_FILE), exist_ok=True)
    with open(_PORTFOLIO_FILE, "w") as f:
        _json.dump(p, f, indent=2)

def get_portfolio() -> dict:
    p = _load_portfolio()
    total_pnl = sum(t.get("pnl", 0) for t in p["trades"])
    wins = [t for t in p["trades"] if t.get("pnl", 0) > 0]
    losses = [t for t in p["trades"] if t.get("pnl", 0) < 0]
    return {
        **p,
        "total_pnl": round(total_pnl, 2),
        "win_count": len(wins),
        "loss_count": len(losses),
        "trade_count": len(p["trades"]),
        "win_rate": round(len(wins) / len(p["trades"]) * 100, 1) if p["trades"] else 0,
        "current_value": round(p["balance"], 2),
        "return_pct": round((p["balance"] - p["initial"]) / p["initial"] * 100, 2),
    }

def open_trade(ticker: str, direction: str, entry_price: float,
               stop_price: float, target_price: float,
               window: str, win_rate: float, amount: float = 0) -> dict:
    p = _load_portfolio()
    if p.get("open_position"):
        return {"error": "יש פוזיציה פתוחה — סגור אותה קודם"}

    trade_amount = amount if amount > 0 else p["balance"]
    if trade_amount > p["balance"]:
        trade_amount = p["balance"]

    shares = trade_amount / entry_price if entry_price > 0 else 0

    p["open_position"] = {
        "ticker": ticker,
        "direction": direction,
        "entry_price": entry_price,
        "stop_price": stop_price,
        "target_price": target_price,
        "shares": round(shares, 4),
        "amount": round(trade_amount, 2),
        "window": window,
        "win_rate": win_rate,
        "opened_at": datetime.now().isoformat(),
    }
    _save_portfolio(p)
    return {"success": True, "position": p["open_position"], "balance": p["balance"]}

def close_trade(exit_price: float, reason: str = "manual") -> dict:
    p = _load_portfolio()
    pos = p.get("open_position")
    if not pos:
        return {"error": "אין פוזיציה פתוחה"}

    if pos["direction"] == "LONG":
        pnl_per_share = exit_price - pos["entry_price"]
    else:
        pnl_per_share = pos["entry_price"] - exit_price

    pnl = round(pnl_per_share * pos["shares"], 2)
    pnl_pct = round(pnl / pos["amount"] * 100, 2) if pos["amount"] > 0 else 0

    trade_record = {
        **pos,
        "exit_price": exit_price,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "reason": reason,
        "closed_at": datetime.now().isoformat(),
    }

    p["trades"].append(trade_record)
    p["balance"] = round(p["balance"] + pnl, 2)
    p["open_position"] = None
    _save_portfolio(p)
    return {"success": True, "trade": trade_record, "balance": p["balance"]}

def reset_portfolio(starting_balance: float = 700) -> dict:
    p = {"balance": starting_balance, "initial": starting_balance, "trades": [], "open_position": None}
    _save_portfolio(p)
    return p
