"""
Catalyst Tracker Service — Orchestrates FDA/Tech calendar + Finviz fundamentals + news.

Combines:
1. FDA Calendar Scraper (multiple biotech sources)
2. Tech Catalyst Scraper (earnings, product launches)
3. Finviz Fundamentals (institutional, insider, margins, SMAs)
4. yfinance news (latest headlines per ticker)
5. FDA Movers — tracks historical catalyst stock movements

Calculates catalyst_score (0-100) for prioritization.
Uses BIO/PMC clinical trial success rate data (2015-2023) for approval probability.
"""

import asyncio
import time
import yfinance as yf
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from app.scrapers.fda_calendar import FDACalendarScraper
from app.scrapers.finviz_fundamentals import FinvizFundamentals
from app.scrapers.tech_catalyst import TechCatalystScraper


# ═══════════════════════════════════════════════════════════════
# BIO / PMC Clinical Development Success Rates (2015-2023)
# Source: PMC12572394, BIO Industry Analysis
# ═══════════════════════════════════════════════════════════════

# Phase transition probabilities (what % advance to next phase)
PHASE_TRANSITION_RATES = {
    'Phase1_to_Phase2': 50,
    'Phase2_to_Phase3': 28,
    'Phase3_to_NDA': 58,
    'NDA_to_Approval': 85,
    'sBLA_sNDA_Approval': 93,
}

# Overall Likelihood of Approval from each stage (Phase → Market)
LOA_BY_PHASE = {
    'Phase1': 6.7,
    'Phase2': 15,
    'Phase3': 58,
    'NDA_BLA': 85,
    'sBLA_sNDA': 93,
    'AdCom_positive': 75,
}

# Success rates by therapeutic area (Overall Success Rate Phase1→Approval)
# Source: PMC12572394 Table, 2015-2023 window
THERAPEUTIC_AREA_LOA = {
    'hematology': 18.5,
    'blood': 18.5,
    'metabolic': 14.0,
    'endocrine': 14.0,
    'diabetes': 14.0,
    'musculoskeletal': 13.0,
    'bone': 13.0,
    'immune': 12.0,
    'autoimmune': 12.0,
    'rheumatology': 12.0,
    'dermatology': 10.0,
    'skin': 10.0,
    'ophthalmology': 9.5,
    'eye': 9.5,
    'retinal': 9.5,
    'respiratory': 4.5,
    'lung': 4.5,
    'asthma': 4.5,
    'cardiovascular': 5.0,
    'heart': 5.0,
    'neurology': 5.5,
    'cns': 5.5,
    'alzheimer': 3.0,
    'parkinson': 5.0,
    'psychiatry': 6.0,
    'oncology': 4.7,
    'cancer': 4.7,
    'tumor': 4.7,
    'infectious': 5.0,
    'infection': 5.0,
    'antiviral': 5.0,
    'rare_disease': 15.0,
    'orphan': 15.0,
    'gastroenterology': 8.0,
    'gi': 8.0,
    'hepatology': 7.0,
    'liver': 7.0,
    'nephrology': 6.0,
    'kidney': 6.0,
    'urology': 8.0,
}

# NDA/BLA-stage approval rates by therapeutic area (Phase 3 → Approval)
# Higher because we're only looking at late-stage drugs
NDA_APPROVAL_BY_AREA = {
    'hematology': 92,
    'blood': 92,
    'metabolic': 88,
    'rare_disease': 90,
    'orphan': 90,
    'oncology': 78,
    'cancer': 78,
    'neurology': 80,
    'cns': 80,
    'cardiovascular': 82,
    'respiratory': 80,
    'infectious': 82,
    'dermatology': 87,
    'ophthalmology': 85,
    'gastroenterology': 85,
    'default': 85,
}

# Drug modality modifiers (vs small molecule baseline)
MODALITY_MODIFIERS = {
    'antibody': +3,
    'monoclonal': +3,
    'bispecific': +2,
    'adc': +1,
    'car-t': -2,
    'cell therapy': -3,
    'gene therapy': -5,
    'sirna': +1,
    'mrna': -2,
    'crispr': -5,
    'antisense': 0,
    'peptide': +1,
    'protein': +1,
    'small molecule': 0,
}


class CatalystTrackerService:
    COMBINED_CACHE_TTL = 300  # 5 minutes
    NEWS_CACHE_TTL = 180  # 3 minutes

    def __init__(self, fda_scraper: FDACalendarScraper, finviz_fundamentals: FinvizFundamentals,
                 tech_scraper: TechCatalystScraper):
        self.fda_scraper = fda_scraper
        self.finviz_fundamentals = finviz_fundamentals
        self.tech_scraper = tech_scraper
        self._fda_cache: Optional[List[Dict]] = None
        self._fda_cache_time: float = 0
        self._tech_cache: Optional[List[Dict]] = None
        self._tech_cache_time: float = 0
        self._news_cache: Dict[str, List[Dict]] = {}
        self._news_cache_time: Dict[str, float] = {}
        self._fda_lock = None
        self._tech_lock = None
        self._yf_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='cat_news')

    def _get_fda_lock(self):
        if self._fda_lock is None:
            self._fda_lock = asyncio.Lock()
        return self._fda_lock

    def _get_tech_lock(self):
        if self._tech_lock is None:
            self._tech_lock = asyncio.Lock()
        return self._tech_lock

    async def get_catalyst_events(self, days_forward: int = 90, days_back: int = 30,
                                   enriched: bool = True) -> List[Dict]:
        """Main method: get FDA catalyst events enriched with fundamentals + news."""
        now = time.time()

        # Return cached if fresh
        if self._fda_cache and (now - self._fda_cache_time) < self.COMBINED_CACHE_TTL:
            return self._fda_cache

        lock = self._get_fda_lock()
        if lock.locked():
            # Return stale cache while another request is processing
            if self._fda_cache:
                return self._fda_cache
            return []

        async with lock:
            # Double-check after acquiring lock
            now = time.time()
            if self._fda_cache and (now - self._fda_cache_time) < self.COMBINED_CACHE_TTL:
                return self._fda_cache

            try:
                # 1. Fetch FDA events
                events = await asyncio.wait_for(
                    self.fda_scraper.get_fda_events(days_forward=days_forward, days_back=days_back),
                    timeout=20
                )

                if enriched and events:
                    # 2. Extract unique tickers and enrich with Finviz fundamentals
                    tickers = list(set(e['ticker'] for e in events if e.get('ticker')))
                    tickers = tickers[:30]  # Limit to top 30

                    if tickers:
                        try:
                            fundamentals = await asyncio.wait_for(
                                self.finviz_fundamentals.get_fundamentals_batch(tickers),
                                timeout=35
                            )
                            for event in events:
                                ticker = event.get('ticker', '')
                                if ticker in fundamentals:
                                    event['fundamentals'] = fundamentals[ticker]
                        except asyncio.TimeoutError:
                            print("Catalyst enrichment TIMEOUT — skipping fundamentals")

                    # 3. Fetch news for top tickers
                    top_tickers = tickers[:15]
                    if top_tickers:
                        try:
                            news_data = await asyncio.wait_for(
                                self._fetch_news_for_tickers(top_tickers),
                                timeout=15
                            )
                            for event in events:
                                ticker = event.get('ticker', '')
                                if ticker in news_data:
                                    event['latest_news'] = news_data[ticker]
                        except asyncio.TimeoutError:
                            print("News fetch TIMEOUT — skipping news")

                # 4. Re-calculate approval probability with Finviz data
                for event in events:
                    event['approval_probability'] = self._calculate_approval_probability(event)

                # 5. Calculate catalyst score for each event
                for event in events:
                    event['catalyst_score'] = self._calculate_catalyst_score(event)

                # Sort by score descending, then by days_until ascending
                events.sort(key=lambda x: (-x.get('catalyst_score', 0), abs(x.get('days_until') or 9999)))

                self._fda_cache = events
                self._fda_cache_time = time.time()
                return events

            except asyncio.TimeoutError:
                print("Catalyst tracker OVERALL TIMEOUT")
                return self._fda_cache or []
            except Exception as e:
                print(f"Catalyst tracker error: {e}")
                import traceback
                traceback.print_exc()
                return self._fda_cache or []

    async def get_tech_catalyst_events(self, days_forward: int = 90,
                                        enriched: bool = True) -> List[Dict]:
        """Get tech stock catalyst events enriched with fundamentals + news."""
        now = time.time()

        if self._tech_cache and (now - self._tech_cache_time) < self.COMBINED_CACHE_TTL:
            return self._tech_cache

        lock = self._get_tech_lock()
        if lock.locked():
            if self._tech_cache:
                return self._tech_cache
            return []

        async with lock:
            now = time.time()
            if self._tech_cache and (now - self._tech_cache_time) < self.COMBINED_CACHE_TTL:
                return self._tech_cache

            try:
                events = await asyncio.wait_for(
                    self.tech_scraper.get_tech_catalyst_events(days_forward=days_forward),
                    timeout=120
                )

                if enriched and events:
                    tickers = list(set(e['ticker'] for e in events if e.get('ticker')))
                    tickers = tickers[:30]

                    if tickers:
                        try:
                            fundamentals = await asyncio.wait_for(
                                self.finviz_fundamentals.get_fundamentals_batch(tickers),
                                timeout=55
                            )
                            for event in events:
                                ticker = event.get('ticker', '')
                                if ticker in fundamentals:
                                    event['fundamentals'] = fundamentals[ticker]
                                    # Fill in company name from Finviz if ticker-only
                                    if event.get('company') == ticker and fundamentals[ticker].get('company_name'):
                                        event['company'] = fundamentals[ticker]['company_name']
                        except asyncio.TimeoutError:
                            print("Tech enrichment TIMEOUT")

                    top_tickers = tickers[:15]
                    if top_tickers:
                        try:
                            news_data = await asyncio.wait_for(
                                self._fetch_news_for_tickers(top_tickers),
                                timeout=15
                            )
                            for event in events:
                                ticker = event.get('ticker', '')
                                if ticker in news_data:
                                    event['latest_news'] = news_data[ticker]
                        except asyncio.TimeoutError:
                            pass

                for event in events:
                    event['catalyst_score'] = self._calculate_catalyst_score(event)

                events.sort(key=lambda x: (-x.get('catalyst_score', 0), abs(x.get('days_until') or 9999)))

                self._tech_cache = events
                self._tech_cache_time = time.time()
                return events

            except asyncio.TimeoutError:
                return self._tech_cache or []
            except Exception as e:
                print(f"Tech catalyst tracker error: {e}")
                return self._tech_cache or []

    async def _fetch_news_for_tickers(self, tickers: List[str]) -> Dict[str, List[Dict]]:
        """Fetch latest news for tickers using yfinance with bounded concurrency."""
        sem = asyncio.Semaphore(3)
        results = {}

        async def fetch_one(ticker: str, idx: int):
            async with sem:
                # Check news cache
                now = time.time()
                if ticker in self._news_cache and (now - self._news_cache_time.get(ticker, 0)) < self.NEWS_CACHE_TTL:
                    return ticker, self._news_cache[ticker]

                await asyncio.sleep(idx * 0.15)
                try:
                    loop = asyncio.get_event_loop()
                    news = await asyncio.wait_for(
                        loop.run_in_executor(self._yf_executor, self._fetch_news_sync, ticker),
                        timeout=4
                    )
                    self._news_cache[ticker] = news
                    self._news_cache_time[ticker] = time.time()
                    return ticker, news
                except asyncio.TimeoutError:
                    return ticker, []
                except Exception:
                    return ticker, []

        tasks = [fetch_one(t, i) for i, t in enumerate(tickers)]
        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for item in completed:
            if isinstance(item, tuple) and len(item) == 2:
                ticker, news = item
                results[ticker] = news

        return results

    def _fetch_news_sync(self, ticker: str) -> List[Dict]:
        """Synchronous yfinance news fetch."""
        news_items = []
        try:
            stock = yf.Ticker(ticker)
            from concurrent.futures import ThreadPoolExecutor as _TP
            with _TP(max_workers=1) as _ex:
                future = _ex.submit(lambda: stock.news or [])
                raw_news = future.result(timeout=3)

            for item in raw_news[:5]:
                content = item.get('content', {}) or {}
                title = str(content.get('title') or '')
                if not title:
                    continue
                provider = content.get('provider', {})
                publisher = str(provider.get('displayName', '')) if isinstance(provider, dict) else str(provider or '')
                canonical = content.get('canonicalUrl', {})
                link = str(canonical.get('url', '')) if isinstance(canonical, dict) else str(canonical or '')
                if not link:
                    click = content.get('clickThroughUrl', {})
                    link = str(click.get('url', '')) if isinstance(click, dict) else str(click or '')
                pub_date = str(content.get('pubDate') or '')

                # Summary
                summary = str(content.get('summary') or '')
                if len(summary) > 300:
                    summary = summary[:297] + '...'

                news_items.append({
                    'title': title,
                    'publisher': publisher,
                    'link': link,
                    'pub_date': pub_date,
                    'summary': summary,
                })
        except Exception:
            pass

        return news_items

    def _calculate_approval_probability(self, event: Dict) -> Dict:
        """
        FDA Approval Probability (PoA) — academic data + real market signals.

        Layer 1: BIO/PMC base rate by phase (Phase 1: 6.7%, Phase 2: 15%, Phase 3: 58%, NDA: 85%)
        Layer 2: Therapeutic area modifier (Hematology: 18.5%, Oncology: 4.7%, Rare: 15%)
        Layer 3: Drug modality modifier (antibody +3%, gene therapy -5%, etc.)
        Layer 4: FDA designations (breakthrough, priority, orphan)
        Layer 5: Real market signals (analyst targets, insider buying, institutional flow)
        """
        cat_type = event.get('catalyst_type', '')
        status = (event.get('status') or '').lower()
        drug_name = (event.get('drug_name') or '').lower()
        indication = (event.get('indication') or '').lower()
        phase = (event.get('phase') or '').lower()
        company = (event.get('company') or '').lower()
        full_text = f"{drug_name} {indication} {phase} {cat_type} {company}".lower()
        sources = event.get('sources', [])
        fundamentals = event.get('fundamentals', {})

        probability = 50
        confidence = 'Low'
        factors = []

        # ═══ Already decided — no estimation needed ═══
        if 'approved' in status or 'complete - approved' in status:
            return {'probability': 100, 'confidence': 'Confirmed', 'factors': ['FDA approved']}
        if 'rejected' in status or 'crl' in status:
            return {'probability': 0, 'confidence': 'Confirmed', 'factors': ['CRL / Rejected']}
        if cat_type == 'CRL':
            return {'probability': 0, 'confidence': 'Confirmed', 'factors': ['Complete Response Letter issued']}
        if cat_type == 'Approval':
            return {'probability': 100, 'confidence': 'Confirmed', 'factors': ['Already approved']}

        # ═══ LAYER 1: Phase-based base rate (BIO/PMC 2015-2023) ═══
        is_supplemental = any(w in full_text for w in ['sbla', 'snda', 'supplemental', 'label expansion'])

        if cat_type in ('PDUFA', 'NDA', 'BLA'):
            if is_supplemental:
                probability = 93
                factors.append('PoA base: sBLA/sNDA supplemental approval 93% (BIO 2015-2023)')
                confidence = 'High'
            else:
                probability = 85
                factors.append('PoA base: NDA/BLA first-cycle approval 85% (BIO 2015-2023)')
                confidence = 'Medium'
        elif cat_type == 'AdCom':
            probability = 75
            factors.append('PoA base: Advisory Committee → approval 75%')
            confidence = 'Medium'
        elif cat_type == 'Phase3':
            probability = 58
            factors.append('PoA base: Phase 3 → approval 58% (BIO 2015-2023)')
            confidence = 'Low'
            if 'pivotal' in full_text:
                probability = 62
                factors[-1] = 'PoA base: pivotal Phase 3 → approval 62%'
        elif cat_type == 'Phase2':
            probability = 15
            factors.append('PoA base: Phase 2 → approval 15% (BIO 2015-2023)')
            confidence = 'Low'
        elif cat_type == 'Phase1':
            probability = 6.7
            factors.append('PoA base: Phase 1 → approval 6.7% (BIO 2015-2023)')
            confidence = 'Low'
        else:
            probability = 50
            factors.append('No specific phase base rate')
            confidence = 'Low'

        # ═══ LAYER 2: Therapeutic area modifier ═══
        area_modifier_applied = False

        # For NDA/BLA stage — use NDA-specific area rates
        if cat_type in ('PDUFA', 'NDA', 'BLA') and not is_supplemental:
            for keyword, rate in NDA_APPROVAL_BY_AREA.items():
                if keyword == 'default':
                    continue
                if keyword in full_text:
                    diff = rate - 85  # difference from default NDA rate
                    if diff != 0:
                        probability = min(max(probability + diff, 10), 97)
                        area_name = keyword.replace('_', ' ').title()
                        factors.append(f'Therapeutic area ({area_name}): NDA approval {rate}% ({diff:+d}%)')
                        area_modifier_applied = True
                    break

        # For earlier phases — use overall LOA by area
        if not area_modifier_applied and cat_type in ('Phase1', 'Phase2', 'Phase3'):
            for keyword, loa in THERAPEUTIC_AREA_LOA.items():
                if keyword in full_text:
                    # Calculate the modifier relative to the generic phase rate
                    generic_loa = LOA_BY_PHASE.get(cat_type, 10)
                    if generic_loa > 0:
                        # Scale: if area LOA is 2x the average, bump probability
                        avg_loa = 7.0  # average across all areas
                        ratio = loa / avg_loa
                        modifier = int((ratio - 1.0) * 10)  # ±points
                        modifier = max(-10, min(10, modifier))
                        if modifier != 0:
                            probability = min(max(probability + modifier, 3), 97)
                            area_name = keyword.replace('_', ' ').title()
                            factors.append(f'Therapeutic area ({area_name}): LOA {loa}% — {"above" if modifier > 0 else "below"} avg ({modifier:+d}%)')
                    break

        # ═══ LAYER 3: Drug modality modifier ═══
        for modality, mod in MODALITY_MODIFIERS.items():
            if modality in full_text and mod != 0:
                probability = min(max(probability + mod, 3), 97)
                modality_name = modality.replace('_', ' ').title()
                factors.append(f'Drug modality ({modality_name}): {mod:+d}%')
                break

        # ═══ LAYER 4: FDA designations ═══
        if any(w in full_text for w in ['breakthrough']):
            probability = min(probability + 4, 97)
            factors.append('Breakthrough Therapy designation: +4%')
        elif any(w in full_text for w in ['priority review', 'priority']):
            probability = min(probability + 3, 97)
            factors.append('Priority Review: +3%')
        elif any(w in full_text for w in ['accelerated approval', 'accelerated']):
            probability = min(probability + 3, 97)
            factors.append('Accelerated Approval pathway: +3%')
        elif any(w in full_text for w in ['fast track']):
            probability = min(probability + 2, 97)
            factors.append('Fast Track designation: +2%')

        if any(w in full_text for w in ['orphan', 'rare disease', 'ultra-rare']):
            probability = min(probability + 4, 97)
            factors.append('Orphan drug designation: +4% (higher approval rate for rare diseases)')

        rare_indicators = ['mucopolysaccharidosis', 'phenylketonuria', 'achondroplasia',
                         'gaucher', 'menkes', 'leber', 'hunter syndrome', 'fabry', 'pompe']
        if any(r in full_text for r in rare_indicators):
            probability = min(probability + 3, 97)
            factors.append('Rare genetic disease: high unmet need (+3%)')

        established_drugs = ['keytruda', 'opdivo', 'dupixent', 'darzalex', 'palynziq',
                           'sarclisa', 'filspari', 'vyvgart', 'inqovi', 'sotyktu']
        if any(d in full_text for d in established_drugs):
            probability = min(probability + 4, 97)
            factors.append('Established drug — label extension (+4%)')

        # ═══ LAYER 5: REAL MARKET SIGNALS (Finviz data) ═══
        has_market_data = False

        # Analyst target price vs current
        try:
            target = float(fundamentals.get('target_price', '0'))
            price = float(fundamentals.get('price', '0'))
            if target > 0 and price > 0:
                upside = ((target - price) / price) * 100
                has_market_data = True
                if upside >= 40:
                    probability = min(probability + 5, 97)
                    factors.append(f'Analyst target ${target:.0f} (+{upside:.0f}% upside) — bullish (+5%)')
                elif upside >= 20:
                    probability = min(probability + 3, 97)
                    factors.append(f'Analyst target ${target:.0f} (+{upside:.0f}% upside) (+3%)')
                elif upside >= 5:
                    probability = min(probability + 1, 97)
                    factors.append(f'Analyst target ${target:.0f} (+{upside:.0f}% upside) (+1%)')
                elif upside < -15:
                    probability = max(probability - 5, 10)
                    factors.append(f'Analyst target ${target:.0f} ({upside:.0f}%) — bearish (-5%)')
                elif upside < -5:
                    probability = max(probability - 2, 10)
                    factors.append(f'Analyst target below price ({upside:.0f}%) (-2%)')
        except (ValueError, TypeError, AttributeError):
            pass

        # Analyst recommendation (1=Strong Buy → 5=Strong Sell)
        try:
            recom_val = float(fundamentals.get('analyst_recom_raw', '0'))
            if recom_val > 0:
                has_market_data = True
                if recom_val <= 1.5:
                    probability = min(probability + 3, 97)
                    factors.append(f'Analyst consensus: Strong Buy ({recom_val:.1f}/5) (+3%)')
                elif recom_val <= 2.2:
                    probability = min(probability + 2, 97)
                    factors.append(f'Analyst consensus: Buy ({recom_val:.1f}/5) (+2%)')
                elif recom_val >= 3.5:
                    probability = max(probability - 3, 10)
                    factors.append(f'Analyst consensus: Underperform ({recom_val:.1f}/5) (-3%)')
                elif recom_val >= 3.0:
                    probability = max(probability - 1, 10)
                    factors.append(f'Analyst consensus: Hold ({recom_val:.1f}/5) (-1%)')
        except (ValueError, TypeError, AttributeError):
            pass

        # Insider transactions
        try:
            insider_trans = float(fundamentals.get('insider_trans', '0').replace('%', ''))
            if insider_trans != 0:
                has_market_data = True
                if insider_trans > 10:
                    probability = min(probability + 4, 97)
                    factors.append(f'Insider buying +{insider_trans:.0f}% — strong bullish (+4%)')
                elif insider_trans > 2:
                    probability = min(probability + 2, 97)
                    factors.append(f'Insider buying +{insider_trans:.0f}% (+2%)')
                elif insider_trans < -15:
                    probability = max(probability - 4, 10)
                    factors.append(f'Heavy insider selling {insider_trans:.0f}% (-4%)')
                elif insider_trans < -5:
                    probability = max(probability - 2, 10)
                    factors.append(f'Insider selling {insider_trans:.0f}% (-2%)')
        except (ValueError, TypeError, AttributeError):
            pass

        # Institutional flow
        try:
            inst_trans = float(fundamentals.get('inst_trans', '0').replace('%', ''))
            if inst_trans != 0:
                has_market_data = True
                if inst_trans > 10:
                    probability = min(probability + 3, 97)
                    factors.append(f'Institutions accumulating +{inst_trans:.0f}% (+3%)')
                elif inst_trans > 3:
                    probability = min(probability + 1, 97)
                    factors.append(f'Institutional buying +{inst_trans:.0f}% (+1%)')
                elif inst_trans < -10:
                    probability = max(probability - 3, 10)
                    factors.append(f'Institutions exiting {inst_trans:.0f}% (-3%)')
                elif inst_trans < -3:
                    probability = max(probability - 1, 10)
                    factors.append(f'Institutional selling {inst_trans:.0f}% (-1%)')
        except (ValueError, TypeError, AttributeError):
            pass

        # Monthly stock performance
        try:
            perf_month = float(fundamentals.get('perf_month', '0').replace('%', ''))
            if abs(perf_month) >= 5:
                has_market_data = True
                if perf_month >= 20:
                    probability = min(probability + 3, 97)
                    factors.append(f'Stock +{perf_month:.0f}% this month — market pricing in approval (+3%)')
                elif perf_month >= 10:
                    probability = min(probability + 1, 97)
                    factors.append(f'Stock +{perf_month:.0f}% this month (+1%)')
                elif perf_month <= -20:
                    probability = max(probability - 4, 10)
                    factors.append(f'Stock {perf_month:.0f}% this month — market concerned (-4%)')
                elif perf_month <= -10:
                    probability = max(probability - 2, 10)
                    factors.append(f'Stock {perf_month:.0f}% this month (-2%)')
        except (ValueError, TypeError, AttributeError):
            pass

        # ═══ CONFIDENCE ═══
        if has_market_data and len(sources) >= 2:
            confidence = 'High'
        elif has_market_data or len(sources) >= 2:
            confidence = 'Medium'
        else:
            confidence = 'Low'

        if len(sources) >= 2:
            factors.append(f'Confirmed by {len(sources)} independent sources')

        # Round probability
        probability = int(round(min(max(probability, 3), 97)))

        return {
            'probability': probability,
            'confidence': confidence,
            'factors': factors,
        }

    def _calculate_catalyst_score(self, event: Dict) -> int:
        """
        Trading Opportunity Score (0-100) — how attractive is this as a trade.

        Based on REAL Finviz data:
        - Timing: how close is the catalyst (closer = more actionable)
        - Volatility potential: ATR, beta, short squeeze setup
        - Volume & liquidity: can you trade it effectively
        - Institutional signal: smart money positioning
        - Analyst consensus: Wall Street sentiment
        - Market confirmation: multiple sources, recent momentum

        This is NOT approval probability — it's "how tradeable and interesting is this event."
        """
        score = 0
        factors = []
        fundamentals = event.get('fundamentals', {})

        # ═══ 1. TIMING (0-20 pts) — closer catalyst = more urgent trade setup ═══
        days = event.get('days_until')
        if days is not None:
            if days == 0:
                score += 20; factors.append('Catalyst TODAY (+20)')
            elif 1 <= days <= 3:
                score += 18; factors.append(f'Catalyst in {days}d — imminent (+18)')
            elif 4 <= days <= 7:
                score += 15; factors.append(f'Catalyst this week (+15)')
            elif 8 <= days <= 14:
                score += 12; factors.append(f'Catalyst in ~2 weeks (+12)')
            elif 15 <= days <= 30:
                score += 8; factors.append(f'Catalyst this month (+8)')
            elif 31 <= days <= 60:
                score += 4; factors.append(f'Catalyst in {days}d (+4)')
            elif days < 0:
                score += max(0, 3 - abs(days) // 7)
        else:
            score += 2

        # ═══ 2. VOLATILITY SETUP (0-20 pts) — real ATR, beta, short squeeze ═══
        # ATR — Average True Range (actual daily $ movement)
        atr_str = fundamentals.get('atr', '')
        price_str = fundamentals.get('price', '')
        try:
            atr = float(atr_str)
            price = float(price_str)
            if price > 0:
                atr_pct = (atr / price) * 100  # ATR as % of price
                if atr_pct >= 5:
                    score += 8; factors.append(f'High ATR {atr_pct:.1f}% — volatile (+8)')
                elif atr_pct >= 3:
                    score += 6; factors.append(f'ATR {atr_pct:.1f}% (+6)')
                elif atr_pct >= 2:
                    score += 4; factors.append(f'ATR {atr_pct:.1f}% (+4)')
                elif atr_pct >= 1:
                    score += 2
        except (ValueError, TypeError, AttributeError):
            pass

        # Beta — sensitivity to market
        beta_str = fundamentals.get('beta', '')
        try:
            beta = float(beta_str)
            if beta >= 2.0:
                score += 4; factors.append(f'High beta {beta:.1f} (+4)')
            elif beta >= 1.5:
                score += 3
            elif beta >= 1.0:
                score += 1
        except (ValueError, TypeError, AttributeError):
            pass

        # Short float — squeeze potential
        short_float_str = fundamentals.get('short_float', '')
        try:
            short_float = float(short_float_str.replace('%', ''))
            if short_float >= 20:
                score += 8; factors.append(f'Short squeeze setup: {short_float:.0f}% short (+8)')
            elif short_float >= 15:
                score += 6; factors.append(f'High short interest: {short_float:.0f}% (+6)')
            elif short_float >= 10:
                score += 4; factors.append(f'Elevated short: {short_float:.0f}% (+4)')
            elif short_float >= 5:
                score += 2
        except (ValueError, TypeError, AttributeError):
            pass

        # ═══ 3. VOLUME & LIQUIDITY (0-15 pts) — can you trade it ═══
        rel_vol_str = fundamentals.get('rel_volume', '')
        try:
            rel_vol = float(rel_vol_str)
            if rel_vol >= 3.0:
                score += 8; factors.append(f'Unusual volume {rel_vol:.1f}x (+8)')
            elif rel_vol >= 2.0:
                score += 6; factors.append(f'Volume surge {rel_vol:.1f}x (+6)')
            elif rel_vol >= 1.5:
                score += 4; factors.append(f'Above-avg volume {rel_vol:.1f}x (+4)')
            elif rel_vol >= 1.0:
                score += 2
        except (ValueError, TypeError):
            pass

        # Average volume — liquidity check
        avg_vol_str = fundamentals.get('avg_volume', '')
        try:
            avg_vol_clean = avg_vol_str.replace(',', '').replace('K', '000').replace('M', '000000')
            avg_vol = float(avg_vol_clean)
            if avg_vol >= 2_000_000:
                score += 5; factors.append('High liquidity 2M+ avg vol (+5)')
            elif avg_vol >= 500_000:
                score += 4; factors.append('Good liquidity (+4)')
            elif avg_vol >= 100_000:
                score += 2
            else:
                factors.append('Low liquidity — caution')
        except (ValueError, TypeError, AttributeError):
            pass

        # Gap — already moving pre-market
        gap_str = fundamentals.get('gap_pct', '')
        try:
            gap = abs(float(gap_str.replace('%', '')))
            if gap >= 5:
                score += 2; factors.append(f'Gap {gap_str} pre-market (+2)')
        except (ValueError, TypeError, AttributeError):
            pass

        # ═══ 4. INSTITUTIONAL SIGNAL (0-15 pts) — smart money ═══
        # Institutional ownership (higher = more analyst coverage, stable)
        inst_own_str = fundamentals.get('inst_own', '')
        try:
            inst_own = float(inst_own_str.replace('%', ''))
            if inst_own >= 80:
                score += 6; factors.append(f'Strong inst. ownership {inst_own:.0f}% (+6)')
            elif inst_own >= 50:
                score += 4; factors.append(f'Inst. ownership {inst_own:.0f}% (+4)')
            elif inst_own >= 20:
                score += 2
        except (ValueError, TypeError, AttributeError):
            pass

        # Insider transactions — are insiders buying ahead of catalyst?
        insider_trans_str = fundamentals.get('insider_trans', '')
        try:
            insider_trans = float(insider_trans_str.replace('%', ''))
            if insider_trans > 5:
                score += 5; factors.append(f'Insider BUYING +{insider_trans:.0f}% (+5)')
            elif insider_trans > 0:
                score += 3; factors.append(f'Insider buying +{insider_trans:.0f}% (+3)')
            elif insider_trans < -10:
                score -= 2; factors.append(f'Insider selling {insider_trans:.0f}% (-2)')
        except (ValueError, TypeError, AttributeError):
            pass

        # Institutional transactions — smart money flow
        inst_trans_str = fundamentals.get('inst_trans', '')
        try:
            inst_trans = float(inst_trans_str.replace('%', ''))
            if inst_trans > 5:
                score += 4; factors.append(f'Institutions accumulating +{inst_trans:.0f}% (+4)')
            elif inst_trans > 0:
                score += 2
            elif inst_trans < -5:
                score -= 1; factors.append(f'Institutions reducing {inst_trans:.0f}% (-1)')
        except (ValueError, TypeError, AttributeError):
            pass

        # ═══ 5. ANALYST & TARGET (0-15 pts) — Wall Street view ═══
        recom_raw = fundamentals.get('analyst_recom_raw', '')
        try:
            recom_val = float(recom_raw)
            # Finviz: 1.0 = Strong Buy, 2.0 = Buy, 3.0 = Hold, 4.0 = Sell, 5.0 = Strong Sell
            if recom_val <= 1.5:
                score += 8; factors.append(f'Analyst: Strong Buy ({recom_val:.1f}) (+8)')
            elif recom_val <= 2.0:
                score += 6; factors.append(f'Analyst: Buy ({recom_val:.1f}) (+6)')
            elif recom_val <= 2.5:
                score += 4; factors.append(f'Analyst: Outperform ({recom_val:.1f}) (+4)')
            elif recom_val <= 3.0:
                score += 2
            elif recom_val > 3.5:
                score -= 2; factors.append(f'Analyst: Underperform ({recom_val:.1f}) (-2)')
        except (ValueError, TypeError, AttributeError):
            # Fallback to text
            recom = fundamentals.get('analyst_recom', '')
            if 'Strong Buy' in recom:
                score += 8
            elif 'Buy' in recom:
                score += 6
            elif 'Hold' in recom:
                score += 2

        # Target price upside
        try:
            target = float(fundamentals.get('target_price', '0'))
            price = float(fundamentals.get('price', '0'))
            if target > 0 and price > 0:
                upside = ((target - price) / price) * 100
                if upside >= 30:
                    score += 7; factors.append(f'Target ${target:.0f} — {upside:.0f}% upside (+7)')
                elif upside >= 15:
                    score += 5; factors.append(f'Target ${target:.0f} — {upside:.0f}% upside (+5)')
                elif upside >= 5:
                    score += 3; factors.append(f'Target ${target:.0f} — {upside:.0f}% upside (+3)')
                elif upside < -10:
                    score -= 2; factors.append(f'Target ${target:.0f} — {abs(upside):.0f}% downside (-2)')
        except (ValueError, TypeError, AttributeError):
            pass

        # ═══ 6. CONFIRMATION (0-15 pts) — data quality + momentum ═══
        # Multiple source confirmation
        sources = event.get('sources', [])
        if len(sources) >= 3:
            score += 6; factors.append(f'Confirmed by {len(sources)} independent sources (+6)')
        elif len(sources) >= 2:
            score += 4; factors.append(f'Confirmed by {len(sources)} sources (+4)')
        else:
            score += 1

        # Catalyst type importance
        cat_type = event.get('catalyst_type', '')
        type_bonus = {'PDUFA': 5, 'Approval': 4, 'AdCom': 4, 'NDA': 3, 'BLA': 3, 'CRL': 3}
        t_bonus = type_bonus.get(cat_type, 0)
        if t_bonus:
            score += t_bonus

        # Recent performance — momentum going into catalyst
        perf_week_str = fundamentals.get('perf_week', '')
        try:
            perf_week = float(perf_week_str.replace('%', ''))
            if abs(perf_week) >= 10:
                score += 4; factors.append(f'Week perf {perf_week:+.1f}% — active (+4)')
            elif abs(perf_week) >= 5:
                score += 2
        except (ValueError, TypeError, AttributeError):
            pass

        event['score_factors'] = factors
        return max(0, min(100, score))

    # ═══════════════════════════════════════════════════════════
    # FDA MOVERS — Track historical catalyst stock movements
    # ═══════════════════════════════════════════════════════════

    async def get_fda_movers(self, days_back: int = 30) -> List[Dict]:
        """
        Track stocks that recently had FDA catalysts and how they moved.
        Uses yfinance to get price data around catalyst dates.
        Returns list of movers with: ticker, date, catalyst_type, move%, volume change, analysis.
        """
        # Get events including past ones
        events = await self.get_catalyst_events(days_forward=90, days_back=days_back, enriched=True)

        # Filter to past events only, deduplicate by (ticker, date)
        past_events = [e for e in events if e.get('days_until') is not None and e.get('days_until') < 0]
        seen_keys = set()
        unique_past = []
        for e in past_events:
            key = (e.get('ticker', ''), e.get('catalyst_date', ''))
            if key not in seen_keys:
                seen_keys.add(key)
                unique_past.append(e)

        if not unique_past:
            return []

        # Fetch price data for past events
        sem = asyncio.Semaphore(3)
        movers = []

        async def analyze_mover(event: Dict):
            async with sem:
                ticker = event.get('ticker', '')
                catalyst_date = event.get('catalyst_date', '')
                if not ticker or not catalyst_date:
                    return None

                try:
                    loop = asyncio.get_event_loop()
                    result = await asyncio.wait_for(
                        loop.run_in_executor(
                            self._yf_executor,
                            self._get_mover_data_sync,
                            ticker,
                            catalyst_date
                        ),
                        timeout=6
                    )
                    if result:
                        result['ticker'] = ticker
                        result['catalyst_date'] = catalyst_date
                        result['catalyst_type'] = event.get('catalyst_type', '')
                        result['drug_name'] = event.get('drug_name', '')
                        result['indication'] = event.get('indication', '')
                        result['company'] = event.get('company', '')
                        result['status'] = event.get('status', '')
                        result['approval_probability'] = event.get('approval_probability', {})
                        result['fundamentals'] = event.get('fundamentals', {})
                        return result
                except (asyncio.TimeoutError, Exception):
                    pass
                return None

        tasks = [analyze_mover(e) for e in unique_past[:15]]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, dict) and r:
                movers.append(r)

        # Sort by absolute move size
        movers.sort(key=lambda x: abs(x.get('catalyst_day_move', 0)), reverse=True)
        return movers

    def _get_mover_data_sync(self, ticker: str, catalyst_date: str) -> Optional[Dict]:
        """Get price movement data around a catalyst date."""
        try:
            cat_dt = datetime.strptime(catalyst_date, '%Y-%m-%d')
            start = cat_dt - timedelta(days=10)
            end = min(cat_dt + timedelta(days=5), datetime.now())

            stock = yf.Ticker(ticker)
            hist = stock.history(start=start.strftime('%Y-%m-%d'),
                               end=end.strftime('%Y-%m-%d'),
                               timeout=5)

            if hist.empty or len(hist) < 3:
                return None

            # Find the catalyst day or nearest trading day
            cat_date_str = cat_dt.strftime('%Y-%m-%d')
            hist.index = hist.index.tz_localize(None)

            # Find nearest trading day to catalyst
            closest_idx = None
            min_diff = 999
            for i, dt in enumerate(hist.index):
                diff = abs((dt - cat_dt).days)
                if diff < min_diff:
                    min_diff = diff
                    closest_idx = i

            if closest_idx is None or closest_idx == 0:
                return None

            # Catalyst day data
            cat_day = hist.iloc[closest_idx]
            prev_day = hist.iloc[closest_idx - 1]

            # Day move
            cat_day_move = ((cat_day['Close'] - prev_day['Close']) / prev_day['Close']) * 100

            # Gap (open vs prev close)
            gap_pct = ((cat_day['Open'] - prev_day['Close']) / prev_day['Close']) * 100

            # Intraday range
            intraday_range = ((cat_day['High'] - cat_day['Low']) / cat_day['Low']) * 100

            # Volume change
            avg_vol = hist.iloc[:closest_idx]['Volume'].mean() if closest_idx > 0 else 1
            vol_ratio = cat_day['Volume'] / avg_vol if avg_vol > 0 else 1

            # Week move (from 5 days before to catalyst day)
            week_start_idx = max(0, closest_idx - 5)
            week_move = ((cat_day['Close'] - hist.iloc[week_start_idx]['Close']) / hist.iloc[week_start_idx]['Close']) * 100

            # Post-catalyst move (if data available)
            post_move = 0
            if closest_idx + 1 < len(hist):
                last_available = hist.iloc[-1]
                post_move = ((last_available['Close'] - cat_day['Close']) / cat_day['Close']) * 100

            # Classify the move
            analysis = self._analyze_mover(cat_day_move, gap_pct, vol_ratio, intraday_range)

            return {
                'catalyst_day_move': round(cat_day_move, 2),
                'gap_pct': round(gap_pct, 2),
                'intraday_range': round(intraday_range, 2),
                'volume_ratio': round(vol_ratio, 1),
                'week_move': round(week_move, 2),
                'post_catalyst_move': round(post_move, 2),
                'price_before': round(prev_day['Close'], 2),
                'price_after': round(cat_day['Close'], 2),
                'analysis': analysis,
            }
        except Exception as e:
            print(f"Mover data error {ticker}: {e}")
            return None

    def _analyze_mover(self, day_move: float, gap: float, vol_ratio: float, intraday: float) -> Dict:
        """Analyze the type of catalyst move for trading insights."""
        move_type = 'neutral'
        signals = []

        if day_move >= 20:
            move_type = 'massive_up'
            signals.append('Massive approval/positive data move')
        elif day_move >= 10:
            move_type = 'strong_up'
            signals.append('Strong positive catalyst reaction')
        elif day_move >= 5:
            move_type = 'moderate_up'
            signals.append('Moderate positive reaction')
        elif day_move <= -20:
            move_type = 'massive_down'
            signals.append('Massive rejection/negative data')
        elif day_move <= -10:
            move_type = 'strong_down'
            signals.append('Strong negative catalyst reaction')
        elif day_move <= -5:
            move_type = 'moderate_down'
            signals.append('Moderate negative reaction')
        else:
            move_type = 'muted'
            signals.append('Muted reaction — already priced in')

        # Gap analysis
        if abs(gap) >= 10:
            signals.append(f'Large gap {"up" if gap > 0 else "down"} {gap:+.1f}% — news broke pre-market')
        elif abs(gap) >= 5:
            signals.append(f'Gap {"up" if gap > 0 else "down"} {gap:+.1f}%')

        # Volume analysis
        if vol_ratio >= 5:
            signals.append(f'Extreme volume {vol_ratio:.0f}x normal — heavy participation')
        elif vol_ratio >= 3:
            signals.append(f'Very high volume {vol_ratio:.0f}x normal')
        elif vol_ratio >= 2:
            signals.append(f'High volume {vol_ratio:.1f}x normal')

        # Intraday range
        if intraday >= 15:
            signals.append(f'Huge intraday range {intraday:.0f}% — extreme volatility')
        elif intraday >= 10:
            signals.append(f'Wide intraday range {intraday:.0f}%')

        # Trading takeaways (Hebrew — actionable insights)
        takeaways = []
        if move_type in ('massive_up', 'strong_up') and abs(gap) >= 5:
            takeaways.append('Gap-and-Go — התנועה קרתה בפרה-מרקט. כניסה הייתה רק לפני הפתיחה')
        if move_type in ('massive_up', 'strong_up') and vol_ratio >= 3:
            takeaways.append('מוסדיים השתתפו — נפח גבוה מעיד על תנועה של "כסף חכם"')
        if move_type in ('massive_up', 'strong_up') and vol_ratio < 2:
            takeaways.append('תנועה חזקה בנפח נמוך — ייתכן עם יותר מחזור התנועה תימשך')
        if move_type in ('massive_down', 'strong_down'):
            takeaways.append('אירוע בינארי — חובה סטופ לוס לפני תאריכי PDUFA')
        if move_type in ('massive_down', 'strong_down') and abs(gap) >= 10:
            takeaways.append('ירידה חדה בגאפ — לא הייתה אפשרות לצאת. זהו הסיכון של FDA plays')
        if move_type == 'muted' and vol_ratio < 2:
            takeaways.append('השוק כבר תמחר — ללא הפתעה אין תנועה משמעותית')
        if move_type == 'muted' and vol_ratio >= 2:
            takeaways.append('נפח גבוה בלי תנועה — ייתכן שהתנועה תגיע בימים הבאים')
        if move_type in ('moderate_up', 'moderate_down'):
            takeaways.append('תגובה מתונה — ייתכן שהתנועה המלאה עדיין לא הסתיימה')
        if day_move >= 10 and intraday >= 15:
            takeaways.append('טווח יומי רחב מאוד — הזדמנות למסחר תוך-יומי (day trade)')

        return {
            'move_type': move_type,
            'signals': signals,
            'takeaways': takeaways,
        }

    # ═══════════════════════════════════════════════════════════
    # TODAY'S BIOTECH MOVERS — Real-time scanner for moving healthcare stocks
    # ═══════════════════════════════════════════════════════════

    async def get_todays_biotech_movers(self) -> List[Dict]:
        """
        Scan for healthcare/biotech stocks moving significantly today.
        Cross-reference with FDA calendar to identify catalyst-driven moves.
        Returns list with: ticker, move%, reason, stage, fundamentals.
        """
        import aiohttp
        from bs4 import BeautifulSoup

        # Get FDA events for cross-referencing
        fda_events = await self.get_catalyst_events(days_forward=90, days_back=7, enriched=False)
        fda_map = {}
        for e in fda_events:
            t = e.get('ticker', '')
            if t:
                fda_map[t] = e

        # Scan Finviz for healthcare movers
        filters_up = 'sec_healthcaretechnology,sec_healthcare,ta_change_u3,sh_avgvol_o200,sh_price_o2'
        filters_down = 'sec_healthcaretechnology,sec_healthcare,ta_change_d3,sh_avgvol_o200,sh_price_o2'

        all_movers = []

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html',
        }
        if self.finviz_fundamentals.cookie:
            headers['Cookie'] = self.finviz_fundamentals.cookie

        use_elite = bool(self.finviz_fundamentals.cookie)
        base_url = 'https://elite.finviz.com/screener.ashx' if use_elite else 'https://finviz.com/screener.ashx'

        async def scan_direction(filters: str, direction: str):
            results = []
            url = f"{base_url}?v=111&f={filters}&o={'change' if direction == 'down' else '-change'}"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                        if resp.status != 200:
                            return results
                        html = await resp.text()
                        soup = BeautifulSoup(html, 'html.parser')

                        table = soup.find('table', class_='table-light')
                        if not table:
                            # Try alternative
                            tables = soup.find_all('table')
                            for t in tables:
                                if t.find('td', string=lambda s: s and '%' in str(s)):
                                    table = t
                                    break

                        if not table:
                            return results

                        rows = table.find_all('tr')[1:]  # skip header
                        for row in rows[:30]:
                            cells = row.find_all('td')
                            if len(cells) < 10:
                                continue
                            try:
                                ticker = cells[1].get_text(strip=True)
                                company = cells[2].get_text(strip=True)
                                sector = cells[3].get_text(strip=True) if len(cells) > 3 else ''
                                industry = cells[4].get_text(strip=True) if len(cells) > 4 else ''
                                market_cap = cells[6].get_text(strip=True) if len(cells) > 6 else ''
                                price = cells[8].get_text(strip=True) if len(cells) > 8 else ''
                                change = cells[9].get_text(strip=True) if len(cells) > 9 else ''
                                volume = cells[10].get_text(strip=True) if len(cells) > 10 else ''

                                if not ticker or ticker in {'FDA', 'SEC', 'CEO', 'No.', 'Ticker'}:
                                    continue
                                # Skip non-ticker values (row numbers, headers)
                                if not ticker.isalpha() or len(ticker) > 5:
                                    continue

                                # Validate that change looks like a number (skip header rows)
                                change_clean = change.replace('%', '').replace('+', '').replace(',', '').strip()
                                try:
                                    float(change_clean)
                                except ValueError:
                                    continue

                                results.append({
                                    'ticker': ticker,
                                    'company': company,
                                    'sector': sector,
                                    'industry': industry,
                                    'market_cap': market_cap,
                                    'price': price,
                                    'change_pct': change,
                                    'volume': volume,
                                    'direction': direction,
                                })
                            except (IndexError, AttributeError):
                                continue
            except Exception as e:
                print(f"Biotech scan error ({direction}): {e}")
            return results

        # Scan both directions in parallel
        up_results, down_results = await asyncio.gather(
            scan_direction(filters_up, 'up'),
            scan_direction(filters_down, 'down'),
        )

        # Merge
        seen = set()
        for item in up_results + down_results:
            ticker = item['ticker']
            if ticker in seen:
                continue
            seen.add(ticker)

            # Cross-reference with FDA calendar
            fda_event = fda_map.get(ticker)
            if fda_event:
                item['has_fda_catalyst'] = True
                item['catalyst_type'] = fda_event.get('catalyst_type', '')
                item['catalyst_date'] = fda_event.get('catalyst_date', '')
                item['days_until'] = fda_event.get('days_until')
                item['drug_name'] = fda_event.get('drug_name', '')
                item['indication'] = fda_event.get('indication', '')
                item['phase'] = fda_event.get('phase', '')
                item['approval_probability'] = fda_event.get('approval_probability', {})
                item['status'] = fda_event.get('status', '')
            else:
                item['has_fda_catalyst'] = False

            # Determine reason for move
            item['move_reason'] = self._classify_biotech_move(item, fda_event)

            all_movers.append(item)

        # Sort: FDA catalyst movers first, then by absolute change
        all_movers.sort(key=lambda x: (
            -int(x.get('has_fda_catalyst', False)),
            -abs(float(str(x.get('change_pct', '0')).replace('%', '').replace('+', '') or '0'))
        ))

        return all_movers

    def _classify_biotech_move(self, mover: Dict, fda_event: Optional[Dict]) -> Dict:
        """Classify why a biotech stock is moving today."""
        change_str = str(mover.get('change_pct', '0')).replace('%', '').replace('+', '')
        try:
            change = float(change_str)
        except ValueError:
            change = 0

        reasons = []
        reason_he = []

        if fda_event:
            days = fda_event.get('days_until')
            cat_type = fda_event.get('catalyst_type', '')
            status = (fda_event.get('status') or '').lower()

            if days is not None and days == 0:
                reasons.append(f'{cat_type} decision TODAY')
                reason_he.append(f'החלטת {cat_type} היום!')
            elif days is not None and 1 <= days <= 7:
                reasons.append(f'{cat_type} in {days} days — pre-catalyst positioning')
                reason_he.append(f'{cat_type} בעוד {days} ימים — מיצוב לפני האירוע')
            elif days is not None and days < 0 and days >= -3:
                reasons.append(f'Post-{cat_type} reaction (was {abs(days)}d ago)')
                reason_he.append(f'תגובה אחרי {cat_type} ({abs(days)} ימים)')
            elif 'approved' in status:
                reasons.append('FDA approval announced')
                reason_he.append('אישור FDA פורסם')
            elif 'crl' in status or 'rejected' in status:
                reasons.append('CRL / Rejection')
                reason_he.append('מכתב תגובה / דחייה')
            else:
                reasons.append(f'Has upcoming {cat_type} catalyst')
                reason_he.append(f'קטליסט {cat_type} קרוב')

        # General move classification
        if abs(change) >= 20:
            reasons.append('Massive move — likely binary event')
            reason_he.append('תנועה מסיבית — כנראה אירוע בינארי')
        elif abs(change) >= 10:
            reasons.append('Major catalyst reaction')
            reason_he.append('תגובה משמעותית לאירוע')

        industry = (mover.get('industry') or '').lower()
        if 'biotech' in industry:
            if not fda_event:
                reasons.append('Biotech — possible data readout or partnership')
                reason_he.append('ביוטק — ייתכן נתונים קליניים או שיתוף פעולה')
        elif 'drug' in industry or 'pharma' in industry:
            if not fda_event:
                reasons.append('Pharma — possible regulatory or earnings')
                reason_he.append('פארמה — ייתכן רגולטורי או דוחות')

        if not reasons:
            reasons.append('Healthcare sector momentum')
            reason_he.append('מומנטום בסקטור הבריאות')

        return {
            'reasons_en': reasons,
            'reasons_he': reason_he,
        }
