from typing import List, Dict
from datetime import datetime


class ScraperResult:
    """Standard format for scraper results"""
    def __init__(
        self,
        source: str,
        title: str,
        url: str,
        published_at: datetime,
        summary: str = "",
        tickers: List[str] = None,
    ):
        self.source = source
        self.title = title
        self.url = url
        self.published_at = published_at
        self.summary = summary
        self.tickers = tickers or []

    def to_dict(self) -> Dict:
        return {
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at,
            "summary": self.summary,
            "tickers": ",".join(self.tickers) if self.tickers else "",
        }
