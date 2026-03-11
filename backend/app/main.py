import os
import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

from app.database import init_db, AsyncSessionLocal
from app.api.routes import router
from app.services.ingestion import IngestionService
from app.services.normalization import NormalizationService
from app.services.signal_engine import SignalEngine
from app.config import settings

# Scheduler
scheduler = AsyncIOScheduler()

# Path to frontend build (for production serving)
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend" / "dist"


async def scheduled_scrape():
    """Scheduled task to scrape news and generate signals"""
    print(f"\n[{datetime.now()}] Starting scheduled scrape...")

    async with AsyncSessionLocal() as db:
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

            print(f"  Scraped: {len(results)}, Saved: {saved_count}, Signals: {signals_count}")

        except Exception as e:
            print(f"  Error during scrape: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    print("Initializing database...")
    await init_db()

    # Finviz Elite login — share cookie across screener + fundamentals
    import asyncio
    from app.api.routes import finviz_screener, finviz_fundamentals
    if settings.finviz_email and settings.finviz_password and not settings.finviz_cookie:
        import aiohttp
        try:
            async with aiohttp.ClientSession() as sess:
                cookie = await finviz_screener._login(sess)
                if cookie:
                    finviz_screener.cookie = cookie
                    finviz_fundamentals.cookie = cookie
                    print(f"Finviz Elite: logged in, cookie shared across services")
                else:
                    print("Finviz Elite: login returned no cookie")
        except Exception as e:
            print(f"Finviz Elite login failed: {e}")

    print(f"Starting scheduler (interval: {settings.scrape_interval_minutes} minutes)...")
    scheduler.add_job(
        scheduled_scrape,
        "interval",
        minutes=settings.scrape_interval_minutes,
        id="scrape_job",
    )
    scheduler.start()

    # Delay initial scrape to avoid Finviz rate limits on user's first request
    print("Scheduling initial scrape (delayed 60s to avoid rate limits)...")
    async def _delayed_scrape():
        await asyncio.sleep(60)
        await scheduled_scrape()
    asyncio.create_task(_delayed_scrape())

    # Smart Portfolio AI Brain — runs every 5 minutes during all trading sessions
    async def _smart_portfolio_tick():
        from datetime import datetime, timezone, timedelta
        et_offset = timedelta(hours=-4)
        now_et = datetime.now(timezone.utc) + et_offset
        is_weekday = now_et.weekday() < 5
        # Extended hours: 4:00 AM – 20:00 PM ET (pre-market through after-hours)
        total_min = now_et.hour * 60 + now_et.minute
        in_trading_hours = is_weekday and (4 * 60 <= total_min <= 20 * 60)
        if not in_trading_hours:
            return
        try:
            import httpx
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post("http://localhost:8000/api/smart-portfolio/think")
                data = r.json()
                d = data.get('decision', {})
                if d and d.get('action') != 'HOLD':
                    print(f"[Brain] {d.get('action')} {d.get('ticker')} (confidence: {d.get('confidence')}%)")
                else:
                    print(f"[Brain] HOLD — {d.get('reason', 'no decision') if d else 'no data'}")
        except Exception as e:
            print(f"[Brain] Error: {e}")

    scheduler.add_job(_smart_portfolio_tick, "interval", minutes=5, id="brain_job")

    # Arena — autonomous tick every 1 minute, all sessions (pre/regular/after)
    async def _arena_tick():
        from datetime import datetime, timezone, timedelta
        from app.services.strategy_arena import get_session_type
        import time as _t
        session = get_session_type()
        if session == "closed":
            return
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                # Refresh finviz-table cache if stale (>90s) — arena is self-sufficient
                from app.api.routes import _FV_TABLE_CACHE, _FV_TABLE_CACHE_TIME
                cache_age = _t.time() - _FV_TABLE_CACHE_TIME
                if cache_age > 90 or not _FV_TABLE_CACHE.get('data', {}).get('stocks'):
                    try:
                        await client.get("http://localhost:8000/api/screener/finviz-table",
                                         timeout=httpx.Timeout(90.0))
                    except Exception:
                        pass  # arena/think has its own fallbacks

                ra = await client.post("http://localhost:8000/api/smart-portfolio/arena/think",
                                       timeout=httpx.Timeout(60.0))
                lb = ra.json().get("leaderboard", [])
                if lb:
                    leader = lb[0]
                    print(f"[Arena:{session}] #{1} {leader['name']} "
                          f"${leader.get('equity', 1000):.0f} ({leader.get('pnl_pct', 0):+.2f}%)")
        except Exception as e:
            print(f"[Arena] tick error: {e}")

    scheduler.add_job(_arena_tick, "interval", seconds=30, id="arena_tick_job",
                      max_instances=1, coalesce=True)

    # Seasonal & Pattern cache refresh (heavy — runs separately every 2h/1h)
    async def _refresh_arena_aux_caches():
        """Refresh seasonal & pattern caches used by SeasonalityTrader / PatternTrader."""
        from app.services.strategy_arena import get_session_type
        if get_session_type() == "closed":
            return
        import httpx, time as _t
        from app.api.routes import (
            _ARENA_SEASONAL_TICKERS, _ARENA_SEASONAL_UPDATED,
            _ARENA_PATTERN_SIGNALS, _ARENA_PATTERN_UPDATED,
        )
        import app.api.routes as _routes
        now = _t.time()

        # Seasonal refresh every 2h
        if now - _ARENA_SEASONAL_UPDATED > 7200:
            try:
                today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
                async with httpx.AsyncClient() as c:
                    r = await c.get(
                        f"http://localhost:8000/api/seasonality?market=ndx100"
                        f"&start_date={today}&min_win_pct=70&years=10&days_min=5&days_max=30",
                        timeout=120
                    )
                    data = r.json()
                if isinstance(data, dict) and not data.get("loading"):
                    pats = data.get("patterns", [])
                    if pats:
                        _routes._ARENA_SEASONAL_TICKERS = {
                            p["ticker"]: p.get("win_ratio", 0)
                            for p in pats if p.get("win_ratio", 0) >= 70
                        }
                        _routes._ARENA_SEASONAL_UPDATED = _t.time()
                        print(f"[Arena:Seasonal] {len(_routes._ARENA_SEASONAL_TICKERS)} tickers: "
                              f"{list(_routes._ARENA_SEASONAL_TICKERS.keys())[:8]}")
            except Exception as e:
                print(f"[Arena:Seasonal] refresh error: {e}")

        # Pattern refresh every 1h
        if now - _ARENA_PATTERN_UPDATED > 3600:
            try:
                async with httpx.AsyncClient() as c:
                    r = await c.get(
                        "http://localhost:8000/api/pattern/scan?limit=20&days=45&interval=5m",
                        timeout=120
                    )
                    pdata = r.json()
                if isinstance(pdata, dict) and not pdata.get("loading"):
                    pat_map = {}
                    for st in pdata.get("stocks", []):
                        tk = st.get("ticker", "")
                        if not tk:
                            continue
                        best = max(
                            (s.get("win_rate", 0) for s in (st.get("signals") or [])
                             if s.get("direction") == "LONG" and s.get("win_rate", 0) >= 65),
                            default=0.0
                        )
                        if best >= 65:
                            pat_map[tk] = best
                    _routes._ARENA_PATTERN_SIGNALS = pat_map
                    _routes._ARENA_PATTERN_UPDATED = _t.time()
                    print(f"[Arena:Pattern] {len(pat_map)} signals: {list(pat_map.keys())[:8]}")
            except Exception as e:
                print(f"[Arena:Pattern] refresh error: {e}")

    scheduler.add_job(_refresh_arena_aux_caches, "interval", minutes=30, id="arena_aux_cache_job",
                      max_instances=1, coalesce=True)
    print("Smart Portfolio Brain: every 5min | Arena: autonomous every 30s | Seasonal/Pattern: every 30min")

    # Arena daily winner at 16:05 ET (Mon-Fri), weekly winner on Fridays
    async def _arena_eod_check():
        """Runs every 1 min — fires daily winner at 16:05, preview at 15:45."""
        from datetime import datetime, timezone, timedelta
        et_offset = timedelta(hours=-4)
        now_et = datetime.now(timezone.utc) + et_offset
        if now_et.weekday() >= 5:
            return
        hour, minute = now_et.hour, now_et.minute
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                # Preview alert: 15:45–15:49
                if hour == 15 and 45 <= minute < 50:
                    await client.post("http://localhost:8000/api/smart-portfolio/arena/preview-alert")
                # Daily winner: 16:05–16:09
                elif hour == 16 and 5 <= minute < 10:
                    await client.post("http://localhost:8000/api/smart-portfolio/arena/declare-daily-winner")
        except Exception as e:
            print(f"[Arena EOD] Error: {e}")

    scheduler.add_job(_arena_eod_check, "interval", minutes=1, id="arena_eod_job")
    print("Arena EOD: preview at 15:45, winner at 16:05 ET")

    # IB Auto-Reconnect — if arena trader is enabled and IB disconnected, reconnect automatically
    _ib_reconnect_failures = [0]  # consecutive failure counter

    async def _ib_auto_reconnect():
        from app.services.ib_service import ib_service
        from app.services.arena_ib_trader import arena_ib_trader
        if not arena_ib_trader.enabled:
            return
        if ib_service.is_connected():
            _ib_reconnect_failures[0] = 0
            return
        # Back off after repeated failures: skip if too many consecutive fails
        if _ib_reconnect_failures[0] >= 10:
            # Reset every 10 min (10 failures × 60s = 10min) to retry
            if _ib_reconnect_failures[0] % 10 == 0:
                print("[IB Reconnect] Resetting backoff, retrying...")
            else:
                return
        try:
            print("[IB Reconnect] Arena trader enabled but IB disconnected — reconnecting...")
            result = await ib_service.connect(host="127.0.0.1", port=4002, client_id=20)
            if result.get("connected"):
                _ib_reconnect_failures[0] = 0
                print(f"[IB Reconnect] ✓ Connected to {result.get('account', '?')}")
            else:
                _ib_reconnect_failures[0] += 1
                print(f"[IB Reconnect] Failed: {result.get('error', 'unknown')} "
                      f"(attempt {_ib_reconnect_failures[0]})")
        except Exception as e:
            _ib_reconnect_failures[0] += 1
            print(f"[IB Reconnect] Error: {e} (attempt {_ib_reconnect_failures[0]})")

    scheduler.add_job(_ib_auto_reconnect, "interval", seconds=60, id="ib_reconnect_job",
                      max_instances=1, coalesce=True)
    print("IB Auto-Reconnect: checks every 60s when arena trader is enabled")

    # Pre-warm briefing cache in background
    async def _prewarm_briefing():
        import httpx
        await asyncio.sleep(8)  # wait for server to fully start
        try:
            async with httpx.AsyncClient() as client:
                await client.get("http://127.0.0.1:8000/api/briefing/daily", timeout=60)
                print("Briefing cache pre-warmed.")
        except Exception as e:
            print(f"Briefing pre-warm failed: {e}")
    asyncio.create_task(_prewarm_briefing())

    # Keep-alive self-ping — prevents Render free tier from sleeping (pings every 14 min)
    async def _keep_alive():
        import httpx
        render_url = os.environ.get("RENDER_EXTERNAL_URL")
        if not render_url:
            return  # only run on Render
        await asyncio.sleep(30)  # wait for full startup
        while True:
            try:
                async with httpx.AsyncClient() as client:
                    await client.get(f"{render_url}/health", timeout=10)
            except Exception:
                pass
            await asyncio.sleep(14 * 60)  # every 14 minutes
    asyncio.create_task(_keep_alive())

    # Interactive Telegram Bot — listen for user messages (non-blocking; failures don't kill server)
    async def _run_bot_safe():
        try:
            from app.services.telegram_bot import start_telegram_bot
            await start_telegram_bot()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[TG Bot] Startup failed (server continues): {e}")
    asyncio.create_task(_run_bot_safe())

    # Pattern Auto-Trader — start background loop + enable state (no immediate scan on startup)
    from app.services.pattern_autotrader import start_background_loop as _start_autotrader, enable_no_scan as _enable_autotrader_fast
    _start_autotrader()
    _enable_autotrader_fast(amount=700, top_n=3)
    print("Pattern Auto-Trader: enabled — scan runs at 3:55 AM ET or on manual trigger")

    # Arena price cache — warm up in background so P&L shows immediately after restart
    async def _warm_arena_prices():
        await asyncio.sleep(15)  # let server finish startup first
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.get("http://localhost:8000/api/screener/finviz-table", timeout=90)
            print("[Arena] Startup price warm-up complete")
        except Exception as e:
            print(f"[Arena] Startup warm-up failed: {e}")
        # Also kick off seasonal/pattern cache refresh right away
        await asyncio.sleep(5)
        try:
            await _refresh_arena_aux_caches()
        except Exception as e:
            print(f"[Arena] Aux cache warmup failed: {e}")
    asyncio.create_task(_warm_arena_prices())

    yield

    # Shutdown
    print("Shutting down scheduler...")
    scheduler.shutdown()

    print("Cleanup complete.")


# Create FastAPI app
app = FastAPI(
    title="Stock Scanner API",
    version="1.0.0",
    lifespan=lifespan,
)

# GZip — compress all responses > 500 bytes (huge win for JSON payloads)
app.add_middleware(GZipMiddleware, minimum_size=500)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler — prevents 500 crashes from killing the server
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)[:200]},
    )

# Lightweight health check — responds before heavy init, keeps Render awake
@app.get("/health")
async def health():
    return {"status": "ok"}

# Include API routes
app.include_router(router, prefix="/api")

# Cache headers for API responses
@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response

# Serve frontend static files in production
if FRONTEND_DIR.exists():
    # Serve static assets (JS, CSS, images) — hashed filenames enable aggressive caching
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="static-assets")

    # Serve other static files (manifest, icons, etc.)
    @app.get("/manifest.json")
    async def serve_manifest():
        for name in ("manifest.webmanifest", "manifest.json"):
            p = FRONTEND_DIR / name
            if p.exists():
                return FileResponse(str(p))
        return {"error": "not found"}

    @app.get("/manifest.webmanifest")
    async def serve_manifest_webmanifest():
        p = FRONTEND_DIR / "manifest.webmanifest"
        if p.exists():
            return FileResponse(str(p))
        return {"error": "not found"}

    @app.get("/icon-{size}.png")
    async def serve_icon(size: str):
        icon_path = FRONTEND_DIR / f"icon-{size}.png"
        if icon_path.exists():
            return FileResponse(str(icon_path))
        return {"error": "not found"}

    # Catch-all: serve index.html for any non-API route (SPA routing)
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        # Don't serve index.html for API routes, docs, or PWA
        if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi"):
            return {"error": "not found"}
        # Try to serve the exact file first
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        # Otherwise serve index.html (SPA)
        return FileResponse(str(FRONTEND_DIR / "index.html"))
else:
    @app.get("/")
    async def root():
        return {
            "message": "Stock Scanner API",
            "version": "1.0.0",
            "docs": "/docs",
            "note": "Frontend not built. Run 'cd frontend && npm run build' to enable UI."
        }
