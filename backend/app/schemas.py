from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class NewsEventBase(BaseModel):
    source: str
    title: str
    url: str
    published_at: datetime
    summary: Optional[str] = None
    tickers: Optional[str] = None
    sentiment_score: float = 0.0


class NewsEventCreate(NewsEventBase):
    pass


class NewsEventResponse(NewsEventBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


class SignalBase(BaseModel):
    ticker: str
    signal_type: str
    score: float = Field(..., ge=0, le=100)
    stance: str  # Bullish/Bearish/Watchlist
    reason: str
    sector: Optional[str] = None
    event_time: datetime


class SignalCreate(SignalBase):
    news_event_id: str


class SignalResponse(SignalBase):
    id: str
    news_event_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class DashboardStats(BaseModel):
    total_signals: int
    total_news: int
    avg_score: float
    bullish_count: int
    bearish_count: int
    top_tickers: List[dict]
