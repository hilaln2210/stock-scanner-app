import feedparser
from datetime import datetime
from typing import List
import re
from app.scrapers import ScraperResult


class MarketWatchScraper:
    """Scrapes MarketWatch RSS feeds"""

    RSS_URLS = [
        "https://www.marketwatch.com/rss/topstories",
        "https://www.marketwatch.com/rss/realtimeheadlines",
    ]

    async def scrape(self) -> List[ScraperResult]:
        """Scrape news from MarketWatch RSS"""
        results = []

        for rss_url in self.RSS_URLS:
            try:
                feed = feedparser.parse(rss_url)

                for entry in feed.entries[:50]:
                    title = entry.get("title", "")
                    url = entry.get("link", "")
                    summary = entry.get("summary", "")

                    # Parse published date
                    published_struct = entry.get("published_parsed")
                    if published_struct:
                        published_at = datetime(*published_struct[:6])
                    else:
                        published_at = datetime.now()

                    # Extract tickers
                    tickers = self._extract_tickers(title + " " + summary)

                    results.append(
                        ScraperResult(
                            source="marketwatch",
                            title=title,
                            url=url,
                            published_at=published_at,
                            summary=summary[:500],
                            tickers=tickers,
                        )
                    )

            except Exception as e:
                print(f"Error scraping MarketWatch RSS {rss_url}: {e}")

        return results

    def _extract_tickers(self, text: str) -> List[str]:
        """Extract ticker symbols from text"""
        patterns = [
            r"\b([A-Z]{1,5})\s+stock",
            r"\(([A-Z]{1,5})\)",
            r"\b([A-Z]{2,5})\s+shares",
        ]

        tickers = set()
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            # Only keep if actually uppercase (avoid false positives)
            tickers.update([m for m in matches if m.isupper() and len(m) <= 5])

        return list(tickers)
