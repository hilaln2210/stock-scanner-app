from typing import List
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import NewsEvent
from app.schemas import NewsEventCreate
from app.scrapers import ScraperResult


class NormalizationService:
    """Handles normalization and deduplication of news events"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def normalize_and_save(self, scraper_results: List[ScraperResult]) -> int:
        """
        Normalize scraper results and save to database
        Returns: number of new events saved
        """
        saved_count = 0

        for result in scraper_results:
            # Check if already exists (by URL)
            existing = await self.db.execute(
                select(NewsEvent).where(NewsEvent.url == result.url)
            )
            if existing.scalar_one_or_none():
                continue  # Skip duplicate

            # Calculate basic sentiment
            sentiment = self._calculate_basic_sentiment(result.title)

            # Create news event
            news_event = NewsEvent(
                source=result.source,
                title=result.title,
                url=result.url,
                published_at=result.published_at,
                summary=result.summary,
                tickers=",".join(result.tickers) if result.tickers else "",
                sentiment_score=sentiment,
            )

            self.db.add(news_event)
            saved_count += 1

        await self.db.commit()
        return saved_count

    def _calculate_basic_sentiment(self, text: str) -> float:
        """
        Basic keyword-based sentiment analysis
        Returns: score between -1 (bearish) and 1 (bullish)
        """
        text_lower = text.lower()

        bullish_keywords = [
            "approval", "beat", "surge", "jump", "rally", "upgrade",
            "breakthrough", "profit", "growth", "exceeds", "strong",
            "positive", "gains", "rises", "soar", "bullish"
        ]

        bearish_keywords = [
            "decline", "fall", "drop", "miss", "downgrade", "lawsuit",
            "investigation", "loss", "weak", "cuts", "layoffs", "concern",
            "warning", "plunge", "crash", "bearish", "reject"
        ]

        bullish_count = sum(1 for word in bullish_keywords if word in text_lower)
        bearish_count = sum(1 for word in bearish_keywords if word in text_lower)

        total = bullish_count + bearish_count
        if total == 0:
            return 0.0

        score = (bullish_count - bearish_count) / total
        return max(-1.0, min(1.0, score))
