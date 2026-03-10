"""
REST API for the arbitrage scanner (paper trading only).
Serves the frontend and exposes scan + simulator endpoints.
Background thread: סורק פולימרקט כל X שניות, נכנס לארביטראז' ומציג בהיסטוריה.
"""

import logging
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import Config
from .scanner import Scanner
from .simulator import PaperTradingSimulator
from . import polymarket

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Arbitrage Scanner API",
    description="Prediction-market arbitrage scanner – paper trading, educational only.",
    version="1.0",
)

# Single instance per process (in-memory state)
_config = Config()
_scanner = Scanner(_config)
_simulator = PaperTradingSimulator(_config)

# Background scan state (for UI)
_last_scan_utc: datetime | None = None
_last_opportunities_count: int = 0
_last_opportunities: list = []  # הזדמנויות מהסריקה האחרונה (ברקע או ידנית) – להצגה בזמן אמת
_background_running: bool = False

# --- Pydantic schemas for API ---


class OpportunityOut(BaseModel):
    market_id: str
    market_type: str
    question: str
    expected_profit_pct: float
    total_cost: float
    liquidity: float
    source: str = "polymarket"


class MarketOut(BaseModel):
    """Single market (for display); may or may not be an opportunity."""
    market_id: str
    question: str
    yes_price: float
    no_price: float
    total_price: float
    liquidity: float
    is_arbitrage: bool
    expected_profit_pct: float
    source: str = "polymarket"


class EntryOut(BaseModel):
    market_id: str
    question: str
    capital_used: float
    expected_profit_pct: float
    entry_date: str


class ExitOut(BaseModel):
    market_id: str
    capital_used: float
    realized_pnl: float
    realized_pnl_pct: float
    exit_date: str
    fee_estimate: float = 0.0  # עמלות משוערות (אופציונלי)


class PositionOut(BaseModel):
    market_id: str
    capital_used: float
    entry_date: str
    expected_profit_pct: float


class SimulatorOut(BaseModel):
    initial_balance: float
    balance: float
    total_pnl: float
    total_pnl_pct: float
    total_realized_pnl: float
    entries: list[EntryOut]
    exits: list[ExitOut]
    open_positions: list[PositionOut]


class SimulateIn(BaseModel):
    max_entries: int = 3


def _opportunity_to_out(o) -> OpportunityOut:
    src = getattr(o.raw_market, "source", "mock")
    return OpportunityOut(
        market_id=o.market_id,
        market_type=o.market_type.value,
        question=o.question,
        expected_profit_pct=round(o.expected_profit_pct, 2),
        total_cost=round(o.total_cost, 4),
        liquidity=round(o.liquidity, 2),
        source=src,
    )


def _entry_to_out(e) -> EntryOut:
    return EntryOut(
        market_id=e.market_id,
        question=e.question,
        capital_used=round(e.capital_used, 2),
        expected_profit_pct=round(e.expected_profit_pct, 2),
        entry_date=e.entry_date.isoformat(),
    )


def _exit_to_out(x) -> ExitOut:
    return ExitOut(
        market_id=x.market_id,
        capital_used=round(x.capital_used, 2),
        realized_pnl=round(x.realized_pnl, 2),
        realized_pnl_pct=round(x.realized_pnl_pct, 2),
        exit_date=x.exit_date.isoformat(),
        fee_estimate=round(getattr(x, "fee_estimate", 0.0), 2),
    )


def _position_to_out(p) -> PositionOut:
    return PositionOut(
        market_id=p.market_id,
        capital_used=round(p.capital_used, 2),
        entry_date=p.entry_date.isoformat(),
        expected_profit_pct=round(p.expected_profit_pct, 2),
    )


# --- Routes ---


def _get_binary_markets(source: str | None, fallback_on_error: bool = True):
    """Return list of BinaryMarket. Supports polymarket, kalshi, manifold, all."""
    from . import kalshi, manifold
    source = (source or _config.data_source or "").strip().lower()
    if source == "all":
        out = []
        try:
            out.extend(polymarket.fetch_binary_markets(_config))
        except Exception as e:
            logger.warning("Polymarket fetch failed: %s", e)
        try:
            out.extend(kalshi.fetch_binary_markets(_config))
        except Exception as e:
            logger.warning("Kalshi fetch failed: %s", e)
        try:
            out.extend(manifold.fetch_binary_markets(500))
        except Exception as e:
            logger.warning("Manifold fetch failed: %s", e)
        return out
    if source == "polymarket":
        try:
            return polymarket.fetch_binary_markets(_config)
        except Exception as e:
            logger.warning("Polymarket fetch failed (%s), falling back to mock", e)
            if fallback_on_error:
                from .utils import load_binary_markets
                path = _config.binary_markets_path()
                if path.exists():
                    return load_binary_markets(path, source="mock")
            raise
    if source == "kalshi":
        return kalshi.fetch_binary_markets(_config)
    if source == "manifold":
        return manifold.fetch_binary_markets(500)
    from .utils import load_binary_markets
    path = _config.binary_markets_path()
    if path.exists():
        return load_binary_markets(path, source="mock")
    return []


@app.get("/api/markets")
def api_markets(source: str | None = None):
    """Return all binary markets (real Polymarket or mock). Falls back to mock if Polymarket fails."""
    try:
        markets = _get_binary_markets(source)
    except Exception as e:
        logger.exception("Markets fetch failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail={
                "message": "לא ניתן לטעון שווקים (Polymarket לא זמין)",
                "error": str(e),
            },
        )
    return [
        MarketOut(
            market_id=m.market_id,
            question=m.question,
            yes_price=round(m.yes_price, 4),
            no_price=round(m.no_price, 4),
            total_price=round(m.total_price(), 4),
            liquidity=round(m.liquidity, 2),
            is_arbitrage=m.is_arbitrage(),
            expected_profit_pct=round(m.locked_profit_pct(), 2),
            source=getattr(m, "source", "polymarket"),
        )
        for m in markets
    ]


@app.get("/api/scan", response_model=list[OpportunityOut])
def api_scan(source: str | None = None) -> list[OpportunityOut]:
    """Run scanner and return detected opportunities. Falls back to mock if Polymarket fails."""
    src = source or _config.data_source
    try:
        opportunities = _scanner.run(data_source=src)
    except Exception as e:
        logger.warning("Scan failed with source=%s (%s), trying mock", src, e)
        if (src or "").strip().lower() == "polymarket":
            try:
                opportunities = _scanner.run(data_source="mock")
            except Exception as e2:
                logger.exception("Scan mock fallback failed: %s", e2)
                raise HTTPException(
                    status_code=503,
                    detail={"message": "סריקה נכשלה", "error": str(e2)},
                )
        else:
            raise HTTPException(
                status_code=503,
                detail={"message": "סריקה נכשלה", "error": str(e)},
            )
    out = [_opportunity_to_out(o) for o in opportunities]
    global _last_opportunities, _last_opportunities_count, _last_scan_utc
    _last_opportunities = out
    _last_opportunities_count = len(out)
    _last_scan_utc = datetime.now(timezone.utc)
    return out


@app.get("/api/last-opportunities", response_model=list[OpportunityOut])
def api_last_opportunities() -> list[OpportunityOut]:
    """הזדמנויות מהסריקה האחרונה (סריקה אוטומטית או ידנית) – להצגה בזמן אמת."""
    return _last_opportunities


@app.get("/api/simulator", response_model=SimulatorOut)
def api_simulator() -> SimulatorOut:
    """Return current paper-trading simulator state."""
    return SimulatorOut(
        initial_balance=round(_simulator.initial_balance, 2),
        balance=round(_simulator.balance, 2),
        total_pnl=round(_simulator.total_pnl(), 2),
        total_pnl_pct=round(_simulator.total_pnl_pct(), 2),
        total_realized_pnl=round(_simulator.total_realized_pnl(), 2),
        entries=[_entry_to_out(e) for e in _simulator.entries],
        exits=[_exit_to_out(x) for x in _simulator.exits],
        open_positions=[_position_to_out(p) for p in _simulator.open_positions],
    )


@app.post("/api/simulate", response_model=SimulatorOut)
def api_simulate(body: SimulateIn = SimulateIn()) -> SimulatorOut:
    """Run scan, enter up to max_entries opportunities, close all; return new state."""
    max_entries = body.max_entries
    today = date.today()
    source = getattr(_config, "background_scan_source", "all") or "all"
    opportunities = _scanner.run(data_source=source)
    if not opportunities and source == "all":
        try:
            opportunities = _scanner.run(data_source="mock")
        except Exception:
            pass
    for o in opportunities[:max_entries]:
        ok, msg = _simulator.try_enter(o, as_of_date=today)
        if not ok:
            logger.warning("Skip entry %s: %s", o.market_id, msg)
    for pos in list(_simulator.open_positions):
        _simulator.close_position(pos.market_id, as_of_date=today)
    return api_simulator()


@app.post("/api/simulator/reset", response_model=SimulatorOut)
def api_simulator_reset() -> SimulatorOut:
    """Reset simulator to initial balance and clear positions."""
    _simulator.reset()
    return api_simulator()


# --- Background: סריקה רצופה + כניסה אוטומטית לארביטראז' ---

def _background_scan_loop() -> None:
    """כל N שניות: סרוק (פולימרקט), אם יש הזדמנויות – היכנס וסגור, יופיע בהיסטוריה."""
    global _last_scan_utc, _last_opportunities_count, _last_opportunities, _background_running
    import os
    interval = getattr(_config, "background_scan_interval_seconds", 90) or 90
    source = (os.environ.get("ARB_BACKGROUND_SOURCE") or getattr(_config, "background_scan_source", "polymarket") or "polymarket").strip().lower()
    max_trades = getattr(_config, "background_max_trades_per_cycle", 2) or 2
    _background_running = True
    logger.info("Background scanner started: every %ds, source=%s, max_trades=%d", interval, source, max_trades)
    first_delay = min(5, interval // 2)  # סריקה ראשונה אחרי 5 שניות
    time.sleep(first_delay)
    while _background_running:
        try:
            if not _background_running:
                break
            opportunities = _scanner.run(data_source=source)
            _last_scan_utc = datetime.now(timezone.utc)
            _last_opportunities_count = len(opportunities)
            _last_opportunities = [_opportunity_to_out(o) for o in opportunities]
            for o in opportunities[:max_trades]:
                ok, msg = _simulator.try_enter(o, as_of_date=date.today())
                if ok:
                    _simulator.close_position(o.market_id, as_of_date=date.today())
                    logger.info("Background: entered and closed %s", o.market_id)
                elif msg:
                    logger.debug("Background skip %s: %s", o.market_id, msg)
            for pos in list(_simulator.open_positions):
                _simulator.close_position(pos.market_id, as_of_date=date.today())
        except Exception as e:
            logger.exception("Background scan error: %s", e)
        if _background_running:
            time.sleep(interval)
    _background_running = False


_background_thread: threading.Thread | None = None


@app.on_event("startup")
def _start_background_scanner() -> None:
    global _background_thread
    if _background_thread is None or not _background_thread.is_alive():
        _background_thread = threading.Thread(target=_background_scan_loop, daemon=True)
        _background_thread.start()


class StatusOut(BaseModel):
    last_scan_iso: str | None
    last_opportunities_count: int
    background_running: bool


@app.get("/api/status", response_model=StatusOut)
def api_status() -> StatusOut:
    """מצב סריקה ברקע – מתי נסרק לאחרונה וכמה הזדמנויות."""
    return StatusOut(
        last_scan_iso=_last_scan_utc.isoformat() if _last_scan_utc else None,
        last_opportunities_count=_last_opportunities_count,
        background_running=_background_running,
    )


# Serve frontend
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")
