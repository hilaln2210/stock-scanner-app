import feedparser
from datetime import datetime
from typing import List
import re
from app.scrapers import ScraperResult


class YahooFinanceScraper:
    """Scrapes Yahoo Finance RSS feeds"""

    RSS_URLS = [
        "https://finance.yahoo.com/news/rssindex",
        "https://finance.yahoo.com/news/rss/topfreeapps",
    ]

    async def scrape(self) -> List[ScraperResult]:
        """Scrape news from Yahoo Finance RSS"""
        results = []

        for rss_url in self.RSS_URLS:
            try:
                feed = feedparser.parse(rss_url)

                for entry in feed.entries[:50]:  # Limit to 50 per feed
                    title = entry.get("title", "")
                    url = entry.get("link", "")
                    summary = entry.get("summary", "")

                    # Parse published date
                    published_struct = entry.get("published_parsed")
                    if published_struct:
                        published_at = datetime(*published_struct[:6])
                    else:
                        published_at = datetime.now()

                    # Extract tickers from title/summary
                    tickers = self._extract_tickers(title + " " + summary)

                    results.append(
                        ScraperResult(
                            source="yahoo",
                            title=title,
                            url=url,
                            published_at=published_at,
                            summary=summary[:500],  # Limit summary length
                            tickers=tickers,
                        )
                    )

            except Exception as e:
                print(f"Error scraping Yahoo RSS {rss_url}: {e}")

        return results

    def _extract_tickers(self, text: str) -> List[str]:
        """Extract ticker symbols from text"""
        # Look for patterns like (AAPL), (NASDAQ:TSLA), $AAPL
        patterns = [
            r"\(([A-Z]{1,5})\)",
            r"\(NASDAQ:([A-Z]{1,5})\)",
            r"\(NYSE:([A-Z]{1,5})\)",
            r"\$([A-Z]{1,5})\b",
        ]

        tickers = set()
        for pattern in patterns:
            matches = re.findall(pattern, text)
            tickers.update(matches)

        return list(tickers)
