"""
Real-Time Move Tracker — Professional Trading Engine

Dual-timeframe logic:
1. Context Move  — daily change since open (background context)
2. Active Move   — 5m/15m price windows (actionable signal)
3. Move Start    — detects when a move actually began
4. Velocity      — %change / time window (not average)
5. Acceleration  — is velocity increasing or decreasing?

Every metric answers: "Where is something starting to happen NOW?"
"""
import yfinance as yf
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict
import math


class MoveTracker:
    """
    Tracks real-time price movement with short-term windows.
    Uses yfinance 1-minute intraday data for actual price history.
    """

    def __init__(self):
        # Cache intraday data per ticker (refreshed every 30s)
        self._intraday_cache: Dict[str, Dict] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        self._CACHE_TTL = 30  # seconds

    async def get_move_data(self, ticker: str) -> Dict:
        """
        Get complete move analysis for a ticker.
        Returns dual-timeframe data ready for frontend.
        """
        try:
            intraday = await self._get_intraday(ticker)
            if not intraday or not intraday.get('prices'):
                return self._empty_move_data(ticker)

            prices = intraday['prices']       # list of {time, price, volume}
            daily_info = intraday['daily']     # {open, prev_close, high, low, volume, avg_volume}

            now_price = prices[-1]['price'] if prices else 0
            if now_price == 0:
                return self._empty_move_data(ticker)

            # 1) Context Move — since open
            open_price = daily_info.get('open', now_price)
            daily_change = ((now_price - open_price) / open_price * 100) if open_price > 0 else 0

            # 2) Active Move — 5m and 15m windows
            change_5m = self._calc_window_change(prices, 5)
            change_15m = self._calc_window_change(prices, 15)

            # 3) Move Start Detection
            move_info = self._detect_move_start(prices, daily_info)

            # 4) Velocity — based on the active move window
            velocity_5m = change_5m / 5 if change_5m != 0 else 0       # %/min over 5m
            velocity_15m = change_15m / 15 if change_15m != 0 else 0   # %/min over 15m

            # 5) Acceleration — is velocity increasing?
            acceleration = self._calc_acceleration(prices)

            # 6) Relative Volume
            current_vol = daily_info.get('volume', 0)
            avg_vol = daily_info.get('avg_volume', 1)
            rel_volume = round(current_vol / avg_vol, 1) if avg_vol > 0 else 0

            # 7) High of Day context
            hod = daily_info.get('high', now_price)
            distance_from_hod = ((now_price - hod) / hod * 100) if hod > 0 else 0

            return {
                'ticker': ticker,
                'price': round(now_price, 2),
                'company_name': daily_info.get('company_name', ticker),
                'sector': daily_info.get('sector', ''),

                # Context Move (daily)
                'daily_change': round(daily_change, 2),
                'open_price': round(open_price, 2),

                # Active Move (short-term windows)
                'change_5m': round(change_5m, 2),
                'change_15m': round(change_15m, 2),

                # Move start detection
                'move_started_ago_min': move_info['started_ago_min'],
                'move_trigger': move_info['trigger'],
                'move_change_since_start': round(move_info['change_since_start'], 2),

                # Velocity & Acceleration
                'velocity_5m': round(velocity_5m, 3),   # %/min
                'velocity_15m': round(velocity_15m, 3),  # %/min
                'acceleration': acceleration,            # 'increasing', 'decreasing', 'steady'

                # Volume
                'volume': current_vol,
                'avg_volume': avg_vol,
                'rel_volume': rel_volume,

                # Structure
                'high_of_day': round(hod, 2),
                'distance_from_hod': round(distance_from_hod, 2),

                'updated_at': datetime.now().astimezone().isoformat(),
            }

        except Exception as e:
            print(f"MoveTracker error for {ticker}: {e}")
            return self._empty_move_data(ticker)

    async def get_bulk_move_data(self, tickers: List[str], max_concurrent: int = 8) -> List[Dict]:
        """Get move data for multiple tickers in parallel."""
        # Deduplicate
        unique_tickers = list(dict.fromkeys(tickers))[:20]

        # Parallel fetch with semaphore to limit concurrency
        sem = asyncio.Semaphore(max_concurrent)

        async def fetch_one(t):
            async with sem:
                return await self.get_move_data(t)

        results = await asyncio.gather(*[fetch_one(t) for t in unique_tickers], return_exceptions=True)

        move_data = {}
        for ticker, result in zip(unique_tickers, results):
            if isinstance(result, dict):
                move_data[ticker] = result
            else:
                move_data[ticker] = self._empty_move_data(ticker)

        return move_data

    # ─── Internal Methods ───────────────────────────────────

    async def _get_intraday(self, ticker: str) -> Optional[Dict]:
        """Fetch 1-minute intraday data via yfinance. Cached for 30s."""
        now = datetime.now()

        # Check cache
        if ticker in self._intraday_cache and ticker in self._cache_timestamps:
            elapsed = (now - self._cache_timestamps[ticker]).total_seconds()
            if elapsed < self._CACHE_TTL:
                return self._intraday_cache[ticker]

        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, self._fetch_intraday_sync, ticker)
            if data:
                self._intraday_cache[ticker] = data
                self._cache_timestamps[ticker] = now
            return data
        except Exception as e:
            print(f"MoveTracker intraday fetch error {ticker}: {e}")
            return None

    def _fetch_intraday_sync(self, ticker: str) -> Optional[Dict]:
        """Synchronous yfinance fetch for intraday 1m data."""
        try:
            stock = yf.Ticker(ticker)

            # Get 1-minute data for today (max 7 days for 1m interval)
            hist = stock.history(period='1d', interval='1m')

            if hist.empty:
                return None

            # Build price list
            prices = []
            for idx, row in hist.iterrows():
                prices.append({
                    'time': idx.to_pydatetime(),
                    'price': float(row['Close']),
                    'volume': int(row['Volume']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                })

            # Get daily info
            info = stock.info
            open_price = float(info.get('open') or info.get('regularMarketOpen') or (prices[0]['price'] if prices else 0))
            prev_close = float(info.get('previousClose') or info.get('regularMarketPreviousClose') or 0)

            daily = {
                'open': open_price,
                'prev_close': prev_close,
                'high': float(info.get('dayHigh') or info.get('regularMarketDayHigh') or max(p['high'] for p in prices) if prices else 0),
                'low': float(info.get('dayLow') or info.get('regularMarketDayLow') or min(p['low'] for p in prices) if prices else 0),
                'volume': int(info.get('volume') or info.get('regularMarketVolume') or 0),
                'avg_volume': int(info.get('averageVolume') or info.get('averageDailyVolume10Day') or 1),
                'company_name': info.get('longName') or info.get('shortName') or ticker,
                'sector': info.get('sector') or '',
                'market_cap': info.get('marketCap') or 0,
            }

            return {'prices': prices, 'daily': daily}

        except Exception as e:
            print(f"MoveTracker sync fetch error {ticker}: {e}")
            return None

    def _calc_window_change(self, prices: List[Dict], minutes: int) -> float:
        """Calculate price change over the last N minutes."""
        if len(prices) < 2:
            return 0.0

        now_price = prices[-1]['price']
        cutoff_time = prices[-1]['time'] - timedelta(minutes=minutes)

        # Find the price closest to N minutes ago
        ref_price = now_price
        for p in prices:
            if p['time'] >= cutoff_time:
                ref_price = p['price']
                break

        if ref_price == 0:
            return 0.0

        return ((now_price - ref_price) / ref_price) * 100

    def _detect_move_start(self, prices: List[Dict], daily_info: Dict) -> Dict:
        """
        Detect when the current move actually started.

        Triggers:
        - Break of High of Day
        - Volume spike (3x average minute volume)
        - Sudden direction change (reversal)
        - Price acceleration point
        """
        if len(prices) < 5:
            return {'started_ago_min': 0, 'trigger': 'insufficient_data', 'change_since_start': 0}

        now = prices[-1]['time']
        now_price = prices[-1]['price']

        # Calculate average minute volume
        total_vol = sum(p['volume'] for p in prices)
        avg_minute_vol = total_vol / len(prices) if prices else 1

        # Walk backward to find the move start
        move_start_idx = len(prices) - 1
        move_trigger = 'momentum'
        running_high = 0

        # Track running high of day up to each point
        for i in range(len(prices)):
            if prices[i]['high'] > running_high:
                running_high = prices[i]['high']

        # Look for trigger events going backwards
        for i in range(len(prices) - 2, max(0, len(prices) - 60), -1):
            p = prices[i]
            p_next = prices[i + 1]

            # 1. Volume spike trigger (3x average)
            if p['volume'] > avg_minute_vol * 3 and avg_minute_vol > 0:
                # Check if price started moving after this volume spike
                price_after = prices[min(i + 3, len(prices) - 1)]['price']
                if abs(price_after - p['price']) / p['price'] * 100 > 0.5:
                    move_start_idx = i
                    move_trigger = 'volume_spike'
                    break

            # 2. Break of prior high (new HOD)
            prior_high = max(pp['high'] for pp in prices[:max(1, i)])
            if p_next['price'] > prior_high and i > 5:
                if abs(now_price - p_next['price']) / p_next['price'] * 100 > 0.3:
                    move_start_idx = i + 1
                    move_trigger = 'break_of_high'
                    break

            # 3. Direction reversal (price was going down, now going up)
            if i >= 3:
                prev_trend = prices[i]['price'] - prices[i - 3]['price']
                next_trend = prices[min(i + 3, len(prices) - 1)]['price'] - prices[i]['price']
                if prev_trend < 0 and next_trend > 0 and abs(next_trend) > abs(prev_trend) * 0.5:
                    move_start_idx = i
                    move_trigger = 'reversal'
                    break

        # Calculate time since move start
        move_start_time = prices[move_start_idx]['time']
        started_ago = (now - move_start_time).total_seconds() / 60
        move_start_price = prices[move_start_idx]['price']
        change_since_start = ((now_price - move_start_price) / move_start_price * 100) if move_start_price > 0 else 0

        return {
            'started_ago_min': int(started_ago),
            'trigger': move_trigger,
            'change_since_start': change_since_start,
        }

    def _calc_acceleration(self, prices: List[Dict]) -> str:
        """
        Calculate if velocity is increasing or decreasing.
        Compare velocity in the last 5min vs the 5min before that.
        """
        if len(prices) < 10:
            return 'steady'

        now_price = prices[-1]['price']

        # Last 5 minutes velocity
        five_min_ago_idx = max(0, len(prices) - 5)
        price_5m_ago = prices[five_min_ago_idx]['price']
        vel_recent = ((now_price - price_5m_ago) / price_5m_ago * 100) / 5 if price_5m_ago > 0 else 0

        # Previous 5 minutes velocity (5-10 min ago)
        ten_min_ago_idx = max(0, len(prices) - 10)
        price_10m_ago = prices[ten_min_ago_idx]['price']
        vel_prev = ((price_5m_ago - price_10m_ago) / price_10m_ago * 100) / 5 if price_10m_ago > 0 else 0

        # Compare
        if abs(vel_recent) < 0.001 and abs(vel_prev) < 0.001:
            return 'steady'

        if vel_recent > vel_prev + 0.01:
            return 'increasing'
        elif vel_recent < vel_prev - 0.01:
            return 'decreasing'
        else:
            return 'steady'

    def _empty_move_data(self, ticker: str) -> Dict:
        return {
            'ticker': ticker,
            'price': 0,
            'company_name': ticker,
            'sector': '',
            'daily_change': 0,
            'open_price': 0,
            'change_5m': 0,
            'change_15m': 0,
            'move_started_ago_min': 0,
            'move_trigger': 'none',
            'move_change_since_start': 0,
            'velocity_5m': 0,
            'velocity_15m': 0,
            'acceleration': 'steady',
            'volume': 0,
            'avg_volume': 0,
            'rel_volume': 0,
            'high_of_day': 0,
            'distance_from_hod': 0,
            'updated_at': datetime.now().astimezone().isoformat(),
        }


# Singleton
move_tracker = MoveTracker()
