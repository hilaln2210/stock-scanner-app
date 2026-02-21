import asyncio
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from typing import List, Optional
from datetime import datetime, timedelta

from app.database import get_db
from app.models import NewsEvent, Signal
from app.schemas import NewsEventResponse, SignalResponse, DashboardStats
from app.services.ingestion import IngestionService
from app.services.normalization import NormalizationService
from app.services.signal_engine import SignalEngine
from app.scrapers.price_monitor import PriceMonitor
from app.scrapers.ipo_tracker import IPOTracker
from app.scrapers.market_pulse import MarketPulseScraper, get_high_momentum_stocks
from app.scrapers.momentum_scanner import MomentumScanner
from app.scrapers.social_trending import SocialTrendingScanner
from app.scrapers.finviz_screener import FinvizScreener
from app.scrapers.fda_calendar import FDACalendarScraper
from app.scrapers.finviz_fundamentals import FinvizFundamentals
from app.scrapers.tech_catalyst import TechCatalystScraper
from app.services.catalyst_tracker import CatalystTrackerService
from app.services.translator import translation_service
from app.services.live_prices import LivePriceService
from app.services.move_tracker import move_tracker
from app.services.briefing_service import BriefingService
from app.config import settings

router = APIRouter()
price_monitor = PriceMonitor()
ipo_tracker = IPOTracker()
live_price_service = LivePriceService()
market_pulse_scraper = MarketPulseScraper(
    email=settings.finviz_email,
    password=settings.finviz_password,
    cookie=settings.finviz_cookie
)
momentum_scanner = MomentumScanner()
social_trending_scanner = SocialTrendingScanner()
finviz_screener = FinvizScreener(
    email=settings.finviz_email,
    password=settings.finviz_password,
    cookie=settings.finviz_cookie
)
fda_calendar_scraper = FDACalendarScraper()
finviz_fundamentals = FinvizFundamentals(
    email=settings.finviz_email,
    password=settings.finviz_password,
    cookie=settings.finviz_cookie
)
tech_catalyst_scraper = TechCatalystScraper()
catalyst_tracker = CatalystTrackerService(
    fda_scraper=fda_calendar_scraper,
    finviz_fundamentals=finviz_fundamentals,
    tech_scraper=tech_catalyst_scraper,
)
briefing_service = BriefingService()

# Response-level cache for heavy endpoints
import time as _time
_response_cache: dict = {}
_response_cache_time: dict = {}
_RESPONSE_CACHE_TTL = 60  # seconds

# Lock to prevent concurrent heavy scans (created lazily)
_vwap_lock = None

def _get_vwap_lock():
    global _vwap_lock
    if _vwap_lock is None:
        import asyncio
        _vwap_lock = asyncio.Lock()
    return _vwap_lock


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@router.get("/signals")
async def get_signals(
    ticker: Optional[str] = Query(None),
    stance: Optional[str] = Query(None),
    min_score: Optional[float] = Query(0),
    limit: int = Query(100, le=500),
    lang: Optional[str] = Query('en'),
    db: AsyncSession = Depends(get_db),
):
    """Get signals with optional filtering and Hebrew translation"""
    query = select(Signal).order_by(Signal.event_time.desc())

    if ticker:
        query = query.where(Signal.ticker == ticker.upper())

    if stance:
        query = query.where(Signal.stance == stance)

    if min_score:
        query = query.where(Signal.score >= min_score)

    query = query.limit(limit)

    result = await db.execute(query)
    signals = result.scalars().all()

    # Translate to Hebrew if requested
    if lang == 'he':
        translated_signals = []
        for signal in signals:
            signal_dict = {
                'id': str(signal.id),
                'ticker': signal.ticker,
                'signal_type': signal.signal_type,
                'score': float(signal.score),
                'stance': signal.stance,
                'reason': signal.reason,
                'event_time': signal.event_time.isoformat() if signal.event_time else None,
                'created_at': signal.created_at.isoformat() if signal.created_at else None,
                'news_event_id': str(signal.news_event_id) if signal.news_event_id else None
            }
            translated = translation_service.translate_signal(signal_dict)
            translated_signals.append(translated)
        return translated_signals

    # Return as list of dicts for English too (to be consistent)
    return [
        {
            'id': str(s.id),
            'ticker': s.ticker,
            'signal_type': s.signal_type,
            'score': float(s.score),
            'stance': s.stance,
            'reason': s.reason,
            'event_time': s.event_time.isoformat() if s.event_time else None,
            'created_at': s.created_at.isoformat() if s.created_at else None,
            'news_event_id': str(s.news_event_id) if s.news_event_id else None
        }
        for s in signals
    ]


@router.get("/signals/{signal_id}", response_model=SignalResponse)
async def get_signal(signal_id: str, db: AsyncSession = Depends(get_db)):
    """Get specific signal by ID"""
    result = await db.execute(select(Signal).where(Signal.id == signal_id))
    signal = result.scalar_one_or_none()

    if not signal:
        return {"error": "Signal not found"}, 404

    return signal


@router.get("/news")
async def get_news(
    source: Optional[str] = Query(None),
    ticker: Optional[str] = Query(None),
    hours: int = Query(48, le=168),
    limit: int = Query(100, le=500),
    lang: Optional[str] = Query('en'),
    db: AsyncSession = Depends(get_db),
):
    """Get news events with optional filtering and Hebrew translation"""
    cutoff = datetime.now() - timedelta(hours=hours)
    query = select(NewsEvent).where(NewsEvent.published_at >= cutoff).order_by(
        NewsEvent.published_at.desc()
    )

    if source:
        query = query.where(NewsEvent.source == source)

    if ticker:
        query = query.where(NewsEvent.tickers.like(f"%{ticker.upper()}%"))

    query = query.limit(limit)

    result = await db.execute(query)
    news = result.scalars().all()

    # Convert to dicts
    news_list = [
        {
            'id': str(n.id),
            'source': n.source,
            'title': n.title,
            'url': n.url,
            'published_at': n.published_at.isoformat() if n.published_at else None,
            'summary': n.summary,
            'tickers': n.tickers,
            'sentiment_score': float(n.sentiment_score) if n.sentiment_score else 0.0,
            'created_at': n.created_at.isoformat() if n.created_at else None
        }
        for n in news
    ]

    # Translate to Hebrew if requested
    if lang == 'he':
        translated_news = await translation_service.translate_news(news_list, 'he')
        return translated_news

    # Return as list of dicts for English too
    return news_list


@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics"""
    # Count signals
    total_signals_result = await db.execute(select(func.count(Signal.id)))
    total_signals = total_signals_result.scalar()

    # Count news (last 48 hours)
    cutoff = datetime.now() - timedelta(hours=48)
    total_news_result = await db.execute(
        select(func.count(NewsEvent.id)).where(NewsEvent.published_at >= cutoff)
    )
    total_news = total_news_result.scalar()

    # Average score
    avg_score_result = await db.execute(select(func.avg(Signal.score)))
    avg_score = avg_score_result.scalar() or 0

    # Stance counts
    bullish_result = await db.execute(
        select(func.count(Signal.id)).where(Signal.stance == "Bullish")
    )
    bullish_count = bullish_result.scalar()

    bearish_result = await db.execute(
        select(func.count(Signal.id)).where(Signal.stance == "Bearish")
    )
    bearish_count = bearish_result.scalar()

    # Top tickers by signal count
    top_tickers_result = await db.execute(
        select(Signal.ticker, func.count(Signal.id).label("count"), func.avg(Signal.score).label("avg_score"))
        .group_by(Signal.ticker)
        .order_by(desc("count"))
        .limit(10)
    )
    top_tickers = [
        {"ticker": row[0], "count": row[1], "avg_score": round(row[2], 2)}
        for row in top_tickers_result.all()
    ]

    return {
        "total_signals": total_signals,
        "total_news": total_news,
        "avg_score": round(avg_score, 2),
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "top_tickers": top_tickers,
    }


@router.get("/top-movers")
async def get_top_movers(limit: int = Query(10, le=50), lang: Optional[str] = Query('en')):
    """Get today's top gaining stocks with quality filters and Hebrew translation"""
    movers = await price_monitor.get_top_movers_today(limit)

    # Translate to Hebrew if requested
    if lang == 'he':
        translated_movers = [translation_service.translate_mover(mover) for mover in movers]
        return {"movers": translated_movers}

    return {"movers": movers}


@router.get("/price-spike/{ticker}")
async def check_price_spike(ticker: str, threshold: float = Query(0.05)):
    """Check if ticker has spiked by threshold% in last 5 minutes"""
    spike = await price_monitor.check_price_spike(ticker.upper(), threshold)
    return spike if spike else {"message": "No spike detected"}


@router.post("/scrape/trigger")
async def trigger_scrape(db: AsyncSession = Depends(get_db)):
    """Manually trigger a scrape (for testing)"""
    try:
        # Ingest
        ingestion = IngestionService()
        results = await ingestion.scrape_all_sources()

        # Normalize and save
        normalization = NormalizationService(db)
        saved_count = await normalization.normalize_and_save(results)

        # Generate signals
        signal_engine = SignalEngine(db)
        signals_count = await signal_engine.generate_signals()

        return {
            "status": "success",
            "scraped": len(results),
            "saved": saved_count,
            "signals_generated": signals_count,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


@router.get("/ipos/today")
async def get_todays_ipos(lang: Optional[str] = Query('en')):
    """Get today's IPOs with expected vs actual pricing and insights (with Hebrew translation)"""
    ipos = await ipo_tracker.get_todays_ipos()

    # Translate to Hebrew if requested
    if lang == 'he':
        translated_ipos = [translation_service.translate_ipo(ipo) for ipo in ipos]
        return {"ipos": translated_ipos, "count": len(translated_ipos)}

    return {"ipos": ipos, "count": len(ipos)}


@router.get("/momentum/market-pulse")
async def get_market_pulse(limit: int = Query(50, le=100), lang: Optional[str] = Query('en')):
    """
    Get high-momentum stocks from Finviz Elite Market Pulse
    Returns stocks with strong momentum indicators + real-time move data
    """
    try:
        stocks = await get_high_momentum_stocks(
            limit=limit,
            email=settings.finviz_email,
            password=settings.finviz_password,
            cookie=settings.finviz_cookie
        )

        # Enrich with live price/volume data
        enriched_stocks = await live_price_service.enrich_stocks_with_live_data(stocks)

        # Enrich with real-time move tracking (5m/15m/velocity/acceleration)
        tickers = [s['ticker'] for s in enriched_stocks if s.get('ticker')]
        move_data = await move_tracker.get_bulk_move_data(tickers)
        for stock in enriched_stocks:
            ticker = stock.get('ticker')
            if ticker and ticker in move_data:
                stock['move'] = move_data[ticker]

        # Translate to Hebrew if requested
        if lang == 'he':
            translated_stocks = await translation_service.translate_stocks(enriched_stocks, 'he')
            return {"stocks": translated_stocks, "count": len(translated_stocks)}

        return {"stocks": enriched_stocks, "count": len(enriched_stocks)}
    except Exception as e:
        print(f"Error fetching market pulse: {e}")
        return {"stocks": [], "count": 0, "error": str(e)}


@router.get("/momentum/move/{ticker}")
async def get_stock_move_data(ticker: str):
    """
    Get real-time move data for a specific ticker.
    Returns: 5m/15m changes, velocity, acceleration, move start detection.
    """
    data = await move_tracker.get_move_data(ticker.upper())
    return data


@router.get("/momentum/scanner")
async def scan_momentum(lang: Optional[str] = Query('en')):
    """
    Real-time momentum scanner - finds high-momentum trading opportunities
    Detects: 5%+ moves, 2x volume, technical breakouts, catalysts
    """
    try:
        opportunities = await momentum_scanner.scan_momentum_opportunities()

        # Enrich with live price/volume data
        enriched_opportunities = await live_price_service.enrich_stocks_with_live_data(opportunities)

        # Enrich with real-time move tracking
        tickers = [s['ticker'] for s in enriched_opportunities if s.get('ticker')]
        move_data = await move_tracker.get_bulk_move_data(tickers)
        for stock in enriched_opportunities:
            ticker = stock.get('ticker')
            if ticker and ticker in move_data:
                stock['move'] = move_data[ticker]

        # Translate to Hebrew if requested
        if lang == 'he':
            translated_opps = await translation_service.translate_stocks(enriched_opportunities, 'he')
            return {"opportunities": translated_opps, "count": len(translated_opps)}

        return {"opportunities": enriched_opportunities, "count": len(enriched_opportunities)}
    except Exception as e:
        print(f"Error scanning momentum: {e}")
        import traceback
        traceback.print_exc()
        return {"opportunities": [], "count": 0, "error": str(e)}


@router.get("/momentum/stock/{ticker}")
async def get_stock_momentum_details(ticker: str, lang: Optional[str] = Query('en')):
    """Get detailed momentum analysis for a specific stock"""
    try:
        details = await momentum_scanner.get_stock_momentum_details(ticker.upper())

        # Enrich with live data
        if details and details.get("ticker"):
            enriched = await live_price_service.enrich_stocks_with_live_data([details])
            details = enriched[0] if enriched else details

        # Translate to Hebrew if requested
        if lang == 'he':
            details = await translation_service.translate_stock(details, 'he')

        return details
    except Exception as e:
        print(f"Error getting momentum details for {ticker}: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


@router.get("/stock/{ticker}")
async def get_stock_live_data(ticker: str, lang: Optional[str] = Query('en')):
    """Get live data for any stock ticker"""
    try:
        # Get live price and volume data
        stock_data = await live_price_service.get_stock_data(ticker.upper())

        if stock_data.get('price', 0) == 0:
            return {"error": f"Could not find data for ticker {ticker.upper()}"}

        # Format as a stock object
        result = {
            "ticker": ticker.upper(),
            "live_data": stock_data,
            "title": f"{stock_data.get('company_name', ticker.upper())} - Live Market Data",
            "momentum_score": 50,  # Neutral score for direct lookups
            "price_change": stock_data.get('change_percent', 0),
            "published_at": stock_data.get('updated_at'),
            "url": f"https://finance.yahoo.com/quote/{ticker.upper()}"
        }

        # Translate to Hebrew if requested
        if lang == 'he':
            result = await translation_service.translate_stock(result, 'he')

        return result
    except Exception as e:
        print(f"Error getting live data for {ticker}: {e}")
        return {"error": str(e)}


@router.get("/trending/social")
async def get_trending_social(limit: int = Query(30, le=50), lang: Optional[str] = Query('en')):
    """
    Get most talked about stocks from social media
    Aggregates mentions from Reddit (r/wallstreetbets, r/stocks), StockTwits, and more
    Shows: mention count, sentiment, source breakdown, if stock is climbing
    """
    try:
        # Get trending stocks from social media
        trending_stocks = await social_trending_scanner.get_trending_stocks(limit=limit)

        # Enrich with live price/volume data to show if stocks are climbing
        enriched_trending = await live_price_service.enrich_stocks_with_live_data(trending_stocks)

        # Translate to Hebrew if requested
        if lang == 'he':
            translated_trending = await translation_service.translate_stocks(enriched_trending, 'he')
            return {"trending": translated_trending, "count": len(translated_trending)}

        return {"trending": enriched_trending, "count": len(enriched_trending)}
    except Exception as e:
        print(f"Error getting social trending stocks: {e}")
        import traceback
        traceback.print_exc()
        return {"trending": [], "count": 0, "error": str(e)}


@router.get("/screener/vwap-momentum")
async def get_vwap_momentum_stocks(lang: Optional[str] = Query('en')):
    """
    Professional VWAP Momentum Screener with response caching.
    Cached for 60s to prevent backend overload.
    """
    cache_key = f"vwap_{lang}"
    now = _time.time()

    # Return cached response if fresh
    if cache_key in _response_cache and (now - _response_cache_time.get(cache_key, 0)) < _RESPONSE_CACHE_TTL:
        return _response_cache[cache_key]

    # Use lock to prevent concurrent heavy scans
    lock = _get_vwap_lock()
    if lock.locked():
        # Another request is already running — return stale cache or empty
        if cache_key in _response_cache:
            return _response_cache[cache_key]
        return {"stocks": [], "count": 0, "loading": True}

    async with lock:
        # Double-check cache after acquiring lock
        now = _time.time()
        if cache_key in _response_cache and (now - _response_cache_time.get(cache_key, 0)) < _RESPONSE_CACHE_TTL:
            return _response_cache[cache_key]

        try:
            stocks = await asyncio.wait_for(
                finviz_screener.scan_momentum_stocks(include_drops=True),
                timeout=35
            )

            # Enrich with move tracking (also with timeout)
            tickers = [s['ticker'] for s in stocks if s.get('ticker')]
            if tickers:
                try:
                    move_data = await asyncio.wait_for(
                        move_tracker.get_bulk_move_data(tickers),
                        timeout=10
                    )
                    for stock in stocks:
                        ticker = stock.get('ticker')
                        if ticker and ticker in move_data:
                            stock['move'] = move_data[ticker]
                except asyncio.TimeoutError:
                    print("Move tracker timeout — skipping move data")

            # Translate to Hebrew if requested
            if lang == 'he':
                try:
                    stocks = await asyncio.wait_for(
                        translation_service.translate_stocks(stocks, 'he'),
                        timeout=15
                    )
                except asyncio.TimeoutError:
                    print("Translation timeout — returning untranslated")

            response = {"stocks": stocks, "count": len(stocks)}

            # Cache the response
            _response_cache[cache_key] = response
            _response_cache_time[cache_key] = _time.time()

            return response
        except asyncio.TimeoutError:
            print("VWAP screener OVERALL TIMEOUT (>35s)")
            if cache_key in _response_cache:
                return _response_cache[cache_key]
            return {"stocks": [], "count": 0, "error": "timeout"}
        except Exception as e:
            print(f"Error in VWAP momentum screener: {e}")
            import traceback
            traceback.print_exc()
            if cache_key in _response_cache:
                return _response_cache[cache_key]
            return {"stocks": [], "count": 0, "error": str(e)}


# ─── FDA Catalyst Endpoints ─────────────────────────────────────

_fda_lock = None
_tech_lock = None

def _get_fda_lock():
    global _fda_lock
    if _fda_lock is None:
        _fda_lock = asyncio.Lock()
    return _fda_lock

def _get_tech_lock():
    global _tech_lock
    if _tech_lock is None:
        _tech_lock = asyncio.Lock()
    return _tech_lock


@router.get("/catalyst/fda")
async def get_fda_catalysts(
    days_forward: int = Query(90, le=365),
    days_back: int = Query(30, le=180),
    catalyst_type: Optional[str] = Query(None),
    lang: Optional[str] = Query('en'),
):
    """
    FDA Catalyst Calendar — biotech stocks with upcoming FDA approvals.
    Returns enriched events with Finviz fundamentals + latest news.
    Cached for 5 minutes.
    """
    cache_key = f"fda_{lang}_{days_forward}_{days_back}_{catalyst_type}"
    now = _time.time()

    # Return cached response if fresh
    if cache_key in _response_cache and (now - _response_cache_time.get(cache_key, 0)) < _RESPONSE_CACHE_TTL * 5:
        return _response_cache[cache_key]

    lock = _get_fda_lock()
    if lock.locked():
        if cache_key in _response_cache:
            return _response_cache[cache_key]
        return {"events": [], "count": 0, "loading": True}

    async with lock:
        now = _time.time()
        if cache_key in _response_cache and (now - _response_cache_time.get(cache_key, 0)) < _RESPONSE_CACHE_TTL * 5:
            return _response_cache[cache_key]

        try:
            events = await asyncio.wait_for(
                catalyst_tracker.get_catalyst_events(
                    days_forward=days_forward,
                    days_back=days_back,
                    enriched=True
                ),
                timeout=60
            )

            # Filter by catalyst type if specified
            if catalyst_type:
                events = [e for e in events if e.get('catalyst_type') == catalyst_type]

            # Translate to Hebrew if requested
            if lang == 'he':
                try:
                    events = await asyncio.wait_for(
                        translation_service.translate_stocks(events, 'he'),
                        timeout=15
                    )
                except asyncio.TimeoutError:
                    print("FDA translation timeout")

            response = {
                "events": events,
                "count": len(events),
                "last_updated": datetime.now().isoformat(),
            }

            _response_cache[cache_key] = response
            _response_cache_time[cache_key] = _time.time()
            return response

        except asyncio.TimeoutError:
            print("FDA catalyst OVERALL TIMEOUT (>60s)")
            if cache_key in _response_cache:
                return _response_cache[cache_key]
            return {"events": [], "count": 0, "error": "timeout"}
        except Exception as e:
            print(f"Error in FDA catalysts: {e}")
            import traceback
            traceback.print_exc()
            if cache_key in _response_cache:
                return _response_cache[cache_key]
            return {"events": [], "count": 0, "error": str(e)}


@router.get("/catalyst/fda/{ticker}")
async def get_ticker_fda_catalysts(ticker: str, lang: Optional[str] = Query('en')):
    """Get FDA catalyst events for a specific ticker."""
    try:
        events = await catalyst_tracker.get_catalyst_events(enriched=True)
        ticker_events = [e for e in events if e.get('ticker', '').upper() == ticker.upper()]

        if lang == 'he' and ticker_events:
            try:
                ticker_events = await asyncio.wait_for(
                    translation_service.translate_stocks(ticker_events, 'he'),
                    timeout=10
                )
            except asyncio.TimeoutError:
                pass

        return {"events": ticker_events, "count": len(ticker_events), "ticker": ticker.upper()}
    except Exception as e:
        return {"events": [], "count": 0, "error": str(e)}


@router.get("/catalyst/fda-movers")
async def get_fda_movers(
    days_back: int = Query(30, le=90),
):
    """
    FDA Movers — tracks historical stock movements around FDA catalyst dates.
    Shows which stocks moved, how much, and why.
    Cached for 5 minutes.
    """
    cache_key = f"fda_movers_{days_back}"
    now = _time.time()

    if cache_key in _response_cache and (now - _response_cache_time.get(cache_key, 0)) < _RESPONSE_CACHE_TTL * 5:
        return _response_cache[cache_key]

    try:
        movers = await asyncio.wait_for(
            catalyst_tracker.get_fda_movers(days_back=days_back),
            timeout=60
        )

        result = {
            "movers": movers,
            "count": len(movers),
            "days_back": days_back,
        }

        _response_cache[cache_key] = result
        _response_cache_time[cache_key] = _time.time()
        return result
    except asyncio.TimeoutError:
        return {"movers": [], "count": 0, "error": "timeout"}
    except Exception as e:
        print(f"FDA movers error: {e}")
        return {"movers": [], "count": 0, "error": str(e)}


@router.get("/catalyst/biotech-movers-today")
async def get_biotech_movers_today():
    """
    Today's + Yesterday's Biotech Movers — healthcare stocks moving significantly.
    Cross-referenced with FDA calendar for catalyst-driven moves.
    Cached for 3 minutes.
    """
    cache_key = "biotech_movers_both"
    now = _time.time()

    if cache_key in _response_cache and (now - _response_cache_time.get(cache_key, 0)) < _RESPONSE_CACHE_TTL * 3:
        return _response_cache[cache_key]

    empty_section = {"movers": [], "count": 0, "session_date": ""}
    try:
        # Phase 1: Scan both sessions in parallel
        today_movers, yesterday_movers = await asyncio.wait_for(
            asyncio.gather(
                catalyst_tracker.get_todays_biotech_movers(),
                catalyst_tracker.get_yesterdays_biotech_movers(),
            ),
            timeout=55
        )

        current_session, prev_session, is_market_open, today_session_active = catalyst_tracker._get_trading_session_dates()

        # Phase 2: RSI enrichment for unique tickers (best-effort, won't block if slow)
        all_tickers = list(dict.fromkeys(
            [m['ticker'] for m in today_movers] + [m['ticker'] for m in yesterday_movers]
        ))
        try:
            rsi_map = await asyncio.wait_for(
                catalyst_tracker._fetch_rsi_batch(all_tickers, limit=15),
                timeout=40
            )
            for m in today_movers + yesterday_movers:
                if m['ticker'] in rsi_map:
                    m.update(rsi_map[m['ticker']])
        except (asyncio.TimeoutError, Exception) as rsi_err:
            print(f"RSI enrichment skipped: {rsi_err}")

        result = {
            "movers": today_movers,  # backward compat
            "count": len(today_movers),
            "today": {
                "movers": today_movers,
                "count": len(today_movers),
                "session_date": str(current_session) if current_session else "",
                "is_market_open": is_market_open,
                "session_active": today_session_active,
            },
            "yesterday": {
                "movers": yesterday_movers,
                "count": len(yesterday_movers),
                "session_date": str(prev_session),
            },
            "last_updated": datetime.now().isoformat(),
        }

        _response_cache[cache_key] = result
        _response_cache_time[cache_key] = _time.time()
        return result
    except asyncio.TimeoutError:
        if cache_key in _response_cache:
            return _response_cache[cache_key]
        return {"movers": [], "count": 0, "today": empty_section, "yesterday": empty_section, "error": "timeout"}
    except Exception as e:
        print(f"Biotech movers today error: {e}")
        import traceback
        traceback.print_exc()
        if cache_key in _response_cache:
            return _response_cache[cache_key]
        return {"movers": [], "count": 0, "today": empty_section, "yesterday": empty_section, "error": str(e)}


@router.get("/catalyst/tech")
async def get_tech_catalysts(
    days_forward: int = Query(90, le=365),
    lang: Optional[str] = Query('en'),
):
    """
    Tech Catalyst Calendar — tech stocks with upcoming earnings, product launches.
    Cached for 5 minutes.
    """
    cache_key = f"tech_{lang}_{days_forward}"
    now = _time.time()

    if cache_key in _response_cache and (now - _response_cache_time.get(cache_key, 0)) < _RESPONSE_CACHE_TTL * 5:
        return _response_cache[cache_key]

    lock = _get_tech_lock()
    if lock.locked():
        if cache_key in _response_cache:
            return _response_cache[cache_key]
        return {"events": [], "count": 0, "loading": True}

    async with lock:
        now = _time.time()
        if cache_key in _response_cache and (now - _response_cache_time.get(cache_key, 0)) < _RESPONSE_CACHE_TTL * 5:
            return _response_cache[cache_key]

        try:
            events = await asyncio.wait_for(
                catalyst_tracker.get_tech_catalyst_events(days_forward=days_forward, enriched=True),
                timeout=130
            )

            if lang == 'he':
                try:
                    events = await asyncio.wait_for(
                        translation_service.translate_stocks(events, 'he'),
                        timeout=15
                    )
                except asyncio.TimeoutError:
                    pass

            response = {
                "events": events,
                "count": len(events),
                "last_updated": datetime.now().isoformat(),
            }

            _response_cache[cache_key] = response
            _response_cache_time[cache_key] = _time.time()
            return response

        except asyncio.TimeoutError:
            print("Tech catalyst OVERALL TIMEOUT (>75s)")
            if cache_key in _response_cache:
                return _response_cache[cache_key]
            return {"events": [], "count": 0, "error": "timeout"}
        except Exception as e:
            print(f"Error in tech catalysts: {e}")
            import traceback
            traceback.print_exc()
            if cache_key in _response_cache:
                return _response_cache[cache_key]
            return {"events": [], "count": 0, "error": str(e)}


# ── Daily Briefing ────────────────────────────────────────────────────────────

_BRIEFING_CACHE_TTL = 3 * 60 * 60   # 3 hours — morning briefing, rarely changes
_briefing_lock = asyncio.Lock()

@router.get("/briefing/daily")
async def get_daily_briefing():
    """
    Daily morning briefing: top 3-5 stocks with earnings beat ≥15% + RSI 45-65.
    Includes market status (SPY/QQQ) and today's catalyst events.
    Cached for 3 hours.
    """
    cache_key = "briefing_daily"
    now = _time.time()

    if cache_key in _response_cache and (now - _response_cache_time.get(cache_key, 0)) < _BRIEFING_CACHE_TTL:
        return _response_cache[cache_key]

    if _briefing_lock.locked():
        if cache_key in _response_cache:
            return _response_cache[cache_key]
        return {"stocks": [], "loading": True, "market_status": {}, "error": "scan in progress"}

    async with _briefing_lock:
        now = _time.time()
        if cache_key in _response_cache and (now - _response_cache_time.get(cache_key, 0)) < _BRIEFING_CACHE_TTL:
            return _response_cache[cache_key]

        try:
            result = await asyncio.wait_for(
                briefing_service.get_daily_briefing(
                    min_surprise_pct=15.0,
                    rsi_min=45.0,
                    rsi_max=65.0,
                    top_n=5,
                ),
                timeout=90
            )

            # Add today's FDA events
            try:
                fda_events = await asyncio.wait_for(
                    catalyst_tracker.get_catalyst_events(days_forward=1, days_back=0, enriched=False),
                    timeout=10
                )
                result['today_events'] = [
                    {
                        'ticker': e.get('ticker'),
                        'company': e.get('company'),
                        'catalyst_type': e.get('catalyst_type'),
                        'drug_name': e.get('drug_name', ''),
                        'days_until': e.get('days_until', 0),
                    }
                    for e in fda_events if e.get('days_until', 999) <= 1
                ]
            except Exception:
                result['today_events'] = []

            _response_cache[cache_key] = result
            _response_cache_time[cache_key] = _time.time()
            return result

        except asyncio.TimeoutError:
            print("Daily briefing TIMEOUT (>90s)")
            if cache_key in _response_cache:
                return _response_cache[cache_key]
            return {"stocks": [], "error": "timeout", "market_status": {}, "today_events": []}
        except Exception as e:
            print(f"Error in daily briefing: {e}")
            import traceback
            traceback.print_exc()
            if cache_key in _response_cache:
                return _response_cache[cache_key]
            return {"stocks": [], "error": str(e), "market_status": {}, "today_events": []}
