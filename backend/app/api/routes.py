import asyncio
import json as _json
from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import StreamingResponse
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
from app.services.briefing_service import BriefingService, fetch_single_ticker_briefing as _fetch_single_briefing
from app.services.technical_signals import TechnicalSignalsService
from app.services.daily_analysis import DailyAnalysisService
from app.services import portfolio_service
from app.config import settings
from app.services.ai_context import build_trading_context, SYSTEM_PROMPT_TEMPLATE
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
tech_signals_service = TechnicalSignalsService()
daily_analysis_service = DailyAnalysisService()

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
    """Return demo portfolio with live prices and P&L."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, portfolio_service.get_portfolio_with_live_prices)
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


# ── AI Assistant ────────────────────────────────────────────────────────────

@router.post("/ai/chat")
async def ai_chat(body: dict = Body(...)):
    """
    Streaming AI chat endpoint. Accepts {messages: [{role, content}]} and
    injects real-time dashboard context into every conversation.
    Returns SSE stream: data: {"token": "..."}\n\n  or  data: {"done": true}\n\n
    """
    if not settings.anthropic_api_key:
        async def _no_key():
            yield "data: " + _json.dumps({"error": "ANTHROPIC_API_KEY לא מוגדר ב-.env"}) + "\n\n"
        return StreamingResponse(_no_key(), media_type="text/event-stream")

    messages = body.get("messages", [])
    if not messages:
        async def _empty():
            yield "data: " + _json.dumps({"error": "no messages"}) + "\n\n"
        return StreamingResponse(_empty(), media_type="text/event-stream")

    # Build context from live dashboard data
    context = build_trading_context(_response_cache)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=context)

    async def _stream():
        try:
            import anthropic as _anthropic
            client = _anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            async with client.messages.stream(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=system_prompt,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield "data: " + _json.dumps({"token": text}) + "\n\n"
            yield "data: " + _json.dumps({"done": True}) + "\n\n"
        except Exception as e:
            yield "data: " + _json.dumps({"error": str(e)}) + "\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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


# ── Finviz Fundamental Table Screener ─────────────────────────────────────────

_FV_TABLE_CACHE: dict = {}
_FV_TABLE_CACHE_TIME: float = 0.0
_FV_TABLE_CACHE_TTL: int = 25       # price/change: 25 s (refresh before 30 s frontend)
_FV_FUND_CACHE: dict = {}           # {ticker: fund_data}
_FV_FUND_CACHE_TIME: float = 0.0
_FV_FUND_CACHE_TTL: int = 1800      # fundamentals: 30 min
_FV_NEWS_CACHE: dict = {}           # {ticker: [news_items]}
_FV_NEWS_CACHE_TIME: dict = {}      # {ticker: timestamp}
_FV_NEWS_CACHE_TTL: int = 300       # news: 5 min per ticker
_FV_INTRA_CACHE: dict = {}          # {ticker: {chg_5m, chg_30m}}
_FV_INTRA_CACHE_TIME: dict = {}     # {ticker: timestamp}
_FV_INTRA_CACHE_TTL: int = 25       # intraday: same as price refresh
_FV_SUMMARY_CACHE: dict = {}        # {ticker: summary_str}
_FV_SUMMARY_CACHE_TIME: dict = {}   # {ticker: timestamp}
_FV_SUMMARY_CACHE_TTL: int = 3600   # business description: 1 hour

_FV_DEFAULT_FILTERS = (
    "cap_midover,sh_avgvol_o2000,sh_curvol_o0,"
    "sh_instown_o10,sh_short_o5,ta_changeopen_u4,ta_rsi_nos50"
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
    Real-Time Health Tags per spec:
      ✅ profitable  — Income > 0
      ❌ loss        — Income < 0
      ⚠️ high_debt   — EV/MC ≥ 1.2
      💰 cash_rich   — EV/MC ≤ 0.9
      🔥 high_growth — Revenue Q/Q ≥ 20% or EPS Y% ≥ 20%
      📉 high_short  — Short Float > 15%
    """
    tags = []

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

    eps_y    = _parse_fv_num(fund.get('eps_this_y', ''))
    sales_qq = _parse_fv_num(fund.get('sales_qq', ''))
    sales_5y = _parse_fv_num(fund.get('sales_past_5y', ''))
    if (eps_y and eps_y >= 20) or (sales_qq and sales_qq >= 20) or (sales_5y and sales_5y >= 15):
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


def _health_score(tags: list) -> int:
    """
    Financial Health Score 0–100 (base 50, capped).
      +30  profitable   +20  cash_rich   +20  high_growth
      −25  loss         −20  high_debt
    Ranges: 80–100 🟢  60–79 🟡  40–59 🟠  0–39 🔴
    """
    score = 50
    if 'profitable'  in tags: score += 30
    if 'cash_rich'   in tags: score += 20
    if 'high_growth' in tags: score += 20
    if 'loss'        in tags: score -= 25
    if 'high_debt'   in tags: score -= 20
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
    """
    import yfinance as _yf
    from concurrent.futures import ThreadPoolExecutor as _TPE2

    def _inner():
        # period='2d' gives yesterday's regular-hours close + today's extended bars
        return _yf.Ticker(ticker).history(period='2d', interval='5m', prePost=True, timeout=6)

    try:
        with _TPE2(max_workers=1) as pool:
            hist = pool.submit(_inner).result(timeout=10)
        if hist is None or len(hist) < 2:
            return {}
        closes = hist['Close'].dropna()
        if len(closes) < 2:
            return {}

        cur   = float(closes.iloc[-1])
        result = {'extended_price': round(cur, 4)}

        # Intraday momentum (works in extended hours too)
        ago5  = float(closes.iloc[-2]) if len(closes) >= 2 else None
        ago30 = float(closes.iloc[-7]) if len(closes) >= 7 else (
                float(closes.iloc[0])  if len(closes) >= 2 else None)
        if ago5  and ago5  > 0: result['chg_5m']  = round((cur - ago5)  / ago5  * 100, 2)
        if ago30 and ago30 > 0: result['chg_30m'] = round((cur - ago30) / ago30 * 100, 2)

        # Extended change vs last regular-session close (9:30–16:00 ET)
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
                if prev_close > 0:
                    result['prev_close'] = round(prev_close, 4)
                    result['extended_chg_pct'] = round((cur - prev_close) / prev_close * 100, 2)
        except Exception:
            pass

        return result
    except Exception:
        return {}


def _fetch_ticker_news_sync(ticker: str) -> list:
    """
    Fetch yfinance news for a ticker with a hard 3-second timeout.
    Returns list of {title, publisher, link, published} dicts.
    """
    import yfinance as _yf
    from concurrent.futures import ThreadPoolExecutor as _TPE2, TimeoutError as _TE

    def _inner():
        return _yf.Ticker(ticker).news or []

    try:
        with _TPE2(max_workers=1) as pool:
            raw = pool.submit(_inner).result(timeout=3)
        return [
            {
                'title':     n.get('title', ''),
                'publisher': n.get('publisher', ''),
                'link':      n.get('link', ''),
                'published': n.get('providerPublishTime', 0),
            }
            for n in raw[:5]
        ]
    except Exception:
        return []


def _classify_move_reason(fund: dict, news: list, change_pct) -> list:
    """
    Derive reasons why the stock is moving today.
    Returns list of {type, label, confidence} — at most 3 reasons.
    """
    reasons = []
    chg = float(change_pct) if change_pct else 0

    # 1. Earnings date matches today / yesterday
    earnings_date_str = fund.get('earnings_date', '') or ''
    today     = datetime.now()
    yesterday = today - timedelta(days=1)
    for d in [today, yesterday]:
        if d.strftime('%b %d') in earnings_date_str or d.strftime('%-d %b') in earnings_date_str:
            reasons.append({'type': 'earnings', 'label': '📊 דוח רבעוני', 'confidence': 'high'})
            break

    # 2. Large gap (pre-market catalyst)
    gap = _parse_fv_num(fund.get('gap_pct', ''))
    if gap and abs(gap) >= 5:
        sign = '+' if gap > 0 else ''
        reasons.append({
            'type': 'gap',
            'label': f'{"📈" if gap > 0 else "📉"} Gap {sign}{gap:.1f}%',
            'confidence': 'high',
        })

    # 3. Classify top news headline
    if news:
        title = news[0].get('title', '').lower()
        if any(w in title for w in ['beat', 'earn', 'eps', 'revenue', 'q4', 'q3', 'q2', 'q1',
                                     'profit', 'quarter', 'results', 'record sales', 'record revenue']):
            if not any(r['type'] == 'earnings' for r in reasons):
                reasons.append({'type': 'earnings', 'label': '📊 תוצאות', 'confidence': 'high'})
        elif any(w in title for w in ['upgrade', 'overweight', 'outperform', 'buy', 'strong buy',
                                       'target raised', 'price target', 'initiates']):
            reasons.append({'type': 'upgrade', 'label': '⬆️ שדרוג אנליסט', 'confidence': 'high'})
        elif any(w in title for w in ['downgrade', 'underweight', 'underperform', 'sell',
                                       'target cut', 'target lowered', 'reduces']):
            reasons.append({'type': 'downgrade', 'label': '⬇️ הורדת דירוג', 'confidence': 'high'})
        elif any(w in title for w in ['fda', 'approval', 'approved', 'clearance',
                                       'phase 3', 'phase iii', 'nda', 'bla', 'pdufa']):
            reasons.append({'type': 'fda', 'label': '💊 FDA / רגולציה', 'confidence': 'high'})
        elif any(w in title for w in ['acqui', 'merger', 'buyout', 'takeover', 'deal',
                                       'agreement', 'transaction', 'purchase']):
            reasons.append({'type': 'ma', 'label': '🤝 מיזוג / רכישה', 'confidence': 'high'})
        elif any(w in title for w in ['guidance', 'outlook', 'forecast', 'raises guidance',
                                       'lowers guidance', 'reiterates', 'sees']):
            reasons.append({'type': 'guidance', 'label': '🔮 תחזית', 'confidence': 'medium'})
        elif any(w in title for w in ['contract', 'award', 'wins', 'partnership',
                                       'collaboration', 'selected', 'chosen']):
            reasons.append({'type': 'contract', 'label': '📝 חוזה / שותפות', 'confidence': 'medium'})
        elif any(w in title for w in ['short', 'fraud', 'investigation', 'lawsuit', 'sec',
                                       'subpoena', 'recall', 'warning']):
            reasons.append({'type': 'risk', 'label': '⚠️ חקירה / סיכון', 'confidence': 'medium'})
        elif any(w in title for w in ['offering', 'dilut', 'shares', 'secondary', 'atm']):
            reasons.append({'type': 'dilution', 'label': '📉 הנפקת מניות', 'confidence': 'medium'})

    # 4. Fallback: generic technical move
    if not reasons and abs(chg) > 0:
        label = f'{"📈" if chg > 0 else "📉"} תנועה טכנית ({chg:+.1f}%)'
        reasons.append({'type': 'technical', 'label': label, 'confidence': 'low'})

    return reasons[:3]


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
                return summary[:dot + 1]
            return summary[:200]
        return ''
    except Exception:
        return ''


@router.get("/screener/finviz-table")
async def get_finviz_table(
    filters: str = Query(default=_FV_DEFAULT_FILTERS),
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

    # Serve from cache if still fresh and same filters
    if (
        _FV_TABLE_CACHE
        and _FV_TABLE_CACHE.get('filters') == filters
        and (now - _FV_TABLE_CACHE_TIME) < _FV_TABLE_CACHE_TTL
    ):
        return _FV_TABLE_CACHE['data']

    # ── 1. Scrape tickers + basic price data from Finviz screener ─────────────
    raw_stocks = await finviz_screener._scrape_screener(
        {'v': '111', 'f': filters, 'o': '-changeopen'},
        'finviz-table',
    )

    if not raw_stocks:
        return {'stocks': [], 'count': 0, 'filters': filters,
                'generated_at': datetime.now().isoformat()}

    tickers = [s['ticker'] for s in raw_stocks if s.get('ticker')]

    # ── 2. Fundamentals (30-min cache) ────────────────────────────────────────
    fund_stale = (now - _FV_FUND_CACHE_TIME) > _FV_FUND_CACHE_TTL
    fund_missing = tickers if fund_stale else [t for t in tickers if t not in _FV_FUND_CACHE]
    if fund_missing:
        new_funds = await finviz_fundamentals.get_fundamentals_batch(fund_missing)
        _FV_FUND_CACHE.update({k: v for k, v in new_funds.items() if v})
        _FV_FUND_CACHE_TIME = now

    # ── 3. News (5-min per-ticker cache) ──────────────────────────────────────
    news_missing = [
        t for t in tickers
        if (now - _FV_NEWS_CACHE_TIME.get(t, 0)) > _FV_NEWS_CACHE_TTL
    ]
    if news_missing:
        loop = asyncio.get_running_loop()
        with _TPE(max_workers=4) as pool:
            news_futs = [
                loop.run_in_executor(pool, _fetch_ticker_news_sync, t)
                for t in news_missing
            ]
            news_results = await asyncio.gather(*news_futs, return_exceptions=True)
        for t, res in zip(news_missing, news_results):
            if isinstance(res, list):
                _FV_NEWS_CACHE[t] = res
                _FV_NEWS_CACHE_TIME[t] = now

    # ── 4. Intraday 5m/30m changes (25-s cache) ───────────────────────────────
    global _FV_INTRA_CACHE, _FV_INTRA_CACHE_TIME
    intra_missing = [
        t for t in tickers
        if (now - _FV_INTRA_CACHE_TIME.get(t, 0)) > _FV_INTRA_CACHE_TTL
    ]
    if intra_missing:
        loop = asyncio.get_running_loop()
        with _TPE(max_workers=4) as pool:
            intra_futs = [
                loop.run_in_executor(pool, _fetch_intraday_sync, t)
                for t in intra_missing
            ]
            intra_results = await asyncio.gather(*intra_futs, return_exceptions=True)
        for t, res in zip(intra_missing, intra_results):
            if isinstance(res, dict):
                _FV_INTRA_CACHE[t] = res
                _FV_INTRA_CACHE_TIME[t] = now

    # ── 5. Business summaries (1-hour cache) ──────────────────────────────────
    global _FV_SUMMARY_CACHE, _FV_SUMMARY_CACHE_TIME
    summary_missing = [
        t for t in tickers
        if t not in _FV_SUMMARY_CACHE
        or (now - _FV_SUMMARY_CACHE_TIME.get(t, 0)) > _FV_SUMMARY_CACHE_TTL
    ]
    if summary_missing:
        loop = asyncio.get_running_loop()
        with _TPE(max_workers=3) as pool:
            summ_futs = [
                loop.run_in_executor(pool, _fetch_summary_sync, t)
                for t in summary_missing
            ]
            summ_results = await asyncio.gather(*summ_futs, return_exceptions=True)
        for t, res in zip(summary_missing, summ_results):
            if isinstance(res, str):
                _FV_SUMMARY_CACHE[t] = res
                _FV_SUMMARY_CACHE_TIME[t] = now

    # ── 6. Merge, classify reasons, build response ────────────────────────────
    stocks = []
    for raw in raw_stocks:
        t     = raw.get('ticker', '')
        fund  = _FV_FUND_CACHE.get(t) or {}
        news  = _FV_NEWS_CACHE.get(t) or []
        intra = _FV_INTRA_CACHE.get(t) or {}
        price = raw.get('price') or _parse_fv_num(fund.get('price', '')) or 0
        mc    = _parse_fv_num(raw.get('market_cap_str', '') or fund.get('market_cap', ''))

        change_pct = raw.get('change_pct')
        reasons = _classify_move_reason(fund, news, change_pct)
        tags    = _stock_tags(fund, price)
        ev      = _compute_ev(fund)
        ev_mc_ratio = round(ev / mc, 3) if ev and mc and mc > 0 else None

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
            'inst_own':       fund.get('inst_own', ''),
            'insider_own':    fund.get('insider_own', ''),
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
            'chg_30m':           intra.get('chg_30m'),
            'extended_price':    intra.get('extended_price'),
            'extended_chg_pct':  intra.get('extended_chg_pct'),
            'prev_close':        intra.get('prev_close'),
            # Earnings status
            'eps_surpr':      fund.get('eps_surpr', ''),
            'eps_sales_surpr':fund.get('eps_sales_surpr', ''),
            'earnings_verdict': _earnings_verdict(fund),
            # Enrichments
            'tags':           tags,
            'health_score':   _health_score(tags),
            'ev_mc_ratio':    ev_mc_ratio,
            'reasons':        reasons,
            'news':           news,
            'business_summary': _FV_SUMMARY_CACHE.get(t, ''),
        })

    out = {
        'stocks':       stocks,
        'count':        len(stocks),
        'filters':      filters,
        'session':      _get_market_session(),
        'generated_at': datetime.now().isoformat(),
    }
    _FV_TABLE_CACHE = {'data': out, 'filters': filters}
    _FV_TABLE_CACHE_TIME = now
    return out
