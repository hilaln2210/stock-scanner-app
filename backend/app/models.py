from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Index
from sqlalchemy.sql import func
from app.database import Base
import uuid


class NewsEvent(Base):
    __tablename__ = "news_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source = Column(String(50), nullable=False, index=True)
    title = Column(Text, nullable=False)
    url = Column(String(500), unique=True, nullable=False)
    published_at = Column(DateTime, nullable=False, index=True)
    summary = Column(Text)
    tickers = Column(String(500))  # Comma-separated tickers

    # Computed fields
    sentiment_score = Column(Float, default=0.0)  # -1 to 1

    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index('idx_source_published', 'source', 'published_at'),
        Index('idx_tickers', 'tickers'),
    )


class Signal(Base):
    __tablename__ = "signals"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    news_event_id = Column(String, nullable=False)

    ticker = Column(String(10), nullable=False, index=True)
    signal_type = Column(String(50), nullable=False)  # earnings, fda_approval, etc
    score = Column(Float, nullable=False, index=True)  # 0-100
    stance = Column(String(20), nullable=False)  # Bullish/Bearish/Watchlist
    reason = Column(Text, nullable=False)

    # Metadata
    sector = Column(String(50))
    event_time = Column(DateTime, nullable=False, index=True)

    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index('idx_ticker_score', 'ticker', 'score'),
        Index('idx_stance_score', 'stance', 'score'),
    )
