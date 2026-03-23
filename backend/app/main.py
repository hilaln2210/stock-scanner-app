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

    # Pre-warm sector briefing cache so first user request is fast
    async def _prewarm_sectors():
        await asyncio.sleep(5)
        try:
            from app.services.sector_briefing_service import get_sector_briefing
            await asyncio.wait_for(get_sector_briefing(), timeout=45)
            print('[Startup] Sector briefing cache warmed up')
        except Exception as e:
            print(f'[Startup] Sector pre-warm failed (non-critical): {e}')
    asyncio.create_task(_prewarm_sectors())

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

    # Disabled — smart portfolio tab hidden to save resources
    # scheduler.add_job(_smart_portfolio_tick, "interval", minutes=5, id="brain_job")

    # Arena — live tick every 10s: fresh Finviz scan every 20s + live prices every tick
    _arena_fv_last_refresh: list = [0.0]   # mutable container for closure

    async def _arena_tick():
        from app.services.strategy_arena import get_session_type, arena_singleton
        import time as _t
        session = get_session_type()
        if session == "closed":
            return
        try:
            import httpx
            import app.api.routes as _routes

            async with httpx.AsyncClient() as client:
                # 1. Refresh Finviz scan every 20s (respects 25s cache TTL — won't double-fetch)
                fv_age = _t.time() - _routes._FV_TABLE_CACHE_TIME
                if fv_age > 20 or not _routes._FV_TABLE_CACHE.get('data', {}).get('stocks'):
                    try:
                        await client.get("http://localhost:8000/api/screener/finviz-table",
                                         timeout=httpx.Timeout(30.0))
                    except Exception:
                        pass

                # 1.5. Refresh hot movers raw list every 60s (GapExplosion needs micro-caps)
                hot_age = _t.time() - _routes._HOT_MOVERS_RAW_CACHE_TIME
                if hot_age > 60:
                    try:
                        await _routes._scrape_hot_movers(5.0)
                    except Exception:
                        pass

                # 2. Fetch live prices for open positions (yfinance, fast)
                open_tickers = set()
                for pf in arena_singleton.portfolios.values():
                    open_tickers.update(pf.positions.keys())
                if open_tickers:
                    tickers_param = ','.join(sorted(open_tickers))
                    try:
                        lp_resp = await client.get(
                            f"http://localhost:8000/api/screener/live-prices?tickers={tickers_param}",
                            timeout=httpx.Timeout(8.0))
                        lp_data = lp_resp.json()
                        # Inject fresh prices into FV_TABLE_CACHE so think() sees them
                        cached_stocks = _routes._FV_TABLE_CACHE.get('data', {}).get('stocks', [])
                        # live-prices returns {ticker: {price, change_pct, ...}}
                        price_map = {}
                        for t, v in lp_data.items():
                            try:
                                p = float(v['price']) if isinstance(v, dict) else float(v)
                                if p > 0:
                                    price_map[t] = p
                            except (TypeError, ValueError, KeyError):
                                pass
                        for s in cached_stocks:
                            t = s.get('ticker')
                            if t in price_map:
                                s['price'] = price_map[t]
                        # Also inject into smallcap cache
                        for s in _routes._FV_SMALLCAP_CACHE:
                            t = s.get('ticker')
                            if t in price_map:
                                s['price'] = price_map[t]
                    except Exception:
                        pass

                # 3. Run arena think with up-to-date data
                ra = await client.post("http://localhost:8000/api/smart-portfolio/arena/think",
                                       timeout=httpx.Timeout(15.0))
                lb = ra.json().get("leaderboard", [])
                if lb:
                    leader = lb[0]
                    print(f"[Arena:{session}] {leader['label']} "
                          f"${leader.get('equity',1000):.0f} ({leader.get('pnl_pct',0):+.2f}%)")
        except Exception as e:
            print(f"[Arena] tick error: {e}")

    scheduler.add_job(_arena_tick, "interval", seconds=10, id="arena_tick_job",
                      max_instances=1, coalesce=True)

    # Small-cap squeeze stock scanner — refreshes every 2 min for HardSqueeze/NanoSqueeze
    async def _refresh_smallcap_squeeze():
        from app.services.strategy_arena import get_session_type
        if get_session_type() == "closed":
            return
        import time as _t
        import app.api.routes as _routes
        if _t.time() - _routes._FV_SMALLCAP_CACHE_TIME < _routes._FV_SMALLCAP_CACHE_TTL:
            return
        try:
            from app.api.routes import finviz_screener
            # Two scans merged: sh_short_o20 (Hard/Gap/Nano ≥20%) +
            # sh_short_o10 (Lightning Squeeze ≥10%), wider net
            _sc_tasks = [
                finviz_screener._scrape_screener(
                    {'v': '111', 'f': 'cap_smallover,sh_short_o20,sh_price_o2',
                     'o': '-changeopen', 'r': str(r)},
                    'smallcap-20',
                ) for r in [1, 21]
            ] + [
                finviz_screener._scrape_screener(
                    {'v': '111', 'f': 'cap_smallover,sh_short_o10,sh_price_o2',
                     'o': '-changeopen', 'r': '1'},
                    'smallcap-10',
                )
            ]
            pages = await __import__('asyncio').gather(*_sc_tasks, return_exceptions=True)
            seen, result = set(), []
            for page in pages:
                if isinstance(page, Exception):
                    continue
                for s in page:
                    t = s.get('ticker')
                    if t and t not in seen:
                        seen.add(t)
                        source = s.get('scan_sources', [''])[0]
                        chg = abs(float(s.get('change_pct') or 0))
                        rvol_est = max(1.5, min(chg * 0.8, 8.0))
                        # floor depends on which scan the stock came from
                        sf_floor = 22.0 if 'smallcap-20' in source else 11.0
                        s.setdefault('short_float', sf_floor)
                        s.setdefault('health_score', 20)
                        s.setdefault('rel_volume', rvol_est)
                        s.setdefault('squeeze_total_score', 55)  # bonus for being in squeeze scan
                        result.append(s)
            if result:
                _routes._FV_SMALLCAP_CACHE[:] = result
                _routes._FV_SMALLCAP_CACHE_TIME = _t.time()
                print(f"[SmallCap] refreshed {len(result)} stocks (short float ≥10%, small cap)")
        except Exception as e:
            print(f"[SmallCap] scan error: {e}")

    scheduler.add_job(_refresh_smallcap_squeeze, "interval", minutes=2,
                      id="smallcap_squeeze_job", max_instances=1, coalesce=True)
    print("SmallCap Squeeze Scanner: refresh every 2min for Hard/Nano Squeeze strategies")

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

        # SeasonalSwing — aggressive seasonal data (win≥60%, includes avg_return + max_loss)
        if now - _routes._ARENA_SEASONAL_SWING_UPDATED > 7200:
            try:
                today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
                async with httpx.AsyncClient() as c:
                    r = await c.get(
                        f"http://localhost:8000/api/seasonality?market=ndx100"
                        f"&start_date={today}&min_win_pct=60&years=10&days_min=5&days_max=30",
                        timeout=120
                    )
                    data = r.json()
                if isinstance(data, dict) and not data.get("loading"):
                    pats = data.get("patterns", [])
                    if pats:
                        swing_map = {}
                        for p in pats:
                            wr = p.get("win_ratio", 0)
                            ar = p.get("avg_return", 0)
                            ml = p.get("max_loss", -999)
                            if wr >= 60 and ar >= 2.0 and abs(ml) <= 25:
                                swing_map[p["ticker"]] = {
                                    "win_ratio":  wr,
                                    "avg_return": ar,
                                    "max_loss":   ml,
                                }
                        _routes._ARENA_SEASONAL_SWING_DATA    = swing_map
                        _routes._ARENA_SEASONAL_SWING_UPDATED = _t.time()
                        print(f"[Arena:SeasonalSwing] {len(swing_map)} tickers: "
                              f"{list(swing_map.keys())[:8]}")
            except Exception as e:
                print(f"[Arena:SeasonalSwing] refresh error: {e}")

    scheduler.add_job(_refresh_arena_aux_caches, "interval", minutes=30, id="arena_aux_cache_job",
                      max_instances=1, coalesce=True)

    # Sector briefing background refresh — keeps cache warm so user requests are instant
    async def _refresh_sector_briefing():
        try:
            from app.services.sector_briefing_service import get_sector_briefing
            await asyncio.wait_for(get_sector_briefing(), timeout=45)
        except Exception:
            pass

    scheduler.add_job(_refresh_sector_briefing, "interval", minutes=3,
                      id="sector_refresh_job", max_instances=1, coalesce=True)
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
    _ib_reconnect_failures = [0]   # consecutive failure counter
    _ib_was_connected = [False]    # True after we confirmed connection at least once this session
    _ib_disconnect_alerted = [False]  # True after we sent the "disconnected" Telegram

    async def _ib_auto_reconnect():
        from app.services.ib_service import ib_service
        from app.services.arena_ib_trader import _tg

        # ── 1. Heartbeat check (every call — catches dead sockets) ─────────
        import asyncio as _asyncio
        loop = _asyncio.get_running_loop()
        is_alive = await loop.run_in_executor(None, ib_service.heartbeat)

        if is_alive:
            # Connected and healthy
            if _ib_disconnect_alerted[0]:
                # Just recovered — send Telegram
                _ib_reconnect_failures[0] = 0
                _ib_disconnect_alerted[0] = False
                account = ib_service._account or "?"
                import time as _time
                down_sec = int(_time.time() - (ib_service._disconnect_time or _time.time())) if ib_service._disconnect_time else 0
                down_str = f" (ניתוק של {down_sec // 60}:{down_sec % 60:02d} דקות)" if down_sec > 0 else ""
                print(f"[IB Reconnect] ✓ Gateway חזר לאוויר — {account}{down_str}")
                await _tg(
                    f"✅ <b>IB Gateway — חיבור חזר</b>\n"
                    f"חשבון: <b>{account}</b>{down_str}\n"
                    f"הארנה חוזרת לפעול."
                )
            _ib_was_connected[0] = True
            _ib_reconnect_failures[0] = 0
            return

        # ── 2. Only auto-reconnect if we were ever manually connected ──────
        if not ib_service._ever_connected:
            return

        # ── 3. First detection → send disconnect alert ─────────────────────
        if not _ib_disconnect_alerted[0]:
            _ib_disconnect_alerted[0] = True
            print("[IB Reconnect] Gateway לא מגיב — שולח התראה")
            await _tg(
                f"🔴 <b>IB Gateway — ניתוק</b>\n"
                f"Gateway לא מגיב על {ib_service._host}:{ib_service._port}\n"
                f"מנסה reconnect אוטומטי...\n"
                f"אם Gateway קרס — הפעל מחדש וכנס ל-IB."
            )

        # ── 4. Backoff: first 3 failures → aggressive (every tick=60s),
        #                 4-10 → every 2 ticks, 11+ → every 5 ticks (~5min) ──
        n = _ib_reconnect_failures[0]
        if n >= 10 and n % 5 != 0:
            _ib_reconnect_failures[0] += 1
            return
        if 3 <= n < 10 and n % 2 != 0:
            _ib_reconnect_failures[0] += 1
            return

        try:
            print(f"[IB Reconnect] מנסה reconnect ל-{ib_service._host}:{ib_service._port} "
                  f"(ניסיון #{_ib_reconnect_failures[0] + 1})...")
            result = await ib_service.connect(
                host=ib_service._host, port=ib_service._port, client_id=20
            )
            if result.get("connected"):
                # Success — alert will be sent on next heartbeat pass
                _ib_reconnect_failures[0] = 0
                print(f"[IB Reconnect] ✓ Connected to {result.get('account', '?')}")
            else:
                _ib_reconnect_failures[0] += 1
                print(f"[IB Reconnect] נכשל: {result.get('error', 'unknown')} "
                      f"(ניסיון #{_ib_reconnect_failures[0]})")
        except Exception as e:
            _ib_reconnect_failures[0] += 1
            print(f"[IB Reconnect] שגיאה: {e} (ניסיון #{_ib_reconnect_failures[0]})")

    scheduler.add_job(_ib_auto_reconnect, "interval", seconds=60, id="ib_reconnect_job",
                      max_instances=1, coalesce=True)
    print("IB Auto-Reconnect: heartbeat + reconnect every 60s, Telegram alerts on disconnect/recover")

    # ── System Watchdog — self-healing monitor every 5 min ─────────────────
    async def _system_watchdog():
        """
        Checks full system health during market hours.
        If something is broken, fixes it automatically.
        """
        from app.services.strategy_arena import get_session_type
        session = get_session_type()
        if session == "closed":
            return

        from app.services.ib_service import ib_service
        from app.services.arena_ib_trader import arena_ib_trader
        issues = []
        fixes = []

        # 1. Check arena is ticking
        from app.services.strategy_arena import arena_singleton
        last_tick = getattr(arena_singleton, 'last_tick', None)
        tick_count = getattr(arena_singleton, 'tick_count', 0)
        if last_tick:
            from datetime import datetime
            try:
                lt = datetime.fromisoformat(str(last_tick))
                age_s = (datetime.now() - lt).total_seconds()
                if age_s > 120:  # no tick in 2+ minutes
                    issues.append(f"Arena stale — last tick {int(age_s)}s ago")
                    # Force a tick
                    try:
                        import httpx
                        async with httpx.AsyncClient(timeout=30) as c:
                            await c.post("http://localhost:8000/api/smart-portfolio/arena/think")
                        fixes.append("Forced arena tick")
                    except Exception:
                        pass
            except Exception:
                pass
        elif session in ("premarket", "regular", "aftermarket"):
            issues.append("Arena never ticked")

        # 2. Check IB connection
        if ib_service._ever_connected and not ib_service.is_connected():
            issues.append("IB disconnected")
            try:
                result = await ib_service.connect(
                    host=ib_service._host, port=ib_service._port, client_id=20
                )
                if result.get("connected"):
                    fixes.append(f"IB reconnected to {result.get('account', '?')}")
                else:
                    issues.append(f"IB reconnect failed: {result.get('error', '?')}")
            except Exception as e:
                issues.append(f"IB reconnect error: {e}")

        # 3. Check arena IB trader
        if arena_ib_trader.enabled:
            if not arena_ib_trader.active_strategy and session in ("premarket", "regular"):
                issues.append("Arena IB trader has no active strategy")
                # Trigger tick to pick leader
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=30) as c:
                        await c.post("http://localhost:8000/api/smart-portfolio/arena/think")
                    fixes.append("Triggered tick to pick leader")
                except Exception:
                    pass

        # 4. Kill zombie uvicorn processes (leftover from --reload restarts)
        import subprocess
        try:
            out = subprocess.check_output(
                ["pgrep", "-f", "uvicorn.*app.main"], text=True
            ).strip().split("\n")
            my_pid = os.getpid()
            my_parent = os.getppid()
            zombie_pids = [
                int(p) for p in out if p.strip()
                and int(p) != my_pid and int(p) != my_parent
            ]
            if zombie_pids:
                for zp in zombie_pids:
                    try:
                        os.kill(zp, 9)
                    except ProcessLookupError:
                        pass
                issues.append(f"Killed {len(zombie_pids)} zombie uvicorn(s): {zombie_pids}")
                fixes.append("Zombie cleanup done")
        except (subprocess.CalledProcessError, Exception):
            pass  # no matches = no zombies

        # Log results
        if issues:
            print(f"[Watchdog:{session}] Issues: {'; '.join(issues)}")
            if fixes:
                print(f"[Watchdog:{session}] Fixed: {'; '.join(fixes)}")
        else:
            # Quiet log every 30 min (every 6th check)
            import time
            if int(time.time()) % 1800 < 300:
                ib_ok = "IB=" + ("OK" if ib_service.is_connected() else "OFF")
                arena_ok = f"Arena=tick#{tick_count}"
                trader_ok = f"Trader={'ON:' + arena_ib_trader.active_strategy if arena_ib_trader.enabled else 'OFF'}"
                print(f"[Watchdog:{session}] All OK — {ib_ok} {arena_ok} {trader_ok}")

    scheduler.add_job(_system_watchdog, "interval", minutes=5, id="watchdog_job",
                      max_instances=1, coalesce=True)
    print("System Watchdog: self-healing checks every 5min during market hours")

    # ── Periodic Telegram arena report every 2 hours ────────────────────────
    async def _arena_tg_report():
        from app.services.arena_ib_trader import send_arena_report
        await send_arena_report()

    scheduler.add_job(_arena_tg_report, "interval", hours=2, id="arena_report_job",
                      max_instances=1, coalesce=True)
    print("Arena Telegram Report: summary every 2h during market hours")

    # ── EOD Auto-replace losing strategies (16:15 ET daily) ─────────────────
    async def _eod_auto_replace():
        """Replace losing strategies with variants of winners at end of trading day."""
        from app.services.strategy_arena import arena_singleton
        from app.services.arena_ib_trader import _tg

        # Build live prices from cache
        from app.api.routes import _FV_TABLE_CACHE, _LIVE_PRICES_CACHE, _safe_float
        cached = _FV_TABLE_CACHE.get('data', {})
        live_prices = {
            s['ticker']: _safe_float(s.get('price'))
            for s in cached.get('stocks', [])
            if s.get('ticker') and _safe_float(s.get('price')) > 0
        }
        for ticker, data in _LIVE_PRICES_CACHE.items():
            price = _safe_float(data.get('price') if isinstance(data, dict) else data)
            if price > 0:
                live_prices[ticker] = price

        replacements = arena_singleton.auto_replace_losers(live_prices)
        if not replacements:
            print("[EOD] No losing strategies to replace")
            return

        # Telegram notification
        lines = []
        for r in replacements:
            closed_str = ", ".join(r["closed"]) if r["closed"] else "אין"
            lines.append(
                f"🔄 <b>{r['replaced']}</b> → <b>{r['new_label']}</b> "
                f"(clone of {r['template']})\n"
                f"   נסגרו: {closed_str}  |  P&L יומי: ${r['old_pnl']:+.2f}"
            )

        msg = (
            f"🔁 <b>EOD — החלפת אסטרטגיות אוטומטית</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            + "\n".join(lines) + "\n\n"
            f"הכל ריק ומוכן לכניסות חדשות מחר ✅"
        )
        await _tg(msg)
        print(f"[EOD] Replaced {len(replacements)} losing strategies")

    # Run via interval every 1 min — fires once at 16:15 ET window
    _eod_replace_done_today: dict = {"date": ""}

    async def _eod_auto_replace_check():
        from datetime import datetime, timezone, timedelta
        et_offset = timedelta(hours=-4)
        now_et = datetime.now(timezone.utc) + et_offset
        if now_et.weekday() >= 5:
            return  # weekend
        today = now_et.strftime("%Y-%m-%d")
        h, m = now_et.hour, now_et.minute
        # Fire in the 16:15–16:19 window, once per day
        if not (h == 16 and 15 <= m < 20):
            return
        if _eod_replace_done_today["date"] == today:
            return
        _eod_replace_done_today["date"] = today
        await _eod_auto_replace()

    scheduler.add_job(_eod_auto_replace_check, "interval", minutes=1,
                      id="eod_replace_job", max_instances=1, coalesce=True)
    print("EOD Strategy Auto-Replace: daily at 16:15 ET")

    # ── Hot Movers Telegram alert every 5 minutes during market hours ────────
    _hot_alert_sent: dict = {}  # ticker → last_sent timestamp (dedup 30min)

    async def _hot_movers_alert():
        import time as _tm3
        from app.services.alerts_service import send_telegram
        from app.api.routes import arena_hot_movers

        now_et = datetime.now(tz=__import__('zoneinfo').ZoneInfo('America/New_York'))
        # premarket 4:00–9:30, regular 9:30–16:00, aftermarket 16:00–20:00
        if not (4 <= now_et.hour < 20):
            return

        try:
            result = await arena_hot_movers(min_chg=5.0)
        except Exception as e:
            print(f"[HotAlert] fetch error: {e}")
            return

        movers = result.get('movers', [])
        # top picks: pick_score >= 6, not alerted in last 30 min
        now_ts = _tm3.time()
        def _pf(v):
            try: return float(str(v).replace('%','').replace(',','').strip()) if v not in (None,'') else None
            except: return None

        EV_SCORE = {
            'profitable_strong': 4, 'profitable': 3, 'profitable_weak': 2,
            'breakeven_cash': 2, 'growing': 2, 'stable_cash': 1,
            'breakeven': 1, 'profitable_strong_debt': 2, 'profitable_debt': 1,
        }

        def _financial_tier(m):
            score = EV_SCORE.get(m.get('ev_cash_reason') or '', 0)
            if score >= 4: return '💰💰💰'
            if score >= 3: return '💰💰'
            if score >= 2: return '💰'
            return None

        def _is_top_candidate(m):
            chg  = m.get('change_pct') or 0
            rvol = _pf(m.get('rel_volume')) or 0
            tier = _financial_tier(m)
            moving = chg > 3.0 and rvol > 1.5 and chg <= 80  # >80% = late entry risk
            if tier and moving:
                return True, tier
            return False, None

        picks = []
        for m in movers:
            if now_ts - _hot_alert_sent.get(m['ticker'], 0) < 1800:
                continue
            # Only alert when bot has real conviction: TOP CANDIDATE + momentum still going up
            if not m.get('strong_conviction'):
                continue
            ok, tier = _is_top_candidate(m)
            if ok:
                picks.append((m, tier))
        picks = picks[:3]

        if not picks:
            return

        _EV_REASON_HE = {
            'profitable_strong':      'רווחית מאוד — EV נמוך ממחיר השוק',
            'profitable':             'רווחית — EV נמוך ממחיר השוק',
            'profitable_weak':        'רווחית בקושי — EV נמוך ממחיר השוק',
            'breakeven_cash':         'איזון — יש מזומן עודף',
            'growing':                'גדלה — הכנסות עולות, עדיין בהפסד',
            'stable_cash':            'יציבה — יש מזומן עודף',
            'breakeven':              'איזון — הוצאות = הכנסות',
            'stable':                 'יציבה — הכנסות לא גדלות',
            'profitable_strong_debt': 'רווחית מאוד — אבל יש חוב',
            'profitable_debt':        'רווחית — אבל יש חוב',
            'profitable_weak_debt':   'רווחית בקושי + חוב גבוה',
            'losing_debt':            'מפסידה + חוב גבוה ⚠️',
            'distressed_debt':        'מצוקה פיננסית + חוב גבוה 🔴',
            'distressed':             'הכנסות נמוכות + הפסד גדול ⚠️',
            'cash_unknown':           'EV נמוך ממחיר השוק — אין מספיק מידע',
        }
        lines = ['🔥 <b>מניות חמות — המלצה עכשיו</b>']
        for m, tier in picks:
            ticker  = m['ticker']
            chg     = m.get('change_pct', 0)
            reason  = m.get('ev_cash_reason') or ''
            strat   = m.get('top_strategy') or ''
            c30     = m.get('chg_30m')
            c1h     = m.get('chg_1h')
            price   = m.get('price', '')
            sf      = _pf(m.get('short_float'))
            rvol    = _pf(m.get('rel_volume'))

            reason_he = _EV_REASON_HE.get(reason, '')
            sf_str   = f"שורט {sf:.0f}%" if sf else ''
            rvol_str = f"נפח פי {rvol:.0f}x" if rvol else ''
            mom_str  = ''
            if c30 is not None and c1h is not None:
                mom_str = f"30 דק' {c30:+.1f}%  |  שעה {c1h:+.1f}%"
            elif c30 is not None:
                mom_str = f"30 דק' {c30:+.1f}%"

            meta = '  |  '.join(filter(None, [sf_str, rvol_str]))
            ts = m.get('trade_suggestion') or {}
            ts_line = ''
            if ts:
                ts_line = f"💡 כניסה ${ts['entry']}  יעד ${ts['target']} (+{ts['target_pct']}%)  סטופ ${ts['stop']} (-{ts['stop_pct']}%)  R:R {ts['rr']}:1"
            lines.append(
                f"\n{tier} <b>{ticker}</b> {chg:+.1f}%  ${price}\n"
                + (f"📊 {reason_he}\n" if reason_he else '')
                + (f"{meta}\n" if meta else '')
                + (f"📈 {mom_str}\n" if mom_str else '')
                + (f"🎯 אסטרטגיה: {strat}\n" if strat else '')
                + (f"{ts_line}" if ts_line else '')
            )
            _hot_alert_sent[ticker] = now_ts

        await send_telegram('\n'.join(lines))

    scheduler.add_job(_hot_movers_alert, "interval", minutes=5, id="hot_movers_alert_job",
                      max_instances=1, coalesce=True)
    print("Hot Movers Alert: Telegram every 5min (market hours, score≥6, dedup 30min)")

    # Disabled — briefing tab hidden to save resources
    # async def _prewarm_briefing():
    #     import httpx
    #     await asyncio.sleep(8)
    #     try:
    #         async with httpx.AsyncClient() as client:
    #             await client.get("http://127.0.0.1:8000/api/briefing/daily", timeout=60)
    #             print("Briefing cache pre-warmed.")
    #     except Exception as e:
    #         print(f"Briefing pre-warm failed: {e}")
    # asyncio.create_task(_prewarm_briefing())

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
        await asyncio.sleep(5)  # let server finish startup first
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

# ── Connection tracker — Telegram alert on new IP ────────────────────────────
_seen_ips: set = set()

@app.middleware("http")
async def connection_tracker(request: Request, call_next):
    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown").split(",")[0].strip()
    # Only track page loads (not API polling noise)
    path = request.url.path
    if ip not in _seen_ips and (path == "/" or path.startswith("/api/arena") or path.startswith("/api/briefing")):
        _seen_ips.add(ip)
        try:
            from app.services.alerts_service import send_telegram
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=3)))
            ua = request.headers.get("User-Agent", "")[:80]
            asyncio.create_task(send_telegram(
                f"🔌 <b>חיבור חדש</b>\n"
                f"🌐 IP: <code>{ip}</code>\n"
                f"📍 Path: <code>{path}</code>\n"
                f"🕐 {now.strftime('%H:%M:%S')} (IST)\n"
                f"📱 {ua}"
            ))
        except Exception:
            pass
    return await call_next(request)


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
