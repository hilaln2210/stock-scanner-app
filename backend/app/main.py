import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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

    print(f"Starting scheduler (interval: {settings.scrape_interval_minutes} minutes)...")
    scheduler.add_job(
        scheduled_scrape,
        "interval",
        minutes=settings.scrape_interval_minutes,
        id="scrape_job",
    )
    scheduler.start()

    # Run initial scrape in background (don't block startup)
    print("Scheduling initial scrape (running in background)...")
    import asyncio
    asyncio.create_task(scheduled_scrape())

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

    yield

    # Shutdown
    print("Shutting down scheduler...")
    scheduler.shutdown()


# Create FastAPI app
app = FastAPI(
    title="Stock Scanner API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api")

# Serve frontend static files in production
if FRONTEND_DIR.exists():
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="static-assets")

    # Serve other static files (manifest, icons, etc.)
    @app.get("/manifest.json")
    async def serve_manifest():
        manifest_path = FRONTEND_DIR / "manifest.json"
        if manifest_path.exists():
            return FileResponse(str(manifest_path))
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
        # Don't serve index.html for API routes or docs
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
