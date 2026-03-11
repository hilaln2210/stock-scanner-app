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

    # Smart Portfolio AI Brain — runs every 5 minutes during market hours
    async def _smart_portfolio_tick():
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
    print("Smart Portfolio Brain: scheduled every 5 minutes")

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
