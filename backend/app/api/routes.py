import asyncio
import re
import json as _json
from fastapi import APIRouter, Body, Depends, Query
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
from app.scrapers.finviz_screener import FinvizScreener
from app.scrapers.fda_calendar import FDACalendarScraper
from app.scrapers.finviz_fundamentals import FinvizFundamentals
from app.scrapers.tech_catalyst import TechCatalystScraper
from app.services.catalyst_tracker import CatalystTrackerService
from app.services.translator import translation_service
from app.services.live_prices import LivePriceService
from app.services.move_tracker import move_tracker
from app.services.technical_analysis import compute_technicals as _compute_ta
from app.services.briefing_service import BriefingService, fetch_single_ticker_briefing as _fetch_single_briefing
from app.services.technical_signals import TechnicalSignalsService
from app.services.daily_analysis import DailyAnalysisService
from app.services import portfolio_service
from app.config import settings
from app.services.ib_service import ib_service

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
tech_signals_service = TechnicalSignalsService()
daily_analysis_service = DailyAnalysisService()

# Response-level cache for heavy endpoints
import time as _time
_response_cache: dict = {}
_response_cache_time: dict = {}
_RESPONSE_CACHE_TTL = 120  # seconds
_MAX_CACHE_ENTRIES = 50

def _evict_expired_caches():
    """Remove expired entries from all caches to prevent unbounded memory growth."""
    now = _time.time()
    expired = [k for k, t in _response_cache_time.items() if now - t > _RESPONSE_CACHE_TTL * 10]
    for k in expired:
        _response_cache.pop(k, None)
        _response_cache_time.pop(k, None)

    if hasattr(_evict_expired_caches, '_sparkline'):
        sc, st = _evict_expired_caches._sparkline
        expired_sp = [k for k, t in st.items() if now - t > 600]
        for k in expired_sp:
            sc.pop(k, None)
            st.pop(k, None)

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


# Mid+Large cap tickers (S&P 500 + S&P 400 core) — used to filter news
_MID_LARGE_CAP_TICKERS = frozenset({
    # Mega/Large cap (S&P 500 core)
    'AAPL','MSFT','NVDA','AMZN','META','GOOGL','GOOG','TSLA','BRK','BRK.B','BRK.A',
    'LLY','JPM','V','UNH','XOM','MA','JNJ','PG','HD','AVGO','MRK','COST','ABBV',
    'CVX','CRM','BAC','NFLX','AMD','PEP','KO','TMO','WMT','ORCL','CSCO','ABT',
    'MCD','ACN','DHR','ADBE','TXN','NKE','QCOM','PM','AMGN','NEE','INTC','RTX',
    'UNP','MS','GS','SPGI','HON','INTU','LOW','COP','IBM','CAT','AXP','GE','UBER',
    'ELV','AMAT','MDT','ISRG','BKNG','REGN','VRTX','NOW','PANW','GILD','SYK','C',
    'BLK','MDLZ','PLD','MO','CI','TJX','BMY','ADI','LRCX','DE','MMC','CB','PNC',
    'SBUX','SO','DUK','ZTS','ICE','CME','KLAC','SNPS','MCO','HCA','EOG','SLB',
    'TGT','WFC','USB','ETN','ITW','FDX','EMR','APD','AON','EW','PSX','FCX',
    'PYPL','CRWD','SNOW','DDOG','MDB','NET','ZS','FTNT','OKTA','HUBS','TEAM',
    'MELI','SE','SHOP','SPOT','ABNB','DASH','RBLX','COIN','HOOD','PLTR','SMCI',
    'CDNS','MRVL','FICO','CARR','CTAS','RSG','WM','ADP','PAYX','FIS','FISV',
    'CCI','AMT','EQIX','PLD','DLR','O','SPG','PSA','AVB','EXR','WELL',
    # S&P 400 Mid-cap core
    'ROKU','ZM','DKNG','APP','CELH','SAIA','RBC','OLED','ELF','FIVE',
    'RH','WING','UFPI','GTLB','BILL','DOCN','PCTY','TOST','DUOL','FTDR',
    'CWST','CACC','CAVA','BROS','KRTX','AXON','ONTO','IBKR','HLNE','FN',
    'AAON','SFM','CSWI','NRDS','MMSI','LANC','STEP','MGNI','CNXC','XPOF',
    'RLI','VRRM','COKE','SITM','ALRM','STRA','PTVE','DFIN','HALO','PRAX',
    'MPC','VLO','PSX','COP','EOG','PXD','DVN','FANG','MRO','HES','OXY',
    'ARQT','ACAD','IONS','DAWN','APLS','IMVT','KROS','TGTX','INSM','NUVL',
    'RBRK','PLD','ROKU','INTC','MDB','SPOT','CELH','GE','SMCI','DG','CME',
    'GS','PYPL','MRNA','BNTX','REGN','BIIB','VRTX','GILD','ALNY','BMRN',
    'SRRK','KYMR','RCKT','RVMD','LEGN','IBRX','INCY','ILMN','FOLD','NBIX',
    'ZM','MU','AMAT','LRCX','KLAC','TSM','ASML','AVGO','TXN','ON','QRVO',
    'BA','CAT','DE','HON','MMM','UPS','LMT','NOC','GD','HII','SAIC','LDOS',
    'JPM','GS','MS','BAC','WFC','C','AXP','BLK','SCHW','ICE','SPGI','MCO',
    'PFE','JNJ','MRK','ABBV','LLY','UNH','AMGN','BMY','CI','CVS','HUM','MDT',
    'XOM','CVX','COP','EOG','PSX','VLO','MPC','SLB','HAL','BKR','OXY','DVN',
    'KO','PEP','WMT','COST','TGT','HD','LOW','NKE','SBUX','MCD','YUM','CMG',
    'AAPL','MSFT','GOOGL','META','AMZN','NVDA','AMD','TSLA','CRM','ORCL',
    'SNOW','DDOG','NET','MDB','ZS','PANW','CRWD','AFRM','COIN','RBLX','SHOP',
    'AMT','PLD','EQIX','DLR','O','SPG','PSA','EXR','CCI','WELL','AVB',
    'AEP','D','DUK','NEE','SO','EXC','SRE','PCG','FE','ES','ETR','XEL',
    'ADBE','CRM','NOW','INTU','ANSS','CDNS','SNPS','PAYC','PCTY','HUBS','WDAY',
})


@router.get("/news")
async def get_news(
    source: Optional[str] = Query(None),
    ticker: Optional[str] = Query(None),
    hours: int = Query(48, le=168),
    limit: int = Query(100, le=500),
    lang: Optional[str] = Query('en'),
    midcap_plus: bool = Query(False),
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

    query = query.limit(limit * 3 if midcap_plus else limit)

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

    # Filter to mid+large cap only
    if midcap_plus:
        def has_midcap_ticker(item):
            tickers_str = item.get('tickers') or ''
            tickers = [t.strip() for t in tickers_str.split(',') if t.strip()]
            return any(t in _MID_LARGE_CAP_TICKERS for t in tickers)
        news_list = [n for n in news_list if has_midcap_ticker(n)][:limit]

    # Translate to Hebrew if requested
    if lang == 'he':
        translated_news = await translation_service.translate_news(news_list, 'he')
        return translated_news

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

def _get_fda_lock():
    global _fda_lock
    if _fda_lock is None:
        _fda_lock = asyncio.Lock()
    return _fda_lock


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




# ── Daily Briefing ────────────────────────────────────────────────────────────

_BRIEFING_CACHE_TTL = 30 * 60   # 30 minutes
_BRIEFING_DISK_CACHE = "/tmp/briefing_disk_cache.json"
_briefing_lock = asyncio.Lock()


def _load_disk_cache():
    """Load briefing result from disk if it exists and is fresh enough."""
    import json as _json
    try:
        with open(_BRIEFING_DISK_CACHE, 'r') as f:
            data = _json.load(f)
        saved_at = data.get('_saved_at', 0)
        if _time.time() - saved_at < _BRIEFING_CACHE_TTL:
            return data, saved_at
    except Exception:
        pass
    return None, 0


def _save_disk_cache(result):
    """Persist briefing result to disk."""
    import json as _json
    try:
        data = dict(result)
        data['_saved_at'] = _time.time()
        with open(_BRIEFING_DISK_CACHE, 'w') as f:
            _json.dump(data, f)
    except Exception:
        pass


@router.get("/briefing/daily")
async def get_daily_briefing(
    force: bool = False,
    min_market_cap: int = Query(500_000_000, description="Minimum market cap in USD (default $500M)"),
):
    """
    Daily briefing: top stocks scored by earnings beat + RSI + momentum.
    Cached 30 min in memory + on disk (survives restarts).
    """
    cache_key = "briefing_daily"
    now = _time.time()

    # Force-refresh: expire TTL but keep old data available during new scan
    if force:
        _response_cache_time.pop(cache_key, None)

    # 1. In-memory cache hit
    if cache_key in _response_cache and (now - _response_cache_time.get(cache_key, 0)) < _BRIEFING_CACHE_TTL:
        return _response_cache[cache_key]

    # 2. Disk cache hit (survives restarts)
    disk_data, saved_at = _load_disk_cache()
    if disk_data and not force:
        _response_cache[cache_key] = disk_data
        _response_cache_time[cache_key] = saved_at
        return disk_data

    if _briefing_lock.locked():
        # Scan in progress — return old data if available, otherwise loading indicator
        if cache_key in _response_cache:
            return _response_cache[cache_key]
        if disk_data:
            return disk_data
        return {"stocks": [], "loading": True, "market_status": {}, "error": "scan in progress"}

    async with _briefing_lock:
        now = _time.time()
        if cache_key in _response_cache and (now - _response_cache_time.get(cache_key, 0)) < _BRIEFING_CACHE_TTL:
            return _response_cache[cache_key]

        try:
            result = await asyncio.wait_for(
                briefing_service.get_daily_briefing(
                    min_market_cap=min_market_cap,
                ),
                timeout=120
            )

            # Only cache if we got actual stocks (don't cache rate-limit failures)
            if not result.get('stocks'):
                if cache_key in _response_cache:
                    return _response_cache[cache_key]
                if disk_data:
                    return disk_data
                return {"stocks": [], "error": "no results", "market_status": {}, "today_events": []}

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
            _save_disk_cache(result)   # persist to disk
            return result

        except asyncio.TimeoutError:
            print("Daily briefing TIMEOUT (>120s)")
            if cache_key in _response_cache:
                return _response_cache[cache_key]
            if disk_data:
                return disk_data
            return {"stocks": [], "error": "timeout", "market_status": {}, "today_events": []}
        except Exception as e:
            print(f"Error in daily briefing: {e}")
            import traceback
            traceback.print_exc()
            if cache_key in _response_cache:
                return _response_cache[cache_key]
            if disk_data:
                return disk_data
            return {"stocks": [], "error": str(e), "market_status": {}, "today_events": []}


# ── Technical Signals (MACD + RSI + Bollinger Bands) ──────────────────────────

_TECH_SIGNALS_CACHE_TTL = 15 * 60   # 15 minutes
_tech_signals_lock = asyncio.Lock()


@router.get("/scanner/signals")
async def get_technical_signals():
    """
    Technical signals scanner: MACD (12/26/9), RSI (20-period), Bollinger Bands (20/2σ).
    Scans top-volume liquid US stocks from Finviz.
    Cached for 15 minutes.
    """
    cache_key = "tech_signals"
    now = _time.time()

    if cache_key in _response_cache and (now - _response_cache_time.get(cache_key, 0)) < _TECH_SIGNALS_CACHE_TTL:
        return _response_cache[cache_key]

    if _tech_signals_lock.locked():
        if cache_key in _response_cache:
            return _response_cache[cache_key]
        return {"stocks": [], "loading": True, "scanned": 0, "error": "scan in progress"}

    async with _tech_signals_lock:
        now = _time.time()
        if cache_key in _response_cache and (now - _response_cache_time.get(cache_key, 0)) < _TECH_SIGNALS_CACHE_TTL:
            return _response_cache[cache_key]

        try:
            result = await asyncio.wait_for(
                tech_signals_service.scan(),
                timeout=120
            )
            _response_cache[cache_key] = result
            _response_cache_time[cache_key] = _time.time()
            return result
        except asyncio.TimeoutError:
            print("Tech signals TIMEOUT (>120s)")
            if cache_key in _response_cache:
                return _response_cache[cache_key]
            return {"stocks": [], "error": "timeout", "scanned": 0, "count": 0}
        except Exception as e:
            print(f"Error in tech signals: {e}")
            if cache_key in _response_cache:
                return _response_cache[cache_key]
            return {"stocks": [], "error": str(e), "scanned": 0, "count": 0}


# ── Daily Analysis (MA + Deviation + Volume + MACD + RSI composite) ───────────

_DAILY_ANALYSIS_CACHE_TTL = 15 * 60   # 15 minutes
_daily_analysis_lock = asyncio.Lock()


@router.get("/analysis/daily")
async def get_daily_analysis():
    """
    Composite stock analysis: MA trend + deviation (anti-FOMO) + volume + MACD + RSI.
    Score 0-100 → STRONG BUY / BUY / HOLD / WAIT / SELL.
    Entry/stop/target levels derived from MA positions.
    Cached 15 minutes.
    """
    cache_key = "daily_analysis"
    now = _time.time()

    if cache_key in _response_cache and (now - _response_cache_time.get(cache_key, 0)) < _DAILY_ANALYSIS_CACHE_TTL:
        return _response_cache[cache_key]

    if _daily_analysis_lock.locked():
        if cache_key in _response_cache:
            return _response_cache[cache_key]
        return {"stocks": [], "loading": True, "scanned": 0, "error": "scan in progress"}

    async with _daily_analysis_lock:
        now = _time.time()
        if cache_key in _response_cache and (now - _response_cache_time.get(cache_key, 0)) < _DAILY_ANALYSIS_CACHE_TTL:
            return _response_cache[cache_key]

        try:
            result = await asyncio.wait_for(
                daily_analysis_service.analyze(),
                timeout=120
            )
            _response_cache[cache_key] = result
            _response_cache_time[cache_key] = _time.time()
            return result
        except asyncio.TimeoutError:
            print("Daily analysis TIMEOUT (>120s)")
            if cache_key in _response_cache:
                return _response_cache[cache_key]
            return {"stocks": [], "error": "timeout", "scanned": 0, "count": 0}
        except Exception as e:
            print(f"Error in daily analysis: {e}")
            if cache_key in _response_cache:
                return _response_cache[cache_key]
            return {"stocks": [], "error": str(e), "scanned": 0, "count": 0}


# ── Demo Portfolio ─────────────────────────────────────────────────────────────

@router.get("/portfolio/demo")
async def get_demo_portfolio():
    """Return demo portfolio with live prices and P&L.
    Fetches prices from Finviz Elite (real-time, pre/post market) first;
    falls back to yfinance for any tickers Finviz doesn't cover.
    """
    loop = asyncio.get_running_loop()

    # Try Finviz Elite prices first (one HTTP request, 10s hard cap)
    finviz_prices = {}
    try:
        raw = portfolio_service._load()
        tickers = [p["ticker"] for p in raw.get("positions", [])]
        if tickers:
            finviz_prices = await asyncio.wait_for(
                finviz_fundamentals.get_prices_batch(tickers),
                timeout=10.0
            )
            if finviz_prices:
                print(f"Finviz prices: {list(finviz_prices.keys())}")
    except Exception as e:
        print(f"Finviz price fetch failed, falling back to yfinance: {e}")

    result = await loop.run_in_executor(
        None,
        lambda: portfolio_service.get_portfolio_with_live_prices(
            override_prices=finviz_prices or None
        )
    )
    return result


@router.post("/portfolio/demo/buy-top3")
async def buy_top3():
    """Auto-buy top 3 stocks from current briefing cache (up to $500 each)."""
    briefing = _response_cache.get("briefing_daily") or {}
    stocks = briefing.get("stocks", [])
    if not stocks:
        return {"error": "No briefing data available — run briefing first"}
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: portfolio_service.buy_top3_from_briefing(stocks)
    )
    return result


@router.post("/portfolio/demo/buy")
async def buy_selected(body: dict = Body(...)):
    """Buy specific tickers selected by the user (up to $500 each)."""
    global _analysis_cache_time
    tickers = [t.upper() for t in body.get("tickers", []) if t]
    if not tickers:
        return {"error": "No tickers specified"}
    briefing = _response_cache.get("briefing_daily") or {}
    stocks = briefing.get("stocks", [])
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: portfolio_service.buy_selected_stocks(tickers, stocks)
    )
    _analysis_cache_time = 0  # invalidate advisor cache after portfolio change
    return result


@router.post("/portfolio/demo/sell/{ticker}")
async def sell_position(ticker: str):
    """Sell entire position in a ticker."""
    global _analysis_cache_time
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: portfolio_service.sell_position(ticker.upper())
    )
    _analysis_cache_time = 0  # invalidate advisor cache
    return result


@router.post("/portfolio/demo/add-cash")
async def add_cash(body: dict = Body(...)):
    """Add cash to the demo portfolio."""
    try:
        amount = float(body.get("amount", 0))
    except (TypeError, ValueError):
        return {"error": "סכום לא תקין"}
    return portfolio_service.add_cash(amount)


@router.post("/portfolio/demo/set-size")
async def set_portfolio_size(body: dict = Body(...)):
    """Update portfolio size and budget per position without resetting positions."""
    try:
        portfolio_size = float(body.get("portfolio_size", 3000))
        budget_per_position = float(body.get("budget_per_position", 700))
    except (TypeError, ValueError):
        return {"error": "ערכים לא תקינים"}
    return portfolio_service.set_portfolio_size(portfolio_size, budget_per_position)


@router.post("/portfolio/demo/reset")
async def reset_portfolio(body: dict = Body(default={})):
    """Reset demo portfolio. Optional: initial_cash, budget_per_position."""
    try:
        initial_cash = float(body.get("initial_cash", 3000))
        budget = float(body.get("budget_per_position", 700))
    except (TypeError, ValueError):
        initial_cash, budget = 3000.0, 700.0
    return portfolio_service.reset_portfolio(initial_cash=initial_cash, max_per_position=budget)


_analysis_cache: dict = {}
_analysis_cache_time: float = 0
_ANALYSIS_CACHE_TTL = 3 * 60  # 3 minutes


@router.get("/portfolio/demo/analysis")
async def get_portfolio_analysis():
    """AI portfolio advisor: missed opportunities + position commentary. Cached 3 min."""
    global _analysis_cache, _analysis_cache_time
    now = _time.time()
    if _analysis_cache and (now - _analysis_cache_time) < _ANALYSIS_CACHE_TTL:
        return _analysis_cache

    briefing = _response_cache.get("briefing_daily") or {}
    briefing_stocks = briefing.get("stocks", [])

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: portfolio_service.analyze_portfolio(briefing_stocks)
    )
    _analysis_cache = result
    _analysis_cache_time = now
    return result


@router.get("/briefing/ticker/{ticker}")
async def get_ticker_briefing(ticker: str):
    """On-demand briefing analysis for any single ticker (price, RSI, earnings, levels)."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, lambda: _fetch_single_briefing(ticker))
    return result


# ── Interactive Brokers ──────────────────────────────────────────────────────

@router.get("/ib/status")
async def ib_status():
    return ib_service.status()


@router.post("/ib/connect")
async def ib_connect(body: dict = Body(default={})):
    host = body.get("host", "127.0.0.1")
    port = int(body.get("port", 4002))
    client_id = int(body.get("client_id", 20))
    return await ib_service.connect(host=host, port=port, client_id=client_id)


@router.get("/ib/account")
async def ib_account():
    return await ib_service.get_account_summary()


@router.get("/ib/positions")
async def ib_positions():
    return await ib_service.get_positions()


@router.get("/ib/orders")
async def ib_orders():
    return await ib_service.get_open_orders()


@router.get("/ib/executions")
async def ib_executions(days: int = Query(7, le=90)):
    return await ib_service.get_executions(days=days)


@router.post("/ib/order")
async def ib_place_order(body: dict = Body(...)):
    ticker = body.get("ticker", "").strip().upper()
    action = body.get("action", "").strip().upper()
    qty = body.get("qty")
    order_type = body.get("order_type", "MKT").upper()
    limit_price = body.get("limit_price")
    stop_price = body.get("stop_price")
    tif = body.get("tif", "DAY").upper()

    if not ticker:
        return {"error": "ticker חסר"}
    if action not in ("BUY", "SELL"):
        return {"error": "action חייב להיות BUY או SELL"}
    if not qty or float(qty) <= 0:
        return {"error": "כמות חייבת להיות גדולה מ-0"}

    return await ib_service.place_order(
        ticker=ticker,
        action=action,
        quantity=float(qty),
        order_type=order_type,
        limit_price=float(limit_price) if limit_price else None,
        stop_price=float(stop_price) if stop_price else None,
        tif=tif,
    )


@router.delete("/ib/order/{order_id}")
async def ib_cancel_order(order_id: int):
    return await ib_service.cancel_order(order_id)


# ── Big-move alert scanner ──────────────────────────────────────────────────
import aiohttp as _aiohttp
from bs4 import BeautifulSoup as _BS4
import yfinance as _yf
from concurrent.futures import ThreadPoolExecutor as _TPE

_ALERT_CACHE: dict = {}
_ALERT_CACHE_TIME: float = 0.0
_ALERT_CACHE_TTL = 90  # seconds


def _fetch_alert_ticker_sync(ticker: str) -> Optional[dict]:
    """Fetch quick stats for one alert candidate using yfinance fast_info."""
    try:
        stk = _yf.Ticker(ticker)
        fi = stk.fast_info
        price = float(fi.last_price or 0)
        if price < 1.0:
            return None
        open_p = float(fi.open or 0)
        if open_p <= 0:
            return None
        pct = round((price - open_p) / open_p * 100, 2)
        if pct < 8.0:
            return None
        mcap = fi.market_cap or 0
        if mcap < 200_000_000:   # must be at least $200M market cap
            return None
        # Get company name & sector quickly
        company = ticker
        sector = ''
        try:
            with _TPE(max_workers=1) as ex:
                info = ex.submit(lambda: stk.info or {}).result(timeout=3)
            company = info.get('shortName') or info.get('longName') or ticker
            sector  = info.get('sector') or ''
        except Exception:
            pass
        mcap_b = mcap / 1e9 if mcap >= 1e9 else None
        mcap_m = mcap / 1e6 if mcap < 1e9 else None
        mcap_str = f"${mcap_b:.1f}B" if mcap_b else f"${mcap_m:.0f}M"
        return {
            'ticker':  ticker,
            'company': company,
            'sector':  sector,
            'price':   round(price, 2),
            'open':    round(open_p, 2),
            'pct':     pct,
            'mcap':    mcap,
            'mcap_str': mcap_str,
        }
    except Exception:
        return None


async def _scrape_alert_candidates() -> list[str]:
    """Use Finviz screener to get tickers up 10%+ today, small-cap and above."""
    url = (
        'https://finviz.com/screener.ashx?v=111'
        '&f=cap_smallover,ta_perf_d10o'   # small+ AND up 10%+ today
        '&o=-perf&r=1'
    )
    headers = {'User-Agent': 'Mozilla/5.0 (StockAlerts/1.0)'}
    tickers = []
    try:
        async with _aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers,
                                   timeout=_aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
        soup = _BS4(html, 'html.parser')
        # Primary selector: screener-link-primary (ticker links)
        for a in soup.select('a.screener-link-primary'):
            t = a.text.strip()
            if t and t.isupper() and 1 < len(t) <= 5:
                tickers.append(t)
        # Fallback: tab-link rows
        if not tickers:
            for row in soup.select('tr.styled-row-light, tr.styled-row-dark, tr[id^="row"]'):
                a = row.select_one('td a.tab-link')
                if a:
                    t = a.text.strip()
                    if t and t.isupper():
                        tickers.append(t)
    except Exception as e:
        print(f"Alerts: Finviz fetch failed: {e}")
    return list(dict.fromkeys(tickers))[:30]  # deduplicate, cap at 30


@router.get("/alerts/movers")
async def get_alert_movers():
    """
    Returns stocks up 10%+ today (small-cap and above) for push-notification display.
    Cached 90 seconds to avoid hammering Finviz/yfinance.
    """
    global _ALERT_CACHE, _ALERT_CACHE_TIME
    import time as _t
    now = _t.time()

    if _ALERT_CACHE and (now - _ALERT_CACHE_TIME) < _ALERT_CACHE_TTL:
        return _ALERT_CACHE

    # 1. Get candidate tickers from Finviz
    candidates = await _scrape_alert_candidates()

    # 2. Enrich with yfinance (parallel, max 5 at once, 8s timeout per ticker)
    loop = asyncio.get_running_loop()
    results = []
    if candidates:
        with _TPE(max_workers=5) as pool:
            futs = [loop.run_in_executor(pool, _fetch_alert_ticker_sync, t)
                    for t in candidates[:25]]
            done = await asyncio.gather(*futs, return_exceptions=True)
        results = [r for r in done if isinstance(r, dict) and r is not None]
        results.sort(key=lambda x: x['pct'], reverse=True)

    out = {
        'movers': results,
        'count': len(results),
        'scanned': len(candidates),
        'generated_at': datetime.now().isoformat(),
    }
    _ALERT_CACHE = out
    _ALERT_CACHE_TIME = now
    return out


# ── Live Prices (fast poll, pre/post market) ───────────────────────────────────

_LIVE_PRICES_CACHE: dict = {}
_LIVE_PRICES_CACHE_TIME: float = 0.0
_LIVE_PRICES_FETCHING: bool = False   # prevent concurrent heavy fetches


_SPARKLINE_CACHE: dict = {}
_SPARKLINE_CACHE_TIME: dict = {}
_evict_expired_caches._sparkline = (_SPARKLINE_CACHE, _SPARKLINE_CACHE_TIME)

@router.get("/screener/sparkline")
async def get_sparkline(ticker: str = Query(...)):
    """Intraday 5-min price points for sparkline chart."""
    import time as _t
    ticker = ticker.strip().upper()
    now = _t.time()
    if ticker in _SPARKLINE_CACHE and (now - _SPARKLINE_CACHE_TIME.get(ticker, 0)) < 120:
        return {'prices': _SPARKLINE_CACHE[ticker]}
    try:
        import yfinance as _yf
        loop = asyncio.get_running_loop()
        def _fetch():
            t = _yf.Ticker(ticker)
            h = t.history(period='1d', interval='5m', prepost=True, timeout=6)
            if h is not None and len(h) >= 2:
                return [round(float(p), 2) for p in h['Close'].dropna().tolist()]
            h = t.history(period='5d', interval='15m', prepost=True, timeout=6)
            if h is not None and len(h) > 0:
                return [round(float(p), 2) for p in h['Close'].dropna().tolist()[-50:]]
            return []
        prices = await asyncio.wait_for(loop.run_in_executor(None, _fetch), timeout=8)
        if prices:
            _SPARKLINE_CACHE[ticker] = prices
            _SPARKLINE_CACHE_TIME[ticker] = now
        return {'prices': prices}
    except Exception:
        return {'prices': _SPARKLINE_CACHE.get(ticker, [])}


@router.get("/screener/live-prices")
async def get_live_prices(tickers: str = Query(...)):
    """
    Real-time data from Finviz screener: price, change%, volume, market cap.
    All columns sync with what Finviz shows (including pre/post market on Elite).
    """
    global _LIVE_PRICES_CACHE, _LIVE_PRICES_CACHE_TIME, _LIVE_PRICES_FETCHING
    import time as _t

    ticker_list = [t.strip().upper() for t in tickers.split(',') if t.strip()][:30]
    if not ticker_list:
        return {}

    now = _t.time()
    cache_ttl = 12
    if now - _LIVE_PRICES_CACHE_TIME < cache_ttl and _LIVE_PRICES_CACHE:
        hit = {t: _LIVE_PRICES_CACHE[t] for t in ticker_list if t in _LIVE_PRICES_CACHE}
        if len(hit) >= len(ticker_list) * 0.5:
            return hit

    if _LIVE_PRICES_FETCHING:
        return {t: _LIVE_PRICES_CACHE[t] for t in ticker_list if t in _LIVE_PRICES_CACHE}

    _LIVE_PRICES_FETCHING = True
    try:
        fv_data = await finviz_fundamentals.get_prices_batch(ticker_list)
        results = {}
        for t in ticker_list:
            fv = fv_data.get(t)
            if fv and fv.get('price'):
                results[t] = {
                    'price': round(float(fv['price']), 4),
                    'change_pct': fv.get('change_pct', ''),
                    'volume': fv.get('volume', 0),
                    'volume_str': fv.get('volume_str', ''),
                    'market_cap_str': fv.get('market_cap_str', ''),
                }
            elif t in _FV_FUND_CACHE:
                fund = _FV_FUND_CACHE[t]
                p = _parse_fv_num(fund.get('price', ''))
                if p:
                    results[t] = {
                        'price': round(p, 4),
                        'change_pct': fund.get('change_pct', ''),
                        'volume': _parse_fv_num(fund.get('volume', '')) or 0,
                    }
        if results:
            _LIVE_PRICES_CACHE.update(results)
            _LIVE_PRICES_CACHE_TIME = _t.time()
        return {t: _LIVE_PRICES_CACHE[t] for t in ticker_list if t in _LIVE_PRICES_CACHE}
    except Exception as e:
        print(f"[live-prices] error: {e}")
        return {t: _LIVE_PRICES_CACHE[t] for t in ticker_list if t in _LIVE_PRICES_CACHE}
    finally:
        _LIVE_PRICES_FETCHING = False


# ── Finviz Fundamental Table Screener ─────────────────────────────────────────

_FV_TABLE_CACHE: dict = {}
_FV_TABLE_CACHE_TIME: float = 0.0
_FV_TABLE_CACHE_TTL: int = 25       # price/change: 25 s (frontend polls every 30 s)
_FV_FUND_CACHE: dict = {}           # {ticker: fund_data}
_FV_FUND_CACHE_TIME: float = 0.0
_FV_FUND_CACHE_TTL: int = 1800      # fundamentals: 30 min
_FV_NEWS_CACHE: dict = {}           # {ticker: [news_items]}
_FV_NEWS_CACHE_TIME: dict = {}      # {ticker: timestamp}
_FV_NEWS_CACHE_TTL: int = 600       # news: 10 min per ticker
_FV_INTRA_CACHE: dict = {}          # {ticker: {chg_5m, chg_30m, chg_4h}}
_FV_INTRA_CACHE_TIME: dict = {}     # {ticker: timestamp}
_FV_INTRA_CACHE_TTL: int = 60       # intraday: 60s to allow background task to complete for all stocks
_FV_SUMMARY_CACHE: dict = {}        # {ticker: summary_str}
_FV_SUMMARY_CACHE_TIME: dict = {}   # {ticker: timestamp}
_FV_SUMMARY_CACHE_TTL: int = 3600   # business description: 1 hour

_FV_TA_CACHE: dict = {}             # {ticker: tech analysis result}
_FV_TA_CACHE_TIME: dict = {}        # {ticker: timestamp}
_FV_TA_CACHE_TTL: int = 90          # technical analysis: 90s (background task takes ~40s for 50 stocks)

_FV_DEFAULT_FILTERS = (
    "cap_midover,sh_avgvol_o2000,sh_curvol_o300,sh_instown_o10,ta_rsi_nos50"
)


def _parse_fv_num(s) -> Optional[float]:
    """Parse Finviz number strings: '5.36B', '-155.90M', '25.09%' → float."""
    if s is None:
        return None
    s = str(s).strip().replace(',', '').replace('+', '')
    if s in ('', '-', 'N/A', '--'):
        return None
    for suf, mult in (('B', 1e9), ('M', 1e6), ('K', 1e3)):
        if s.upper().endswith(suf):
            try:
                return float(s[:-1]) * mult
            except Exception:
                return None
    try:
        return float(s.rstrip('%'))
    except Exception:
        return None


def _compute_ev(fund: dict) -> Optional[float]:
    """
    Derive Enterprise Value from Finviz data.
    Priority: direct 'enterprise_value' → EV/Sales × Sales → None.
    """
    ev = _parse_fv_num(fund.get('enterprise_value', ''))
    if ev:
        return ev
    ev_sales_r = _parse_fv_num(fund.get('ev_sales', ''))
    sales      = _parse_fv_num(fund.get('sales', ''))
    if ev_sales_r and sales and ev_sales_r > 0:
        return ev_sales_r * sales
    return None


def _stock_tags(fund: dict, price: float = 0) -> list:
    """
    Fundamentals layer tags:
      ✅ profitable  — Net Income > 0
      ❌ loss        — Net Income < 0
      ⚠️ high_debt   — EV/MC ≥ 1.2
      💰 cash_rich   — EV/MC ≤ 0.9
      🔥 high_growth — Sales Y/Y ≥ 50 AND Sales Q/Q ≥ 10
                        (fallback: Sales Q/Q ≥ 30 if Y/Y missing and Sales ≥ 50M)
      📉 high_short  — Short Float > 15%
    """
    tags: list[str] = []

    income = _parse_fv_num(fund.get('income', ''))
    if income is not None:
        tags.append('profitable' if income > 0 else 'loss')

    mc = _parse_fv_num(fund.get('market_cap', ''))
    ev = _compute_ev(fund)
    if ev and mc and mc > 0:
        ratio = ev / mc
        if ratio >= 1.2:
            tags.append('high_debt')
        elif ratio <= 0.9:
            tags.append('cash_rich')

    sales      = _parse_fv_num(fund.get('sales', ''))
    sales_qq   = _parse_fv_num(fund.get('sales_qq', ''))
    sales_yy   = _parse_fv_num(
        fund.get('sales_year', '') or fund.get('sales_yoy', '') or fund.get('sales_year_yoy', '')
    )

    high_growth = False
    if sales_yy is not None:
        # Primary rule: Sales Y/Y >= 50 AND Sales Q/Q >= 10
        if sales_yy >= 50 and (sales_qq is None or sales_qq >= 10):
            high_growth = True
    else:
        # Fallback when Y/Y missing: Sales Q/Q >= 30 and Sales >= 50M
        if sales_qq is not None and sales_qq >= 30 and sales is not None and sales >= 50_000_000:
            high_growth = True

    if high_growth:
        tags.append('high_growth')

    short = _parse_fv_num(fund.get('short_float', ''))
    if short and short > 15:
        tags.append('high_short')

    return tags


def _earnings_verdict(fund: dict) -> Optional[str]:
    """
    Determine last-quarter earnings verdict from available Finviz data.
    Priority: EPS Surprise % → EPS Q/Q proxy.
    Returns 'beat' | 'miss' | 'inline' | None.
    """
    # Direct EPS Surprise field (e.g. "12.50%")
    surpr_raw = fund.get('eps_surpr', '') or ''
    surpr = _parse_fv_num(surpr_raw)
    if surpr is not None:
        if surpr > 3:   return 'beat'
        if surpr < -3:  return 'miss'
        return 'inline'

    # Combined "EPS/Sales Surpr" like "90.83% 1.50%" — take first number
    combined = str(fund.get('eps_sales_surpr', '') or '').strip()
    if combined:
        first = combined.split()[0] if ' ' in combined else combined.split('%')[0] + '%'
        surpr2 = _parse_fv_num(first)
        if surpr2 is not None:
            if surpr2 > 3:   return 'beat'
            if surpr2 < -3:  return 'miss'
            return 'inline'

    # Fallback: EPS Q/Q as proxy (a big positive jump likely beat)
    eps_qq = _parse_fv_num(fund.get('eps_qq', ''))
    if eps_qq is not None:
        if eps_qq > 10:  return 'beat'
        if eps_qq < -10: return 'miss'

    return None


def _health_score(tags: list, ev_sales_ratio: Optional[float]) -> int:
    """
    Health Score (0–100):
      base 50
      +30 profitable
      -25 loss
      +20 cash_rich
      -20 high_debt
      +20 high_growth
      -10 if EV/Sales > 20
    """
    score = 50
    if 'profitable' in tags:
        score += 30
    if 'loss' in tags:
        score -= 25
    if 'cash_rich' in tags:
        score += 20
    if 'high_debt' in tags:
        score -= 20
    if 'high_growth' in tags:
        score += 20

    if ev_sales_ratio is not None and ev_sales_ratio > 20:
        score -= 10

    return max(0, min(100, score))


def _health_detail(tags: list, ev_sales_ratio: Optional[float], short_pct: Optional[float], rsi_val: Optional[float]) -> list:
    """Readable breakdown of what raises/lowers the Health and Risk scores."""
    items = []
    items.append({'text': 'בסיס', 'pts': 50})
    if 'profitable' in tags:
        items.append({'text': '✅ רווחית (Net Income > 0)', 'pts': 30})
    if 'loss' in tags:
        items.append({'text': '❌ הפסדית', 'pts': -25})
    if 'cash_rich' in tags:
        items.append({'text': '💰 EV/MC ≤ 0.9 (מזומן גבוה)', 'pts': 20})
    if 'high_debt' in tags:
        items.append({'text': '⚠️ EV/MC ≥ 1.2 (חוב גבוה)', 'pts': -20})
    if 'high_growth' in tags:
        items.append({'text': '🔥 צמיחה גבוהה', 'pts': 20})
    if ev_sales_ratio is not None and ev_sales_ratio > 20:
        items.append({'text': '📊 EV/Sales > 20 (מוערכת ביתר)', 'pts': -10})
    if short_pct is not None and short_pct > 15:
        items.append({'text': f'📉 שורט {short_pct:.0f}% (סיכון)', 'pts': -12})
    if rsi_val is not None and rsi_val > 75:
        items.append({'text': f'⚡ RSI {rsi_val:.0f} (קניית יתר)', 'pts': -6})
    return items


def _risk_score(tags: list, short_pct: Optional[float], rsi: Optional[float]) -> int:
    """
    Risk Score (0–100):
      +30 high_debt
      +25 loss
      +20 short > 15%
      +10 RSI > 75
    """
    score = 0
    if 'high_debt' in tags:
        score += 30
    if 'loss' in tags:
        score += 25
    if short_pct is not None and short_pct > 15:
        score += 20
    if rsi is not None and rsi > 75:
        score += 10
    return max(0, min(100, score))


def _get_market_session() -> str:
    """Return current US market session: 'pre' | 'regular' | 'post' | 'closed'."""
    try:
        import pytz as _pytz
        from datetime import datetime as _dt
        et = _pytz.timezone('US/Eastern')
        now = _dt.now(et)
        if now.weekday() >= 5:
            return 'closed'
        h = now.hour + now.minute / 60.0
        if h < 4:    return 'closed'
        if h < 9.5:  return 'pre'
        if h < 16:   return 'regular'
        if h < 20:   return 'post'
        return 'closed'
    except Exception:
        return 'regular'


def _fetch_intraday_sync(ticker: str) -> dict:
    """
    Fetch 5-minute bars with extended hours (prePost=True) and compute:
      chg_5m           — price change vs ~5 min ago (1 bar back)
      chg_30m          — price change vs ~30 min ago (6 bars back)
      extended_price   — current live price (pre/post/regular)
      extended_chg_pct — % change from last regular-session close
      prev_close       — last regular-session closing price
    Fallback: if 5m returns too few bars, try 15m (chg_5m ≈ 1 bar, chg_30m = 2 bars).
    """
    import yfinance as _yf
    from concurrent.futures import ThreadPoolExecutor as _TPE2

    def _get_bars(interval: str, period: str):
        return _yf.Ticker(ticker).history(period=period, interval=interval, prepost=True, timeout=8)

    def _build_result(hist, is_5m: bool):
        if hist is None or len(hist) < 2:
            return None
        closes = hist['Close'].dropna()
        if len(closes) < 2:
            return None
        cur = float(closes.iloc[-1])
        result = {'extended_price': round(cur, 4)}
        if is_5m:
            # 5m bars: 1 bar=5m, 2 bars=10m, 6 bars=30m, 48 bars=4h
            ago5  = float(closes.iloc[-2]) if len(closes) >= 2 else None
            ago10 = float(closes.iloc[-3]) if len(closes) >= 3 else None
            ago30 = float(closes.iloc[-7]) if len(closes) >= 7 else (float(closes.iloc[0]) if len(closes) >= 2 else None)
            ago4h = float(closes.iloc[-49]) if len(closes) >= 49 else (float(closes.iloc[0]) if len(closes) >= 2 else None)
        else:
            # 15m bars: 1 bar≈15m, 2 bars≈30m, 16 bars≈4h
            ago5  = float(closes.iloc[-2]) if len(closes) >= 2 else None
            ago10 = None
            ago30 = float(closes.iloc[-3]) if len(closes) >= 3 else (float(closes.iloc[0]) if len(closes) >= 2 else None)
            ago4h = float(closes.iloc[-17]) if len(closes) >= 17 else (float(closes.iloc[0]) if len(closes) >= 2 else None)
        if ago5 and ago5 > 0:
            result['chg_5m'] = round((cur - ago5) / ago5 * 100, 2)
        if ago10 and ago10 > 0:
            result['chg_10m'] = round((cur - ago10) / ago10 * 100, 2)
        if ago30 and ago30 > 0:
            result['chg_30m'] = round((cur - ago30) / ago30 * 100, 2)
        if ago4h and ago4h > 0:
            result['chg_4h'] = round((cur - ago4h) / ago4h * 100, 2)
        return result

    def _add_extended_chg(hist, result):
        try:
            import pytz as _pytz
            et = _pytz.timezone('US/Eastern')
            hist_et = hist.copy()
            hist_et.index = hist.index.tz_convert(et)
            h_flt = hist_et.index.hour + hist_et.index.minute / 60.0
            reg_mask = (h_flt >= 9.5) & (h_flt < 16.0)
            reg_closes = hist_et[reg_mask]['Close'].dropna()
            if not reg_closes.empty:
                prev_close = float(reg_closes.iloc[-1])
                cur = result.get('extended_price')
                if prev_close > 0 and cur is not None:
                    result['prev_close'] = round(prev_close, 4)
                    result['extended_chg_pct'] = round((cur - prev_close) / prev_close * 100, 2)
        except Exception:
            pass

    try:
        with _TPE2(max_workers=1) as pool:
            hist = pool.submit(lambda: _get_bars('5m', '7d')).result(timeout=12)
        result = _build_result(hist, is_5m=True)
        if result is None:
            with _TPE2(max_workers=1) as pool2:
                hist = pool2.submit(lambda: _get_bars('15m', '5d')).result(timeout=12)
            result = _build_result(hist, is_5m=False)
        if result and hist is not None and len(hist) >= 2:
            _add_extended_chg(hist, result)
        return result if result else {}
    except Exception:
        return {}


_TITLE_TRANSLATE_CACHE: dict = {}  # {original_title: hebrew_title}

def _translate_title_he(title: str) -> str:
    """Translate text to Hebrew using deep-translator, with in-process cache."""
    if not title:
        return title
    cached = _TITLE_TRANSLATE_CACHE.get(title)
    if cached:
        return cached
    for attempt in range(2):
        try:
            from deep_translator import GoogleTranslator
            result = GoogleTranslator(source='en', target='iw').translate(title)
            if result and result != title:
                _TITLE_TRANSLATE_CACHE[title] = result
                return result
        except Exception:
            pass
    return title


def _fetch_ticker_news_sync(ticker: str) -> list:
    """
    Fetch yfinance news for a ticker with a hard 3-second timeout.
    Returns list of {title, publisher, link, published} dicts, titles translated to Hebrew.
    """
    import yfinance as _yf
    from concurrent.futures import ThreadPoolExecutor as _TPE2, TimeoutError as _TE

    def _inner():
        return _yf.Ticker(ticker).news or []

    def _normalize(n: dict) -> dict:
        # New yfinance format: {'id': ..., 'content': {...}}
        c = n.get('content') or {}
        if c:
            pub_date = c.get('pubDate') or c.get('displayTime') or ''
            import re as _re
            ts = 0
            if pub_date:
                try:
                    from datetime import datetime as _dt
                    ts = int(_dt.fromisoformat(pub_date.replace('Z', '+00:00')).timestamp())
                except Exception:
                    pass
            link = ''
            cu = c.get('canonicalUrl') or {}
            if isinstance(cu, dict):
                link = cu.get('url', '')
            if not link:
                link = c.get('previewUrl', '')
            provider = c.get('provider') or {}
            publisher = provider.get('displayName', '') if isinstance(provider, dict) else ''
            return {
                'title':     c.get('title', ''),
                'publisher': publisher,
                'link':      link,
                'published': ts,
            }
        # Legacy flat format
        return {
            'title':     n.get('title', ''),
            'publisher': n.get('publisher', ''),
            'link':      n.get('link', ''),
            'published': n.get('providerPublishTime', 0),
        }

    try:
        with _TPE2(max_workers=1) as pool:
            raw = pool.submit(_inner).result(timeout=3)
        items = [_normalize(n) for n in raw[:5]]
        # Keep original English title for keyword matching, translate display title
        for item in items:
            if item.get('title'):
                item['title_en'] = item['title']   # original — used by _classify_move_reason
                item['title'] = _translate_title_he(item['title'])
        return items
    except Exception:
        return []


_CATALYST_RULES = [
    (['beat', 'earn', 'eps', 'revenue', 'q4', 'q3', 'q2', 'q1',
      'profit', 'quarter', 'results', 'record sales', 'record revenue',
      'surprise', 'topped estimates', 'exceeds'],
     'earnings', '📊 תוצאות פיננסיות', 'high'),
    (['upgrade', 'overweight', 'outperform', 'strong buy',
      'target raised', 'price target', 'initiates', 'rate buy', 'reiterate buy',
      'bull', 'top pick'],
     'upgrade', '⬆️ שדרוג אנליסט', 'high'),
    (['downgrade', 'underweight', 'underperform', 'sell rating',
      'target cut', 'target lowered', 'reduces', 'bear'],
     'downgrade', '⬇️ הורדת דירוג', 'high'),
    (['fda', 'approval', 'approved', 'clearance', 'phase 3', 'phase iii',
      'nda', 'bla', 'pdufa', 'phase 2', 'clinical trial', 'efficacy'],
     'fda', '💊 FDA / רגולציה', 'high'),
    (['acqui', 'merger', 'buyout', 'takeover', 'deal',
      'agreement', 'transaction', 'purchase', 'tender offer'],
     'ma', '🤝 מיזוג / רכישה', 'high'),
    (['guidance', 'outlook', 'forecast', 'raises guidance',
      'lowers guidance', 'reiterates', 'sees fy', 'sees q'],
     'guidance', '🔮 תחזית החברה', 'medium'),
    (['contract', 'award', 'wins', 'partnership', 'collaboration',
      'selected', 'chosen', 'signed', 'expands'],
     'contract', '📝 חוזה / שותפות', 'medium'),
    (['short', 'fraud', 'investigation', 'lawsuit', 'sec filing',
      'subpoena', 'recall', 'warning letter', 'class action'],
     'risk', '⚠️ חקירה / סיכון', 'medium'),
    (['offering', 'dilut', 'shares', 'secondary', 'atm', 'shelf'],
     'dilution', '📉 הנפקת מניות', 'medium'),
    (['insider buy', 'insider purchas', 'ceo buy', 'director buy', '10b5'],
     'insider', '🏷️ קניית פנים', 'medium'),
    (['split', 'stock split', 'reverse split'],
     'split', '✂️ פיצול מניה', 'medium'),
    (['dividend', 'special dividend', 'distribution'],
     'dividend', '💵 דיבידנד', 'medium'),
    (['ai ', 'artificial intelligence', 'machine learning', 'gpu',
      'data center', 'quantum', 'chip', 'semiconductor'],
     'ai_sector', '🤖 AI / סמיקונדקטור', 'medium'),
]


def _classify_move_reason(fund: dict, news: list, change_pct) -> list:
    """
    Derive reasons why the stock is moving today.
    Scans ALL news headlines and fundamental data to find real catalysts.
    Returns list of {type, label, confidence, source} — at most 4 reasons.
    """
    reasons = []
    seen_types = set()
    chg = float(change_pct) if change_pct else 0

    earnings_date_str = fund.get('earnings_date', '') or ''
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    for d in [today, yesterday]:
        if d.strftime('%b %d') in earnings_date_str or d.strftime('%-d %b') in earnings_date_str:
            reasons.append({'type': 'earnings', 'label': '📊 דוח רבעוני', 'confidence': 'high', 'source': f'דוח {earnings_date_str}'})
            seen_types.add('earnings')
            break

    gap = _parse_fv_num(fund.get('gap_pct', ''))
    if gap and abs(gap) >= 3:
        sign = '+' if gap > 0 else ''
        reasons.append({
            'type': 'gap', 'confidence': 'high',
            'label': f'{"📈" if gap > 0 else "📉"} Gap {sign}{gap:.1f}%',
            'source': 'פתיחה עם פער',
        })
        seen_types.add('gap')

    rel_vol = _parse_fv_num(fund.get('rel_volume', ''))
    if rel_vol and rel_vol >= 3:
        reasons.append({
            'type': 'volume_spike', 'confidence': 'medium',
            'label': f'📊 נפח x{rel_vol:.1f}', 'source': 'נפח חריג',
        })
        seen_types.add('volume_spike')

    for article in (news or [])[:5]:
        if len(reasons) >= 4:
            break
        # Use original English title for keyword matching (translated title breaks English rules)
        title = (article.get('title_en') or article.get('title', '') or '').lower()
        publisher = article.get('publisher', '') or ''
        for keywords, rtype, label, conf in _CATALYST_RULES:
            if rtype in seen_types:
                continue
            if any(w in title for w in keywords):
                source_short = publisher.strip('()') if publisher else ''
                reasons.append({
                    'type': rtype, 'label': label, 'confidence': conf,
                    'source': source_short or article.get('title', '')[:60],
                })
                seen_types.add(rtype)
                break

    sma20 = _parse_fv_num(fund.get('sma20_dist', ''))
    if sma20 is not None and abs(sma20) > 8 and 'technical' not in seen_types:
        reasons.append({
            'type': 'technical', 'confidence': 'low',
            'label': f'{"📈" if sma20 > 0 else "📉"} {abs(sma20):.0f}% {"מעל" if sma20 > 0 else "מתחת"} SMA20',
            'source': 'סטייה מהממוצע',
        })

    if not reasons and abs(chg) > 0:
        label = f'{"📈" if chg > 0 else "📉"} תנועה טכנית ({chg:+.1f}%)'
        reasons.append({'type': 'technical', 'label': label, 'confidence': 'low', 'source': ''})

    return reasons[:4]


def _fetch_summary_sync(ticker: str) -> str:
    """
    Fetch company business summary from yfinance with a 4-second hard timeout.
    Returns the first sentence (≤200 chars) or empty string on failure.
    """
    import yfinance as _yf
    from concurrent.futures import ThreadPoolExecutor as _TPE2

    def _inner():
        info = _yf.Ticker(ticker).info
        return (info.get('longBusinessSummary') or info.get('description') or '').strip()

    try:
        with _TPE2(max_workers=1) as pool:
            summary = pool.submit(_inner).result(timeout=4)
        if summary:
            dot = summary.find('. ')
            if 30 < dot < 220:
                text = summary[:dot + 1]
            else:
                text = summary[:200]
            return _translate_title_he(text)
        return ''
    except Exception:
        return ''


def _fetch_sales_qq_sync(ticker: str) -> Optional[float]:
    """
    Best-effort fallback for Sales Q/Q using yfinance quarterly financials.
    Returns percentage growth (latest quarter vs previous) or None.
    """
    import yfinance as _yf
    from concurrent.futures import ThreadPoolExecutor as _TPE2

    def _inner():
        stk = _yf.Ticker(ticker)
        # yfinance API may expose quarterly_financials or quarterly_income_stmt
        fin = getattr(stk, "quarterly_financials", None)
        if fin is None or len(getattr(fin, "columns", [])) < 2:
            fin = getattr(stk, "quarterly_income_stmt", None)
        if fin is None or 'Total Revenue' not in getattr(fin, "index", []):
            return None
        cols = list(fin.columns)
        if len(cols) < 2:
            return None
        latest = fin[cols[0]].get('Total Revenue')
        prev   = fin[cols[1]].get('Total Revenue')
        if latest is None or prev is None or prev == 0:
            return None
        return float((latest - prev) / prev * 100.0)

    try:
        with _TPE2(max_workers=1) as pool:
            val = pool.submit(_inner).result(timeout=6)
        return val
    except Exception:
        return None


async def _fallback_sales_qq_batch(tickers: list[str]) -> dict:
    """
    Fetch Sales Q/Q for a small batch of tickers via yfinance (fallback when Finviz missing).
    Hard-capped concurrency and timeouts.
    """
    if not tickers:
        return {}
    loop = asyncio.get_running_loop()
    results: dict = {}
    # Limit to first 15 to avoid heavy calls
    subset = tickers[:15]
    with _TPE(max_workers=3) as pool:
        futs = [
            loop.run_in_executor(pool, _fetch_sales_qq_sync, t)
            for t in subset
        ]
        done = await asyncio.gather(*futs, return_exceptions=True)
    for t, val in zip(subset, done):
        if isinstance(val, (int, float)):
            results[t] = float(val)
    return results


@router.get("/screener/prices")
async def get_screener_prices(tickers: str = Query(...)):
    """Fetch live prices (pre/post-market aware) for portfolio tickers via yfinance."""
    ticker_list = [t.strip().upper() for t in tickers.split(',') if t.strip()]
    if not ticker_list:
        return {}

    loop = asyncio.get_event_loop()
    results = {}

    async def fetch_one(ticker: str):
        try:
            intra = await asyncio.wait_for(
                loop.run_in_executor(None, lambda t=ticker: _fetch_intraday_sync(t)),
                timeout=8.0,
            )
            if intra:
                _FV_INTRA_CACHE[ticker] = intra
                _FV_INTRA_CACHE_TIME[ticker] = _time.time()
            price = intra.get('extended_price') or intra.get('prev_close')
            if price:
                results[ticker] = {
                    "price": float(price),
                    "change_pct": intra.get('extended_chg_pct'),
                    "prev_close": intra.get('prev_close'),
                    "source": "yfinance_extended",
                }
        except Exception:
            pass

    await asyncio.gather(*[fetch_one(t) for t in ticker_list])
    return results


_fv_table_lock: asyncio.Lock | None = None

def _get_fv_table_lock():
    global _fv_table_lock
    if _fv_table_lock is None:
        _fv_table_lock = asyncio.Lock()
    return _fv_table_lock

@router.get("/screener/finviz-table")
async def get_finviz_table(
    filters: str = Query(default=_FV_DEFAULT_FILTERS),
    ensure_tickers: str = Query(default=""),
):
    """
    Finviz-style fundamental table screener with move reasons + news.
    Price cache: 25 s. Fundamentals: 30 min. News: 5 min per ticker.
    """
    global _FV_TABLE_CACHE, _FV_TABLE_CACHE_TIME
    global _FV_FUND_CACHE, _FV_FUND_CACHE_TIME
    global _FV_NEWS_CACHE, _FV_NEWS_CACHE_TIME
    import time as _t
    now = _t.time()

    _evict_expired_caches()

    cache_key = f"{filters}|{ensure_tickers}"
    if (
        _FV_TABLE_CACHE
        and _FV_TABLE_CACHE.get("cache_key") == cache_key
        and (now - _FV_TABLE_CACHE_TIME) < _FV_TABLE_CACHE_TTL
    ):
        return _FV_TABLE_CACHE["data"]

    lock = _get_fv_table_lock()
    if lock.locked():
        if _FV_TABLE_CACHE and _FV_TABLE_CACHE.get("data"):
            return _FV_TABLE_CACHE["data"]
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=202,
            content={'stocks': [], 'count': 0, 'loading': True,
                     'message': 'First scan in progress — please wait'},
        )

    async with lock:
        now = _t.time()
        if (
            _FV_TABLE_CACHE
            and _FV_TABLE_CACHE.get("cache_key") == cache_key
            and (now - _FV_TABLE_CACHE_TIME) < _FV_TABLE_CACHE_TTL
        ):
            return _FV_TABLE_CACHE["data"]

        return await _do_finviz_table_scan(filters, ensure_tickers, now, cache_key)


async def _do_finviz_table_scan(filters, ensure_tickers, now, cache_key):
    """Actual scanning logic — called under lock."""
    global _FV_TABLE_CACHE, _FV_TABLE_CACHE_TIME
    global _FV_FUND_CACHE, _FV_FUND_CACHE_TIME
    global _FV_NEWS_CACHE, _FV_NEWS_CACHE_TIME

    has_cache = bool(_FV_TABLE_CACHE and _FV_TABLE_CACHE.get("data"))
    scan_timeout = 90 if not has_cache else 50

    try:
        return await asyncio.wait_for(
            _finviz_table_inner(filters, ensure_tickers, now, cache_key),
            timeout=scan_timeout,
        )
    except asyncio.TimeoutError:
        print(f"[finviz-table] TIMEOUT (>{scan_timeout}s)")
        if has_cache:
            return _FV_TABLE_CACHE["data"]
        return {'stocks': [], 'count': 0, 'error': 'timeout'}
    except Exception as e:
        print(f"[finviz-table] Error: {e}")
        import traceback; traceback.print_exc()
        if _FV_TABLE_CACHE and _FV_TABLE_CACHE.get("data"):
            return _FV_TABLE_CACHE["data"]
        return {'stocks': [], 'count': 0, 'error': str(e)[:200]}


async def _finviz_table_inner(filters, ensure_tickers, now, cache_key):
    """Core scanning — scrapes, merges, caches."""
    global _FV_TABLE_CACHE, _FV_TABLE_CACHE_TIME
    global _FV_FUND_CACHE, _FV_FUND_CACHE_TIME
    global _FV_NEWS_CACHE, _FV_NEWS_CACHE_TIME

    raw_stocks = []
    seen_tickers = set()
    pages = await asyncio.gather(*[
        finviz_screener._scrape_screener(
            {'v': '111', 'f': filters, 'o': '-changeopen', 'r': str(r_start)},
            'finviz-table',
        )
        for r_start in [1, 21, 41]
    ], return_exceptions=True)
    for page in pages:
        if isinstance(page, Exception):
            continue
        for s in page:
            t = s.get('ticker')
            if t and t not in seen_tickers:
                seen_tickers.add(t)
                raw_stocks.append(s)

    # ── 1b. ensure_tickers: טיקרים לחיזוק — נשלוף מ-Finviz quote אם לא בסריקה ───
    # נתונים מגיעים כולם מ-Finviz (screener + quote.ashx)
    _WATCHLIST = ["AAOI"]  # תמיד לכלול
    portfolio_tickers = set(smart_portfolio.positions.keys()) if smart_portfolio.positions else set()
    ensure_set = set(_WATCHLIST) | portfolio_tickers | {t.strip().upper() for t in ensure_tickers.split(",") if t.strip()}
    ensure_set -= seen_tickers
    if ensure_set:
        for ticker in ensure_set:
            if not re.match(r"^[A-Z]{1,5}$", ticker):
                continue
            try:
                funds = await finviz_fundamentals.get_fundamentals_batch([ticker])
                f = funds.get(ticker)
                if not f:
                    continue
                raw_stocks.insert(
                    0,
                    {
                        "ticker": ticker,
                        "company": f.get("company", ticker),
                        "sector": f.get("sector", ""),
                        "industry": f.get("industry", ""),
                        "price": _parse_fv_num(f.get("price", "")),
                        "change_pct": _parse_fv_num(f.get("change_pct", "")),
                        "volume": _parse_fv_num(f.get("volume", "")),
                        "market_cap_str": f.get("market_cap", ""),
                        "scan_sources": ["ensure_tickers"],
                    },
                )
                seen_tickers.add(ticker)
            except Exception:
                pass

    if not raw_stocks:
        return {'stocks': [], 'count': 0, 'filters': filters,
                'generated_at': datetime.now().isoformat()}

    tickers = [s['ticker'] for s in raw_stocks if s.get('ticker')]

    # ── 2. Fundamentals מ-Finviz בלבד (EPS, RSI, Short%, מחיר, שינוי) ──────────
    fund_stale = (now - _FV_FUND_CACHE_TIME) > _FV_FUND_CACHE_TTL
    fund_missing = tickers if fund_stale else [t for t in tickers if t not in _FV_FUND_CACHE]
    if fund_missing:
        batches = [fund_missing[i:i+15] for i in range(0, len(fund_missing), 15)]
        results = await asyncio.gather(*[
            finviz_fundamentals.get_fundamentals_batch(b) for b in batches
        ], return_exceptions=True)
        for res in results:
            if isinstance(res, dict):
                _FV_FUND_CACHE.update({k: v for k, v in res.items() if v})
        _FV_FUND_CACHE_TIME = now

    # ── 3. News from Finviz fundamentals (already scraped) ──────────────────
    for t in tickers:
        fund = _FV_FUND_CACHE.get(t)
        if fund and fund.get('news') and t not in _FV_NEWS_CACHE:
            _FV_NEWS_CACHE[t] = fund['news']
            _FV_NEWS_CACHE_TIME[t] = now

    # ── 3b. Translate news titles to Hebrew in background ─────────────────
    news_to_translate = [
        t for t in tickers
        if _FV_NEWS_CACHE.get(t)
        and any(not n.get('title_he') for n in _FV_NEWS_CACHE[t])
    ]

    def _translate_news_batch(ticker_list):
        for t in ticker_list:
            items = _FV_NEWS_CACHE.get(t) or []
            for item in items:
                if item.get('title') and not item.get('title_he'):
                    item['title_he'] = _translate_title_he(item['title'])

    if news_to_translate:
        loop = asyncio.get_running_loop()
        asyncio.ensure_future(
            loop.run_in_executor(_TPE(max_workers=2), _translate_news_batch, news_to_translate)
        )

    # ── 4. Intraday momentum — ברקע (chg_5m, chg_10m, chg_30m) ─────────
    intra_missing = [
        t for t in tickers
        if t not in _FV_INTRA_CACHE or (now - _FV_INTRA_CACHE_TIME.get(t, 0)) > _FV_INTRA_CACHE_TTL
    ]

    # ── 5. Summary — ברקע (לא חוסם) ──────────────────────────────────────
    summary_missing = [
        t for t in tickers
        if t not in _FV_SUMMARY_CACHE or (now - _FV_SUMMARY_CACHE_TIME.get(t, 0)) > _FV_SUMMARY_CACHE_TTL
    ]

    # ── 5b. Technical Analysis — ברקע (all tickers) ──────────────────
    ta_missing = [
        t for t in tickers
        if t not in _FV_TA_CACHE or (now - _FV_TA_CACHE_TIME.get(t, 0)) > _FV_TA_CACHE_TTL
    ]

    def _compute_ta_sync(ticker: str):
        return _compute_ta(ticker)

    async def _enrich_in_background():
        """Intraday + Summary + TA — ברקע, מקביל."""
        loop = asyncio.get_running_loop()

        async def _do_intra():
            if not _bg_intra_missing:
                return
            try:
                import yfinance as _yf2
                # Batch download — much faster than per-ticker fetches
                _tstr = ' '.join(_bg_intra_missing)
                def _batch_download():
                    return _yf2.download(
                        tickers=_tstr, period='7d', interval='5m',
                        prepost=True, group_by='ticker', threads=True,
                        auto_adjust=True, progress=False,
                    )
                with _TPE(max_workers=1) as pool:
                    df_all = await asyncio.wait_for(
                        loop.run_in_executor(pool, _batch_download),
                        timeout=20
                    )
                ts_now = _time.time()
                for t in _bg_intra_missing:
                    try:
                        # Multi-ticker download has MultiIndex columns
                        if isinstance(df_all.columns, __import__('pandas').MultiIndex):
                            closes = df_all[t]['Close'].dropna() if t in df_all.columns.get_level_values(0) else None
                        else:
                            closes = df_all['Close'].dropna() if len(_bg_intra_missing) == 1 else None
                        if closes is None or len(closes) < 2:
                            continue
                        cur = float(closes.iloc[-1])
                        res = {'extended_price': round(cur, 4)}
                        ago5  = float(closes.iloc[-2]) if len(closes) >= 2 else None
                        ago10 = float(closes.iloc[-3]) if len(closes) >= 3 else None
                        ago30 = float(closes.iloc[-7]) if len(closes) >= 7 else float(closes.iloc[0])
                        ago4h = float(closes.iloc[-49]) if len(closes) >= 49 else float(closes.iloc[0])
                        if ago5 and ago5 > 0:   res['chg_5m']  = round((cur-ago5)/ago5*100,2)
                        if ago10 and ago10 > 0: res['chg_10m'] = round((cur-ago10)/ago10*100,2)
                        if ago30 and ago30 > 0: res['chg_30m'] = round((cur-ago30)/ago30*100,2)
                        if ago4h and ago4h > 0: res['chg_4h']  = round((cur-ago4h)/ago4h*100,2)
                        _FV_INTRA_CACHE[t] = res
                        _FV_INTRA_CACHE_TIME[t] = ts_now
                    except Exception:
                        pass
            except Exception:
                pass

        async def _do_summary():
            if not summary_missing:
                return
            try:
                with _TPE(max_workers=3) as pool:
                    futs = [loop.run_in_executor(pool, _fetch_summary_sync, t) for t in summary_missing]
                    ress = await asyncio.gather(*futs, return_exceptions=True)
                for t, res in zip(summary_missing, ress):
                    if isinstance(res, str):
                        _FV_SUMMARY_CACHE[t] = res
                        _FV_SUMMARY_CACHE_TIME[t] = now
            except Exception:
                pass

        async def _do_ta():
            if not ta_missing:
                return
            try:
                with _TPE(max_workers=4) as pool:
                    futs = [loop.run_in_executor(pool, _compute_ta_sync, t) for t in ta_missing]
                    ress = await asyncio.gather(*futs, return_exceptions=True)
                for t, res in zip(ta_missing, ress):
                    if isinstance(res, dict) and res:
                        _FV_TA_CACHE[t] = res
                        _FV_TA_CACHE_TIME[t] = _time.time()
            except Exception:
                pass

        # Run intraday + TA in parallel; summary is lightweight and can run in parallel too
        await asyncio.gather(_do_intra(), _do_ta(), _do_summary(), return_exceptions=True)

    # אחזור intraday — batch download סינכרוני לכל המניות החסרות
    import pandas as _pd2
    if intra_missing:
        _t0_intra = _time.time()
        try:
            import yfinance as _yf_sync
            _tstr_all = ' '.join(intra_missing)
            def _sync_batch_dl():
                return _yf_sync.download(
                    tickers=_tstr_all, period='7d', interval='5m',
                    prepost=True, group_by='ticker', threads=True,
                    auto_adjust=True, progress=False,
                )
            _loop2 = asyncio.get_running_loop()
            with _TPE(max_workers=1) as _pool2:
                _df_sync = await asyncio.wait_for(
                    _loop2.run_in_executor(_pool2, _sync_batch_dl),
                    timeout=20
                )
            _ts_sync = _time.time()
            _cached_count = 0
            for _t in intra_missing:
                try:
                    if isinstance(_df_sync.columns, _pd2.MultiIndex):
                        _lvl0 = _df_sync.columns.get_level_values(0)
                        _lvl1 = _df_sync.columns.get_level_values(1)
                        # group_by='ticker': level0=ticker, level1=OHLCV
                        if _t in _lvl0:
                            _cl = _df_sync[_t]['Close'].dropna()
                        # group_by='column' (default): level0=OHLCV, level1=ticker
                        elif _t in _lvl1:
                            _cl = _df_sync['Close'][_t].dropna()
                        else:
                            continue
                    else:
                        _cl = _df_sync['Close'].dropna() if len(intra_missing) == 1 else None
                    if _cl is None or len(_cl) < 2:
                        continue
                    _cur = float(_cl.iloc[-1])
                    _res2 = {'extended_price': round(_cur, 4)}
                    _a5  = float(_cl.iloc[-2]) if len(_cl) >= 2 else None
                    _a10 = float(_cl.iloc[-3]) if len(_cl) >= 3 else None
                    _a30 = float(_cl.iloc[-7]) if len(_cl) >= 7 else float(_cl.iloc[0])
                    _a4h = float(_cl.iloc[-49]) if len(_cl) >= 49 else float(_cl.iloc[0])
                    if _a5 and _a5 > 0:   _res2['chg_5m']  = round((_cur-_a5)/_a5*100, 2)
                    if _a10 and _a10 > 0: _res2['chg_10m'] = round((_cur-_a10)/_a10*100, 2)
                    if _a30 and _a30 > 0: _res2['chg_30m'] = round((_cur-_a30)/_a30*100, 2)
                    if _a4h and _a4h > 0: _res2['chg_4h']  = round((_cur-_a4h)/_a4h*100, 2)
                    _FV_INTRA_CACHE[_t] = _res2
                    _FV_INTRA_CACHE_TIME[_t] = _ts_sync
                    _cached_count += 1
                except Exception:
                    pass
            print(f"[intra-sync] batch ok: {_cached_count}/{len(intra_missing)} cached in {_ts_sync-_t0_intra:.1f}s")
        except asyncio.TimeoutError:
            print(f"[intra-sync] TIMEOUT after {_time.time()-_t0_intra:.1f}s, fallback to per-ticker")
            _first_batch = intra_missing[:15]
            try:
                _loop = asyncio.get_running_loop()
                with _TPE(max_workers=4) as _pool:
                    _futs = [_loop.run_in_executor(_pool, _fetch_intraday_sync, t) for t in _first_batch]
                    _ress = await asyncio.wait_for(asyncio.gather(*_futs, return_exceptions=True), timeout=8.0)
                for _t, _res in zip(_first_batch, _ress):
                    if isinstance(_res, dict) and _res:
                        _FV_INTRA_CACHE[_t] = _res
                        _FV_INTRA_CACHE_TIME[_t] = _time.time()
            except (asyncio.TimeoutError, Exception):
                pass
        except Exception as _e_intra:
            print(f"[intra-sync] ERROR: {_e_intra}")

    _bg_intra_missing = [t for t in intra_missing if t not in _FV_INTRA_CACHE]
    asyncio.create_task(_enrich_in_background())

    # ── 6. Merge — בונה טבלה עם fundamentals מ-Finviz ─────────────────────────
    stocks = []
    for raw in raw_stocks:
        t     = raw.get('ticker', '')
        fund  = _FV_FUND_CACHE.get(t) or {}
        news  = _FV_NEWS_CACHE.get(t) or []
        intra = _FV_INTRA_CACHE.get(t) or {}
        ta_data = _FV_TA_CACHE.get(t) or {}
        price = raw.get('price') or _parse_fv_num(fund.get('price', '')) or 0
        mc    = _parse_fv_num(raw.get('market_cap_str', '') or fund.get('market_cap', ''))

        change_pct = raw.get('change_pct')
        reasons = _classify_move_reason(fund, news, change_pct)
        tags    = _stock_tags(fund, price)
        ev      = _compute_ev(fund)
        ev_mc_ratio = round(ev / mc, 3) if ev and mc and mc > 0 else None

        # Numeric EV / ratios for scores
        ev      = _compute_ev(fund)
        ev_sales_field = _parse_fv_num(fund.get('ev_sales', ''))
        ev_sales_ratio = None
        if ev_sales_field is not None:
            ev_sales_ratio = ev_sales_field
        elif ev and _parse_fv_num(fund.get('sales', '')):
            sales_val = _parse_fv_num(fund.get('sales', ''))
            if sales_val and sales_val > 0:
                ev_sales_ratio = ev / sales_val

        tags = _stock_tags(fund, price)
        short_pct = _parse_fv_num(fund.get('short_float', ''))
        rsi_val   = _parse_fv_num(fund.get('rsi', ''))
        health    = _health_score(tags, ev_sales_ratio)
        risk      = _risk_score(tags, short_pct, rsi_val)
        ai_signal = health - risk * 0.6
        if   ai_signal >= 70: ai_label = 'Strong Setup'
        elif ai_signal >= 50: ai_label = 'Watchlist'
        else:                 ai_label = 'Avoid'

        # שינוי טרום/אחרי שעות: אם יש מחיר נוכחי אבל אין extended_chg_pct, לחשב מ־prev_close (מ־intra או מ־Finviz)
        ext_price = intra.get('extended_price')
        prev_close = intra.get('prev_close')
        if prev_close is None:
            prev_close = _parse_fv_num(fund.get('prev_close', ''))
        extended_chg_pct = intra.get('extended_chg_pct')
        if extended_chg_pct is None and ext_price is not None and prev_close is not None and prev_close > 0:
            extended_chg_pct = round((float(ext_price) - prev_close) / prev_close * 100, 2)
        if prev_close is not None and isinstance(prev_close, (int, float)):
            prev_close = round(float(prev_close), 4)

        stocks.append({
            'ticker':         t,
            'company':        raw.get('company') or fund.get('company', t),
            'sector':         raw.get('sector') or fund.get('sector', ''),
            'industry':       raw.get('industry') or fund.get('industry', ''),
            # Price/volume
            'price':          price,
            'change_pct':     change_pct,
            'volume':         raw.get('volume'),
            'market_cap':     mc,
            'market_cap_str': raw.get('market_cap_str') or fund.get('market_cap', ''),
            # Fundamentals
            'income':         _parse_fv_num(fund.get('income', '')),
            'income_str':     fund.get('income', ''),
            'sales':          _parse_fv_num(fund.get('sales', '')),
            'sales_str':      fund.get('sales', ''),
            # Year-over-year sales growth (Sales Y/Y) אם קיים בפינויז (לדוגמה Sales YoY)
            'sales_yy':       _parse_fv_num(fund.get('sales_year', '') or fund.get('sales_yoy', '') or fund.get('sales_year_yoy', '')),
            # Enterprise Value & ratios
            'ev':             ev,
            'ev_str':         fund.get('enterprise_value', ''),
            'ev_mc_ratio':    ev_mc_ratio,
            'ev_sales_ratio': ev_sales_ratio,
            'pe':             fund.get('pe_ratio', ''),
            'forward_pe':     fund.get('forward_pe', ''),
            'eps_this_y':     fund.get('eps_this_y', ''),
            'eps_qq':         fund.get('eps_qq', ''),
            'sales_qq':       fund.get('sales_qq', ''),
            'profit_margin':  fund.get('profit_margin', ''),
            'gross_margin':   fund.get('gross_margin', ''),
            'debt_equity':    fund.get('debt_equity', ''),
            'cash_per_share': fund.get('cash_per_share', ''),
            'short_float':    fund.get('short_float', ''),
            'short_ratio':    fund.get('short_ratio', ''),
            'short_interest': fund.get('short_interest', ''),
            'avg_volume':     fund.get('avg_volume', ''),
            'shs_float':      fund.get('shs_float', ''),
            'inst_own':       fund.get('inst_own', ''),
            'insider_own':    fund.get('insider_own', ''),
            'insider_trans':  fund.get('insider_trans', ''),
            'rsi':            fund.get('rsi', ''),
            'sma20':          fund.get('sma20_dist', ''),
            'sma50':          fund.get('sma50_dist', ''),
            'atr':            fund.get('atr', ''),
            'beta':           fund.get('beta', ''),
            'volatility':     fund.get('volatility', ''),
            'target_price':   fund.get('target_price', ''),
            'analyst_recom':  fund.get('analyst_recom', ''),
            'earnings_date':  fund.get('earnings_date', ''),
            'gap_pct':        fund.get('gap_pct', ''),
            'perf_week':      fund.get('perf_week', ''),
            'perf_month':     fund.get('perf_month', ''),
            'enterprise_value': fund.get('enterprise_value', ''),
            'ev_ebitda':      fund.get('ev_ebitda', ''),
            'ev_sales':       fund.get('ev_sales', ''),
            # Intraday momentum (extended hours aware)
            'chg_5m':            intra.get('chg_5m'),
            'chg_10m':           intra.get('chg_10m'),
            'chg_30m':           intra.get('chg_30m'),
            'chg_4h':            intra.get('chg_4h'),
            'extended_price':    intra.get('extended_price'),
            'extended_chg_pct':  extended_chg_pct,
            'prev_close':        prev_close,
            # Earnings status
            'eps_surpr':      fund.get('eps_surpr', ''),
            'eps_sales_surpr':fund.get('eps_sales_surpr', ''),
            'earnings_verdict': _earnings_verdict(fund),
            # Rel Volume
            'rel_volume':     fund.get('rel_volume', ''),
            # Enrichments & scores
            'tags':           tags,
            'health_score':   health,
            'risk_score':     risk,
            'ai_signal':      round(ai_signal, 1),
            'ai_label':       ai_label,
            'health_detail':  _health_detail(tags, ev_sales_ratio, short_pct, rsi_val),
            'reasons':        reasons,
            'news':           news,
            'business_summary': _FV_SUMMARY_CACHE.get(t, ''),
            # Technical Analysis
            'tech_signal':    ta_data.get('tech_signal', ''),
            'tech_score':     ta_data.get('tech_score', None),
            'tech_detail':    ta_data.get('tech_detail', ''),
            'tech_timing':    ta_data.get('tech_timing', ''),
            'tech_timing_up':       ta_data.get('tech_timing_up', ''),
            'tech_timing_down':     ta_data.get('tech_timing_down', ''),
            'tech_timing_up_desc':  ta_data.get('tech_timing_up_desc', ''),
            'tech_timing_down_desc': ta_data.get('tech_timing_down_desc', ''),
            'tech_timing_up_conf':  ta_data.get('tech_timing_up_conf', ''),
            'tech_timing_down_conf': ta_data.get('tech_timing_down_conf', ''),
            'tech_support':   ta_data.get('tech_support', None),
            'tech_resistance': ta_data.get('tech_resistance', None),
            'day_high':        ta_data.get('day_high', None),
            'day_low':         ta_data.get('day_low', None),
            'tech_patterns':        ta_data.get('tech_patterns') or '',
            'tech_patterns_detail': ta_data.get('tech_patterns_detail') or [],
            'tech_indicators':      ta_data.get('tech_indicators') or {},
            # Short Squeeze
            'squeeze_stage':   ta_data.get('squeeze_stage') or 'none',
            'squeeze_score':   ta_data.get('squeeze_score') or 0,
            'squeeze_signals': ta_data.get('squeeze_signals') or [],
        })

    # Enrich with full squeeze analysis (Short Float + DTC + intraday stage)
    try:
        from app.services.gemini_brain import score_short_squeeze_full as _score_squeeze
        for s in stocks:
            sq = _score_squeeze(s)
            s['squeeze_total_score'] = sq.get('squeeze_total_score', 0)
            s['squeeze_stage']       = sq.get('squeeze_stage', s.get('squeeze_stage', 'none'))
            s['squeeze_label']       = sq.get('squeeze_label', '')
            s['squeeze_emoji']       = sq.get('squeeze_emoji', '')
            s['squeeze_entry']       = sq.get('squeeze_entry', '')
            s['squeeze_signals']     = sq.get('squeeze_signals', s.get('squeeze_signals', []))
            s['float_rotation']      = sq.get('float_rotation')
            s['squeeze_catalyst']    = sq.get('squeeze_catalyst', '')
            s['squeeze_has_catalyst']= sq.get('squeeze_has_catalyst', False)
            s['squeeze_above_vwap']  = sq.get('squeeze_above_vwap', False)
            s['squeeze_near_hod']    = sq.get('squeeze_near_hod', False)
            s['squeeze_above_resistance'] = sq.get('squeeze_above_resistance', False)
            s['squeeze_breakout_label']   = sq.get('squeeze_breakout_label', '')
    except Exception:
        pass

    out = {
        'stocks':       stocks,
        'count':        len(stocks),
        'filters':      filters,
        'session':      _get_market_session(),
        'generated_at': datetime.now().isoformat(),
    }
    _FV_TABLE_CACHE = {'data': out, 'filters': filters, 'cache_key': cache_key}
    _FV_TABLE_CACHE_TIME = now
    return out


# ═══════════════════════════════════════════════════════════════════════════════
#  Smart Portfolio + Alerts endpoints
# ═══════════════════════════════════════════════════════════════════════════════

from app.services.smart_portfolio import smart_portfolio
from app.services.alerts_service import send_signal_alert, send_telegram, get_signal_log
from app.services.gemini_brain import get_ai_decision, post_mortem, _load_strategy, detect_market_regime, evaluate_exits, _load_regime, _safe_float


def _default_smart_portfolio_stats():
    """תשובת ברירת מחדל כש־Smart Portfolio לא זמין (למשל בענן בלי אחסון נתונים)."""
    return {
        'equity': 3000.0,
        'cash': 3000.0,
        'positions': {},
        'total_pnl': 0,
        'total_pnl_pct': 0,
        'daily_pnl': 0,
        'total_trades': 0,
        'winning_trades': 0,
        'peak_equity': 3000.0,
        'note': 'דמו — נתונים מתאפסים בענן',
    }


@router.get("/smart-portfolio/status")
async def smart_portfolio_status():
    """Current smart portfolio state, positions, equity curve."""
    try:
        live = {}
        for ticker in smart_portfolio.positions:
            if ticker in _LIVE_PRICES_CACHE:
                live[ticker] = _LIVE_PRICES_CACHE[ticker].get('price', 0)
            elif ticker in _FV_FUND_CACHE:
                p = _parse_fv_num(_FV_FUND_CACHE[ticker].get('price', ''))
                if p:
                    live[ticker] = p

        stats = smart_portfolio.get_stats(live)

        # Enrich positions with current_price + unrealized P&L so the Telegram bot
        # and frontend get accurate per-position data from a single endpoint.
        enriched_pos = {}
        for ticker, pos in stats.get('positions', {}).items():
            entry = pos.get('entry_price', 0)
            current = live.get(ticker, entry)
            side = pos.get('side', 'long')
            qty = pos.get('qty', 1)
            if entry > 0:
                if side == 'long':
                    upnl_pct = (current - entry) / entry * 100
                    upnl = (current - entry) * qty
                else:
                    upnl_pct = (entry - current) / entry * 100
                    upnl = (entry - current) * qty
            else:
                upnl_pct = upnl = 0.0
            enriched_pos[ticker] = {
                **pos,
                'current_price': round(current, 4),
                'has_live_price': ticker in live,
                'unrealized_pnl': round(upnl, 2),
                'unrealized_pnl_pct': round(upnl_pct, 2),
            }

        stats['positions'] = enriched_pos
        return stats
    except Exception as e:
        return _default_smart_portfolio_stats()


@router.get("/smart-portfolio/trades")
async def smart_portfolio_trades():
    """Trade history."""
    return smart_portfolio.get_trade_history()


@router.post("/smart-portfolio/think")
async def smart_portfolio_think():
    """
    Trigger the AI brain to analyze current market and make a decision.
    Can be called periodically (every 5 minutes) or on-demand.
    """
    cached = _FV_TABLE_CACHE.get('data', {})
    stocks = cached.get('stocks', [])
    if not stocks:
        return {'decision': None, 'error': 'No stock data available'}

    live_prices = {}
    for s in stocks:
        t = s.get('ticker')
        if t in _LIVE_PRICES_CACHE:
            live_prices[t] = _LIVE_PRICES_CACHE[t].get('price', s.get('price', 0))
        else:
            live_prices[t] = s.get('price', 0)

    stock_data_map = {s.get('ticker'): s for s in stocks if s.get('ticker')}
    closed = smart_portfolio.check_stops(live_prices, stock_data_map)
    for trade in closed:
        await send_signal_alert({
            'action': 'CLOSED', 'ticker': trade['ticker'],
            'price': trade['exit_price'], 'confidence': 100,
            'reason': trade['exit_reason'],
            'stop_loss': 0, 'target': 0,
        })
        await post_mortem(trade, _load_strategy())

    # Smart exit suggestions — close positions the brain recommends exiting
    regime = detect_market_regime(stocks)
    exit_suggestions = evaluate_exits(smart_portfolio.positions, stocks, live_prices, regime)
    for suggestion in exit_suggestions:
        if suggestion.get('urgency') == 'high' and suggestion.get('action') == 'close':
            ticker = suggestion['ticker']
            if ticker in smart_portfolio.positions:
                price = live_prices.get(ticker, 0)
                if price:
                    r = smart_portfolio.close_position(ticker, price, suggestion['reason'])
                    if r.get('success'):
                        closed.append(r['trade'])
                        await send_signal_alert({
                            'action': 'SMART_EXIT', 'ticker': ticker,
                            'price': price, 'confidence': 90,
                            'reason': suggestion['reason'],
                            'stop_loss': 0, 'target': 0,
                        })
                        await post_mortem(r['trade'], _load_strategy())

    portfolio_state = smart_portfolio.get_stats(live_prices)
    history = smart_portfolio.get_trade_history()

    decision = await get_ai_decision(stocks, portfolio_state, history)
    if not decision:
        return {'decision': None, 'error': 'AI did not return a decision'}

    result = {'decision': decision, 'executed': False, 'closed_trades': closed}

    if decision.get('action') in ('BUY', 'SHORT') and decision.get('confidence', 0) >= 60:
        ticker = decision.get('ticker', '').upper()
        if not ticker or ticker in smart_portfolio.positions:
            return result

        if not smart_portfolio.can_open_position(live_prices):
            result['error'] = 'Daily loss limit reached'
            return result

        price = live_prices.get(ticker, 0)
        if not price:
            return result

        equity = smart_portfolio.get_total_equity(live_prices)
        position_pct = min(decision.get('position_pct', 10), 20) / 100
        qty = max(1, int((equity * position_pct) / price))
        sl_pct = decision.get('stop_loss_pct', 5) / 100
        tgt_pct = decision.get('target_pct', 10) / 100

        if decision['action'] == 'BUY':
            stop = round(price * (1 - sl_pct), 2)
            target = round(price * (1 + tgt_pct), 2)
        else:
            stop = round(price * (1 + sl_pct), 2)
            target = round(price * (1 - tgt_pct), 2)

        trade_result = smart_portfolio.open_position(
            ticker, 'long' if decision['action'] == 'BUY' else 'short',
            price, qty, stop, target, decision.get('reason', '')
        )
        result['executed'] = trade_result.get('success', False)
        result['trade'] = trade_result

        if trade_result.get('success'):
            await send_signal_alert({
                'action': decision['action'], 'ticker': ticker,
                'price': price, 'confidence': decision.get('confidence', 0),
                'reason': decision.get('reason', ''),
                'analysis': decision.get('analysis', ''),
                'engine': decision.get('engine', ''),
                'stop_loss': stop, 'target': target,
            })

    smart_portfolio.record_equity(live_prices)
    return result


@router.post("/smart-portfolio/reset")
async def smart_portfolio_reset():
    """Reset the demo portfolio to initial state."""
    smart_portfolio.reset()
    return {'success': True, 'message': 'Portfolio reset to $3,000'}


@router.get("/smart-portfolio/export")
async def smart_portfolio_export():
    """Export portfolio state (for backup or sync to Render)."""
    return smart_portfolio.export_state()


@router.post("/smart-portfolio/import")
async def smart_portfolio_import(payload: dict):
    """Import portfolio state (e.g. from localhost to sync to Render)."""
    smart_portfolio.import_state(payload)
    return {'success': True, 'message': 'Portfolio imported'}


@router.get("/smart-portfolio/regime")
async def get_market_regime():
    """Get current market regime analysis."""
    cached = _FV_TABLE_CACHE.get('data', {})
    stocks = cached.get('stocks', [])
    if stocks:
        return detect_market_regime(stocks)
    return _load_regime()


@router.get("/alerts/log")
async def alerts_log():
    """Recent signal alerts log."""
    return get_signal_log()


@router.post("/alerts/test-telegram")
async def test_telegram():
    """Send a test message to Telegram."""
    ok = await send_telegram("🧪 <b>Test</b> — Stock Scanner connected!")
    return {'success': ok}
