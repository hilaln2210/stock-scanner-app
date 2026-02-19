from typing import List, Dict
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import NewsEvent, Signal
from app.schemas import SignalCreate
import re


class SignalEngine:
    """Generates trading signals from news events"""

    # MASSIVELY EXPANDED Signal patterns
    SIGNAL_PATTERNS = {
        # Earnings
        "earnings_beat": {
            "keywords": ["beat", "exceeds expectations", "better than expected", "tops estimates", "surpasses forecast"],
            "base_score": 78,
            "stance": "Bullish",
        },
        "earnings_miss": {
            "keywords": ["miss", "falls short", "disappoints", "below expectations", "misses estimates"],
            "base_score": 72,
            "stance": "Bearish",
        },
        "earnings_call": {
            "keywords": ["earnings call", "earnings transcript", "q1 2026 earnings", "q4 2025 earnings", "quarterly results"],
            "base_score": 60,
            "stance": "Watchlist",
        },

        # FDA & Healthcare
        "fda_approval": {
            "keywords": ["fda approval", "fda approves", "approved by fda", "regulatory approval", "clearance from fda"],
            "base_score": 88,
            "stance": "Bullish",
        },
        "fda_rejection": {
            "keywords": ["fda reject", "fda declines", "fda denial", "fails to win approval"],
            "base_score": 82,
            "stance": "Bearish",
        },
        "clinical_trial": {
            "keywords": ["clinical trial", "phase 3", "trial results", "study shows", "positive data"],
            "base_score": 70,
            "stance": "Bullish",
        },

        # Analyst Activity
        "analyst_upgrade": {
            "keywords": ["upgrade", "raises target", "initiates coverage", "outperform", "overweight", "buy rating"],
            "base_score": 68,
            "stance": "Bullish",
        },
        "analyst_downgrade": {
            "keywords": ["downgrade", "lowers target", "cuts rating", "underperform", "underweight", "sell rating"],
            "base_score": 68,
            "stance": "Bearish",
        },
        "price_target_raised": {
            "keywords": ["raises price target", "lifts target", "increases pt", "price target to"],
            "base_score": 65,
            "stance": "Bullish",
        },

        # Corporate Actions
        "merger_acquisition": {
            "keywords": ["merger", "acquisition", "acquire", "takeover", "buyout", "deal to buy"],
            "base_score": 75,
            "stance": "Watchlist",
        },
        "stock_split": {
            "keywords": ["stock split", "splits shares", "announces split", "forward split"],
            "base_score": 70,
            "stance": "Bullish",
        },
        "buyback": {
            "keywords": ["buyback", "share repurchase", "repurchase program", "buy back shares"],
            "base_score": 72,
            "stance": "Bullish",
        },
        "dividend_increase": {
            "keywords": ["dividend increase", "raises dividend", "boosts dividend", "ups payout"],
            "base_score": 68,
            "stance": "Bullish",
        },

        # Guidance
        "guidance_raise": {
            "keywords": ["raises guidance", "increases forecast", "ups outlook", "boosts guidance", "lifts forecast"],
            "base_score": 80,
            "stance": "Bullish",
        },
        "guidance_lower": {
            "keywords": ["lowers guidance", "cuts forecast", "reduces outlook", "slashes guidance", "lowers expectations"],
            "base_score": 78,
            "stance": "Bearish",
        },

        # Market Movement
        "surge_rally": {
            "keywords": ["surge", "soar", "rally", "jump", "skyrocket", "climbs", "pops", "gains"],
            "base_score": 65,
            "stance": "Bullish",
        },
        "plunge_selloff": {
            "keywords": ["plunge", "crash", "tumble", "plummet", "crater", "nosedive", "tank", "slump"],
            "base_score": 65,
            "stance": "Bearish",
        },
        "record_high": {
            "keywords": ["record high", "all-time high", "hits record", "new peak", "reaches milestone"],
            "base_score": 70,
            "stance": "Bullish",
        },

        # Negative Events
        "offering": {
            "keywords": ["public offering", "secondary offering", "share offering", "dilutive offering", "stock offering"],
            "base_score": 62,
            "stance": "Bearish",
        },
        "lawsuit": {
            "keywords": ["lawsuit", "sued", "litigation", "legal action", "class action", "settles lawsuit"],
            "base_score": 58,
            "stance": "Bearish",
        },
        "layoffs": {
            "keywords": ["layoffs", "job cuts", "workforce reduction", "eliminating positions", "cutting jobs"],
            "base_score": 60,
            "stance": "Bearish",
        },
        "investigation": {
            "keywords": ["investigation", "probe", "sec investigat", "doj investigat", "under scrutiny"],
            "base_score": 62,
            "stance": "Bearish",
        },

        # Positive Developments
        "partnership": {
            "keywords": ["partnership", "collaboration", "joint venture", "teams up with", "partners with"],
            "base_score": 65,
            "stance": "Bullish",
        },
        "product_launch": {
            "keywords": ["launches", "unveils", "introduces", "debuts", "rolls out", "new product"],
            "base_score": 68,
            "stance": "Bullish",
        },
        "contract_win": {
            "keywords": ["wins contract", "awarded contract", "secures deal", "lands contract", "contract award"],
            "base_score": 72,
            "stance": "Bullish",
        },
        "revenue_growth": {
            "keywords": ["revenue growth", "sales jump", "revenue surge", "strong sales", "revenue beat"],
            "base_score": 75,
            "stance": "Bullish",
        },

        # Tech Specific
        "ai_announcement": {
            "keywords": ["ai breakthrough", "artificial intelligence", "ai model", "generative ai", "machine learning"],
            "base_score": 70,
            "stance": "Bullish",
        },
        "data_breach": {
            "keywords": ["data breach", "hack", "cyber attack", "security breach", "ransomware"],
            "base_score": 65,
            "stance": "Bearish",
        },

        # Market Sentiment
        "bullish_outlook": {
            "keywords": ["bullish", "optimistic", "confident", "positive outlook", "upbeat", "strength ahead"],
            "base_score": 60,
            "stance": "Bullish",
        },
        "bearish_outlook": {
            "keywords": ["bearish", "pessimistic", "caution", "concerns", "weak outlook", "challenges ahead"],
            "base_score": 60,
            "stance": "Bearish",
        },
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_signals(self, lookback_minutes: int = 60) -> int:
        """
        Generate signals from recent news events
        Returns: number of signals generated
        """
        # Get recent news that don't have signals yet
        result = await self.db.execute(
            select(NewsEvent)
            .where(NewsEvent.tickers != "")
            .where(NewsEvent.tickers.isnot(None))
            .order_by(NewsEvent.published_at.desc())
            .limit(200)  # Increased from 100
        )
        news_events = result.scalars().all()

        signals_created = 0

        for event in news_events:
            # Check if signal already exists
            existing = await self.db.execute(
                select(Signal).where(Signal.news_event_id == event.id)
            )
            if existing.scalar_one_or_none():
                continue

            # Detect signal type
            signal_type, pattern = self._detect_signal_type(event.title, event.summary)
            if not signal_type:
                continue  # No recognizable signal

            # Parse tickers
            tickers = [t.strip() for t in event.tickers.split(",") if t.strip()]

            for ticker in tickers[:3]:  # Limit to 3 tickers per event
                # Calculate score
                score = self._calculate_score(event, pattern)

                # Generate reason
                reason = self._generate_reason(event, signal_type, pattern["stance"])

                # Create signal
                signal = Signal(
                    news_event_id=event.id,
                    ticker=ticker,
                    signal_type=signal_type,
                    score=score,
                    stance=pattern["stance"],
                    reason=reason,
                    event_time=event.published_at,
                )

                self.db.add(signal)
                signals_created += 1

        await self.db.commit()
        return signals_created

    def _detect_signal_type(self, title: str, summary: str) -> tuple:
        """
        Detect signal type from title and summary
        Returns: (signal_type, pattern_config) or (None, None)
        """
        text = f"{title} {summary}".lower()

        # Try to match patterns (prioritize more specific ones first)
        for signal_type, pattern in self.SIGNAL_PATTERNS.items():
            for keyword in pattern["keywords"]:
                if keyword in text:
                    return signal_type, pattern

        return None, None

    def _calculate_score(self, event: NewsEvent, pattern: Dict) -> float:
        """Calculate opportunity score based on event and pattern"""
        base_score = pattern["base_score"]

        # Adjust for sentiment alignment
        if pattern["stance"] == "Bullish" and event.sentiment_score > 0:
            base_score += event.sentiment_score * 12
        elif pattern["stance"] == "Bearish" and event.sentiment_score < 0:
            base_score += abs(event.sentiment_score) * 12

        # Adjust for recency (newer = higher score)
        age_minutes = (datetime.now() - event.published_at).total_seconds() / 60
        if age_minutes < 15:
            recency_boost = 12
        elif age_minutes < 60:
            recency_boost = 7
        elif age_minutes < 180:
            recency_boost = 3
        else:
            recency_boost = 0

        base_score += recency_boost

        # Adjust for source reliability
        source_boost = {
            "finviz": 6,
            "yahoo": 4,
            "marketwatch": 4,
        }.get(event.source, 0)

        base_score += source_boost

        return min(100, max(0, base_score))

    def _generate_reason(self, event: NewsEvent, signal_type: str, stance: str) -> str:
        """Generate human-readable reason for signal"""
        signal_descriptions = {
            "earnings_beat": "🎯 Beat earnings expectations - positive surprise",
            "earnings_miss": "📉 Missed earnings - disappointed investors",
            "earnings_call": "📊 Earnings announcement - monitor for guidance",
            "fda_approval": "🚀 FDA APPROVED - major catalyst!",
            "fda_rejection": "❌ FDA rejection - significant setback",
            "clinical_trial": "🧪 Clinical trial results released",
            "analyst_upgrade": "📈 Analyst upgrade - increased confidence",
            "analyst_downgrade": "📉 Analyst downgrade - lowered expectations",
            "price_target_raised": "🎯 Price target raised by analysts",
            "merger_acquisition": "🤝 M&A activity - transformational potential",
            "stock_split": "✂️ Stock split announced - bullish signal",
            "buyback": "💰 Share buyback - management confidence",
            "dividend_increase": "💵 Dividend increase - shareholder friendly",
            "guidance_raise": "📊 Guidance raised - strong outlook",
            "guidance_lower": "⚠️ Guidance lowered - caution ahead",
            "surge_rally": "🚀 Stock surging - momentum building",
            "plunge_selloff": "⚠️ Sharp decline - watch for stabilization",
            "record_high": "🏆 New record high - strong momentum",
            "offering": "💧 Dilutive offering - share count increase",
            "lawsuit": "⚖️ Legal issues - potential liability",
            "layoffs": "📉 Workforce reduction - cost cutting mode",
            "investigation": "🔍 Under investigation - regulatory risk",
            "partnership": "🤝 Strategic partnership announced",
            "product_launch": "🎉 New product launch",
            "contract_win": "✅ Major contract secured",
            "revenue_growth": "📈 Strong revenue growth reported",
            "ai_announcement": "🤖 AI development announced",
            "data_breach": "🔒 Security breach reported - reputation risk",
            "bullish_outlook": "🐂 Bullish outlook from management",
            "bearish_outlook": "🐻 Cautious outlook - headwinds ahead",
        }

        base_reason = signal_descriptions.get(signal_type, "⚡ Market-moving event detected")

        # Add context
        reason_parts = [base_reason]

        if event.sentiment_score > 0.4:
            reason_parts.append("Very strong positive sentiment.")
        elif event.sentiment_score > 0.2:
            reason_parts.append("Positive sentiment detected.")
        elif event.sentiment_score < -0.4:
            reason_parts.append("Very strong negative sentiment.")
        elif event.sentiment_score < -0.2:
            reason_parts.append("Negative sentiment detected.")

        age_minutes = (datetime.now() - event.published_at).total_seconds() / 60
        if age_minutes < 30:
            reason_parts.append("🔥 BREAKING - just announced!")
        elif age_minutes < 120:
            reason_parts.append("Recent development.")

        return " ".join(reason_parts)
