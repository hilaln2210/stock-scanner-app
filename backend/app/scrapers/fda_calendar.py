"""
FDA Calendar Scraper — Aggregates biotech catalyst data from multiple sources.

Sources:
1. BioPharmCatalyst (try __NEXT_DATA__ JSON, fallback HTML)
2. RTTNews FDA Calendar (server-rendered HTML)
3. Drugs.com New Drug Approvals
4. ClinicalTrials.gov API (Phase 3 trials)
5. CheckRare Orphan Drug PDUFA dates
6. FDATracker.com Standard FDA Calendar

Merges & deduplicates by (ticker, catalyst_date, catalyst_type).
Cache TTL: 15 minutes (FDA data changes infrequently).
"""

import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import re
import asyncio
import json
import time


# ─── Comprehensive company-to-ticker mapping ────────────────────────────
COMPANY_TICKER_MAP = {
    # Big Pharma
    'pfizer': 'PFE', 'moderna': 'MRNA', 'johnson & johnson': 'JNJ',
    'janssen': 'JNJ', 'merck': 'MRK', 'eli lilly': 'LLY', 'lilly': 'LLY',
    'abbvie': 'ABBV', 'amgen': 'AMGN', 'gilead': 'GILD',
    'regeneron': 'REGN', 'vertex': 'VRTX', 'biogen': 'BIIB',
    'bristol-myers': 'BMY', 'bristol myers': 'BMY', 'bms': 'BMY',
    'astrazeneca': 'AZN', 'novartis': 'NVS', 'roche': 'RHHBY',
    'genentech': 'RHHBY', 'sanofi': 'SNY', 'novo nordisk': 'NVO',
    'bayer': 'BAYRY', 'gsk': 'GSK', 'glaxosmithkline': 'GSK',
    'takeda': 'TAK', 'astellas': 'ALPMY', 'daiichi sankyo': 'DSNKY',
    'boehringer': 'BAMXF', 'celgene': 'BMY', 'alexion': 'AZN',
    # Mid-cap biotech
    'illumina': 'ILMN', 'incyte': 'INCY', 'jazz': 'JAZZ',
    'biomarin': 'BMRN', 'bluebird': 'BLUE', 'crispr': 'CRSP',
    'intellia': 'NTLA', 'editas': 'EDIT', 'alnylam': 'ALNY',
    'seagen': 'PFE', 'ionis': 'IONS', 'neurocrine': 'NBIX',
    'sarepta': 'SRPT', 'ultragenyx': 'RARE', 'halozyme': 'HALO',
    'exact sciences': 'EXAS', 'guardant': 'GH',
    'argenx': 'ARGX', 'revolution': 'RVMD', 'karuna': 'BMY',
    # Additional biotech (from CheckRare, FDATracker, RTTNews)
    'regenxbio': 'RGNX', 'vanda': 'VNDA', 'eton': 'ETON',
    'ascendis': 'ASND', 'rocket': 'RCKT', 'lantheus': 'LNTH',
    'denali': 'DNLI', 'travere': 'TVTX', 'viridian': 'VRDN',
    'vera therapeutics': 'VERA', 'pharmaessentia': 'DRGX',
    'nuvalent': 'NUVL', 'inovio': 'INO', 'summit': 'SMMT',
    'atara': 'ATRA', 'taiho': 'TAIHY', 'otsuka': 'OTSKF',
    'camurus': 'CAMX', 'xspray': 'XSPRF',
    # Gene/cell therapy
    'bluebird bio': 'BLUE', 'beam': 'BEAM', 'prime medicine': 'PRME',
    'verve': 'VERV', 'passage bio': 'PASG', 'solid bio': 'SLDB',
    'uniqure': 'QURE', 'abeona': 'ABEO',
    # Oncology-focused
    'exelixis': 'EXEL', 'arcus': 'RCUS', 'turning point': 'BMY',
    'mirati': 'BMY', 'relay': 'RLAY', 'revolution medicines': 'RVMD',
    'nurix': 'NRIX', 'kymera': 'KYMR',
    # Immunology
    'horizon': 'AMGN', 'prometheus': 'MRK', 'annexon': 'ANNX',
    'compass': 'CMPX', 'protagonist': 'PTGX',
    # Rare disease
    'alexion': 'AZN', 'pharming': 'PHAR', 'kiniksa': 'KNSA',
    'amicus': 'FOLD', 'insmed': 'INSM',
    # CNS
    'cerevel': 'ABBV', 'sage': 'SAGE', 'axsome': 'AXSM',
    'intra-cellular': 'ITCI', 'acadia': 'ACAD', 'minerva': 'MNVR',
    # Other
    'rigel': 'RIGL', 'catalyst bio': 'CPRX', 'amneal': 'AMRX',
    'teva': 'TEVA', 'mylan': 'VTRS', 'viatris': 'VTRS',
    'hikma': 'HKMPY', 'dr. reddy': 'RDY', 'sun pharma': 'SUNPHARMA',
    'cipla': 'CIPLA', 'lupin': 'LUPIN',
    'pierre fabre': 'PIERREF', 'chiesi': 'CHIESI',
    'immedica': 'IMMEDICA', 'sentynl': 'SENTYNL',
    # Additional biotech companies
    'protagonist': 'PTGX', 'tg therapeutics': 'TGTX',
    'rhythm': 'RYTM', 'intercept': 'ICPT', 'madrigal': 'MDGL',
    'soleno': 'SLNO', 'bridgebio': 'BBIO', 'spring': 'SPRB',
    'coherus': 'CHRS', 'puma': 'PBYI', 'agios': 'AGIO',
    'blueprint': 'BPMC', 'myriad': 'MYGN', 'natera': 'NTRA',
    'arrowhead': 'ARWR', 'dicerna': 'DRNA', 'stoke': 'STOK',
    'alector': 'ALEC', 'praxis': 'PRAX', 'cassava': 'SAVA',
    'annovis': 'ANVS', 'cortexyme': 'CRTX',
    'tarsus': 'TARS', 'aldeyra': 'ALDX', 'ocugen': 'OCGN',
    'inhibrx': 'INBX', 'arctus': 'ARCT', 'arcturus': 'ARCT',
    'aprea': 'APRE', 'imago': 'IMGO',
}


# Non-tradeable tickers (private companies, foreign-only, etc.)
NON_TRADEABLE_TICKERS = {
    'PIERREF', 'CHIESI', 'IMMEDICA', 'SENTYNL', 'BAMXF',
    'SUNPHARMA', 'CIPLA', 'LUPIN',  # India-only
}


# Common false-positive "tickers" to exclude
EXCLUDED_TICKERS = {
    'FDA', 'SEC', 'CEO', 'IPO', 'ETF', 'USA', 'USD', 'NDA', 'BLA', 'CRL',
    'THE', 'FOR', 'AND', 'NEW', 'ALL', 'NDS', 'SNDA', 'SBLA', 'PDUFA',
    'AML', 'NSCLC', 'AFRS', 'MPS', 'AML', 'EBV', 'PTLD', 'NET', 'NETS',
    'CML', 'ALL', 'AML', 'NHL', 'RCC', 'HCC', 'GBM', 'CLL', 'SLE', 'IBD',
    'PRE', 'NOT', 'ITS', 'MAY', 'DEC', 'JAN', 'FEB', 'MAR', 'APR', 'JUN',
    'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DNA', 'RNA', 'CDX', 'MDD', 'PKU',
    'GAD', 'OCD', 'ASD', 'IGA', 'TED', 'NETs',
}


class FDACalendarScraper:
    CACHE_TTL = 900  # 15 minutes

    SOURCE_NAMES = {
        'biopharmcatalyst': 'BioPharmCatalyst',
        'rttnews': 'RTTNews',
        'drugs_com': 'Drugs.com',
        'clinicaltrials_gov': 'ClinicalTrials.gov',
        'checkrare': 'CheckRare',
        'fdatracker': 'FDATracker',
    }

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        self._cache: List[Dict] = []
        self._cache_time: float = 0

    async def get_fda_events(self, days_forward: int = 90, days_back: int = 30) -> List[Dict]:
        """Main entry point. Returns cached data if fresh, otherwise scrapes all sources."""
        now = time.time()
        if self._cache and (now - self._cache_time) < self.CACHE_TTL:
            return self._cache

        tasks = [
            self._scrape_biopharmcatalyst(),
            self._scrape_rttnews_fda(),
            self._scrape_drugs_com(),
            self._scrape_clinicaltrials_gov(),
            self._scrape_checkrare(),
            self._scrape_fdatracker(),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        source_names = ['BioPharmCatalyst', 'RTTNews', 'Drugs.com', 'ClinicalTrials.gov', 'CheckRare', 'FDATracker']
        all_events = []
        for i, result in enumerate(results):
            if isinstance(result, list):
                all_events.extend(result)
                print(f"  FDA source {source_names[i]}: {len(result)} events")
            elif isinstance(result, Exception):
                print(f"  FDA source {source_names[i]} error: {result}")

        merged = self._merge_and_deduplicate(all_events)

        # Filter by date range
        now_date = datetime.now()
        start_date = now_date - timedelta(days=days_back)
        end_date = now_date + timedelta(days=days_forward)

        filtered = []
        for event in merged:
            try:
                event_date = datetime.strptime(event['catalyst_date'], '%Y-%m-%d')
                if start_date <= event_date <= end_date:
                    event['days_until'] = (event_date - now_date).days
                    filtered.append(event)
            except (ValueError, KeyError):
                event['days_until'] = None
                filtered.append(event)

        # Estimate approval probability for each event
        for event in filtered:
            event['approval_probability'] = self._estimate_approval_probability(event)

        # Sort: soonest future events first, then past events
        filtered.sort(key=lambda x: (
            0 if x.get('days_until') is not None and x['days_until'] >= 0 else 1,
            abs(x.get('days_until') or 9999)
        ))

        self._cache = filtered
        self._cache_time = time.time()
        print(f"FDA Calendar: {len(filtered)} total events (from {len(all_events)} raw)")
        return filtered

    # ─── Source 1: BioPharmCatalyst ──────────────────────────────────────

    async def _scrape_biopharmcatalyst(self) -> List[Dict]:
        """Scrape BioPharmCatalyst FDA calendar."""
        events = []
        url = "https://www.biopharmcatalyst.com/calendars/fda-calendar"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        print(f"BioPharmCatalyst returned {response.status}")
                        return events

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Try to find __NEXT_DATA__ or __NUXT__ embedded JSON
                    for script in soup.find_all('script', {'id': '__NEXT_DATA__'}):
                        try:
                            data = json.loads(script.string)
                            events.extend(self._parse_nextdata_biopharm(data))
                            if events:
                                return events
                        except (json.JSONDecodeError, TypeError):
                            pass

                    # Try NUXT data
                    for script in soup.find_all('script'):
                        if script.string and 'window.__NUXT__' in (script.string or ''):
                            try:
                                json_str = re.search(r'window\.__NUXT__\s*=\s*(.+?);\s*$', script.string, re.DOTALL)
                                if json_str:
                                    pass
                            except Exception:
                                pass

                    # Fallback: parse HTML tables
                    tables = soup.find_all('table')
                    for table in tables:
                        rows = table.find_all('tr')
                        header_row = rows[0] if rows else None
                        if not header_row:
                            continue

                        headers = [th.get_text(strip=True).lower() for th in header_row.find_all(['th', 'td'])]

                        for row in rows[1:]:
                            cells = row.find_all('td')
                            if len(cells) < 3:
                                continue
                            try:
                                event = self._parse_biopharm_row(cells, headers)
                                if event:
                                    events.append(event)
                            except Exception:
                                continue

                    # Also try div-based layouts
                    if not events:
                        events.extend(self._parse_biopharm_cards(soup))

        except Exception as e:
            print(f"BioPharmCatalyst error: {e}")

        return events

    def _parse_nextdata_biopharm(self, data: dict) -> List[Dict]:
        """Parse __NEXT_DATA__ JSON from BioPharmCatalyst."""
        events = []
        try:
            page_props = data.get('props', {}).get('pageProps', {})
            catalysts = page_props.get('catalysts', page_props.get('events', page_props.get('data', [])))

            if isinstance(catalysts, list):
                for cat in catalysts:
                    ticker = cat.get('ticker', cat.get('symbol', ''))
                    if not ticker:
                        company = cat.get('company', '')
                        m = re.search(r'\(([A-Z]{1,5})\)', company)
                        if m:
                            ticker = m.group(1)
                    if not ticker:
                        continue

                    events.append({
                        'ticker': ticker.upper(),
                        'company': cat.get('company', cat.get('companyName', '')),
                        'drug_name': cat.get('drug', cat.get('drugName', '')),
                        'indication': cat.get('indication', cat.get('disease', '')),
                        'catalyst_type': self._normalize_catalyst_type(cat.get('catalystType', cat.get('type', ''))),
                        'catalyst_date': self._parse_date(cat.get('date', cat.get('catalystDate', ''))),
                        'phase': cat.get('stage', cat.get('phase', '')),
                        'status': cat.get('status', 'Upcoming'),
                        'source': 'biopharmcatalyst',
                        'source_url': 'https://www.biopharmcatalyst.com/calendars/fda-calendar',
                    })
        except Exception as e:
            print(f"Error parsing BioPharmCatalyst NEXT_DATA: {e}")

        return events

    def _parse_biopharm_row(self, cells, headers) -> Optional[Dict]:
        """Parse a single table row from BioPharmCatalyst."""
        cell_texts = [c.get_text(strip=True) for c in cells]

        data = {}
        for i, h in enumerate(headers):
            if i < len(cell_texts):
                data[h] = cell_texts[i]

        ticker = data.get('ticker', data.get('symbol', ''))
        if not ticker:
            for cell in cells:
                link = cell.find('a')
                if link:
                    href = link.get('href', '')
                    m = re.search(r'/company/([A-Z]{1,5})', href, re.IGNORECASE)
                    if m:
                        ticker = m.group(1).upper()
                        break
                    text = link.get_text(strip=True)
                    if re.match(r'^[A-Z]{1,5}$', text):
                        ticker = text
                        break

        if not ticker:
            return None

        company = data.get('company', data.get('name', ''))
        drug = data.get('drug', data.get('drug name', ''))
        indication = data.get('indication', data.get('disease', ''))
        cat_type = data.get('catalyst', data.get('type', data.get('event', '')))
        date_str = data.get('date', data.get('pdufa date', data.get('target date', '')))
        phase = data.get('stage', data.get('phase', ''))
        status = data.get('status', 'Upcoming')

        return {
            'ticker': ticker.upper(),
            'company': company,
            'drug_name': drug,
            'indication': indication,
            'catalyst_type': self._normalize_catalyst_type(cat_type),
            'catalyst_date': self._parse_date(date_str),
            'phase': phase,
            'status': status,
            'source': 'biopharmcatalyst',
            'source_url': 'https://www.biopharmcatalyst.com/calendars/fda-calendar',
        }

    def _parse_biopharm_cards(self, soup) -> List[Dict]:
        """Parse card-based layout from BioPharmCatalyst."""
        events = []
        for card in soup.find_all(['div', 'article'], class_=lambda x: x and any(
            word in str(x).lower() for word in ['catalyst', 'event', 'calendar-item', 'row']
        )):
            try:
                text = card.get_text(' ', strip=True)
                ticker_match = re.search(r'\b([A-Z]{2,5})\b', text)
                if not ticker_match:
                    continue

                ticker = ticker_match.group(1)
                if ticker in EXCLUDED_TICKERS:
                    continue

                date_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\w+ \d{1,2},? \d{4})', text)
                date_str = date_match.group(1) if date_match else ''

                events.append({
                    'ticker': ticker,
                    'company': '',
                    'drug_name': '',
                    'indication': '',
                    'catalyst_type': self._detect_catalyst_type(text),
                    'catalyst_date': self._parse_date(date_str),
                    'phase': self._detect_phase(text),
                    'status': 'Upcoming',
                    'source': 'biopharmcatalyst',
                    'source_url': 'https://www.biopharmcatalyst.com/calendars/fda-calendar',
                })
            except Exception:
                continue
        return events

    # ─── Source 2: RTTNews ───────────────────────────────────────────────

    async def _scrape_rttnews_fda(self) -> List[Dict]:
        """Scrape RTTNews FDA Calendar — robust multi-strategy parsing."""
        events = []
        url = "https://www.rttnews.com/CorpInfo/FDACalendar.aspx"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        return events

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Strategy 1: Find main content area
                    main_div = (
                        soup.find('div', {'id': 'ctl00_cphBody_divContent'}) or
                        soup.find('div', class_='corpDiv') or
                        soup.find('div', {'id': 'corporateBody'}) or
                        soup.find('div', class_='eventCalendar') or
                        soup
                    )

                    # Strategy 2: Parse tables
                    events.extend(self._parse_rttnews_tables(main_div, url))

                    # Strategy 3: If tables didn't yield results, try text-based parsing
                    if not events:
                        events.extend(self._parse_rttnews_text(main_div, url))

                    # Strategy 4: Try all links with ticker patterns
                    if not events:
                        events.extend(self._parse_rttnews_links(soup, url))

        except Exception as e:
            print(f"RTTNews FDA error: {e}")

        return events

    def _parse_rttnews_tables(self, container, url: str) -> List[Dict]:
        """Parse RTTNews table-based layout."""
        events = []
        tables = container.find_all('table')

        for table in tables:
            rows = table.find_all('tr')
            current_date = ''

            for row in rows:
                cells = row.find_all('td')
                if not cells:
                    continue

                # Date header rows
                if len(cells) == 1:
                    date_text = cells[0].get_text(strip=True)
                    parsed = self._parse_date(date_text)
                    if parsed:
                        current_date = parsed
                    continue

                if len(cells) >= 2:
                    text = row.get_text(' ', strip=True)

                    ticker = ''
                    company = ''

                    # Extract ticker from parentheses in any cell
                    for cell in cells:
                        cell_text = cell.get_text(strip=True)
                        ticker_match = re.search(r'\(([A-Z]{1,5})\)', cell_text)
                        if ticker_match:
                            ticker = ticker_match.group(1)
                        link = cell.find('a')
                        if link:
                            href = link.get('href', '')
                            if '/Content/Company' in href or 'ticker' in href.lower():
                                company = link.get_text(strip=True)
                            # Also extract from link text
                            if not ticker:
                                link_text = link.get_text(strip=True)
                                tm = re.search(r'\(([A-Z]{1,5})\)', link_text)
                                if tm:
                                    ticker = tm.group(1)

                    # Fallback: search full row text
                    if not ticker:
                        ticker_match = re.search(r'\(([A-Z]{1,5})\)', text)
                        if ticker_match:
                            ticker = ticker_match.group(1)

                    # Try to find ticker from company name
                    if not ticker and company:
                        ticker = self._sponsor_to_ticker(company)

                    if not ticker:
                        continue

                    # Extract drug name and indication
                    drug_name = ''
                    indication = ''
                    for cell in cells:
                        cell_text = cell.get_text(strip=True)
                        if ' for ' in cell_text.lower() and not drug_name:
                            parts = re.split(r'\s+for\s+', cell_text, maxsplit=1, flags=re.IGNORECASE)
                            if len(parts) == 2:
                                drug_name = parts[0].strip()
                                indication = parts[1].strip()
                        elif not drug_name and any(kw in cell_text.lower() for kw in ['nda', 'bla', 'snda', 'sbla']):
                            drug_name = cell_text.strip()

                    # Extract date from row
                    date_in_row = ''
                    for cell in cells:
                        cell_text = cell.get_text(strip=True)
                        d = self._parse_date(cell_text)
                        if d:
                            date_in_row = d
                            break
                    # Also try to find date pattern in full text
                    if not date_in_row:
                        dm = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', text)
                        if dm:
                            date_in_row = self._parse_date(dm.group(1))

                    events.append({
                        'ticker': ticker.upper(),
                        'company': company,
                        'drug_name': drug_name[:200] if drug_name else '',
                        'indication': indication[:200] if indication else '',
                        'catalyst_type': self._detect_catalyst_type(text),
                        'catalyst_date': date_in_row or current_date,
                        'phase': self._detect_phase(text),
                        'status': self._detect_status(text),
                        'source': 'rttnews',
                        'source_url': url,
                    })

        return events

    def _parse_rttnews_text(self, container, url: str) -> List[Dict]:
        """
        Parse RTTNews text content. RTTNews now renders as multi-line text:
            CompanyName
            (
            TICKER
            )
            DrugName (NDA/BLA/sBLA)
            MM/DD/YYYY
            FDA decision on ... for ...
        """
        events = []
        text = container.get_text('\n', strip=True)
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        i = 0
        while i < len(lines) - 4:
            # Pattern: line[i] = company, line[i+1] = "(", line[i+2] = TICKER, line[i+3] = ")"
            if (lines[i + 1] == '(' and
                    lines[i + 3] == ')' and
                    re.match(r'^[A-Z]{1,6}(?:,\s*[A-Z.]{1,6})*$', lines[i + 2])):

                company = lines[i]
                # Handle multi-ticker like "SNYNF , SAN.PA" — take first
                ticker_raw = lines[i + 2].split(',')[0].strip()
                ticker = ticker_raw.replace('.', '')

                if ticker in EXCLUDED_TICKERS or len(ticker) > 5:
                    i += 4
                    continue

                # Look ahead for drug info, date, description
                drug_name = ''
                catalyst_date = ''
                indication = ''
                description = ''
                status = 'Upcoming'

                j = i + 4
                lookahead = min(j + 8, len(lines))
                while j < lookahead:
                    line = lines[j]

                    # Date line
                    d = self._parse_date(line)
                    if d and not catalyst_date and len(line) < 20:
                        catalyst_date = d
                        j += 1
                        continue

                    # Drug line with (NDA)/(BLA)/(sBLA)/(sNDA)
                    if re.search(r'\((s?NDA|s?BLA|ANDA)\s*\)', line) and not drug_name:
                        drug_name = re.sub(r'\s*\((s?NDA|s?BLA|ANDA)\s*\)', '', line).strip()
                        j += 1
                        continue

                    # FDA decision description
                    if line.lower().startswith('fda decision') or line.lower().startswith('fda approves'):
                        description = line
                        # Extract indication from "for ..." clause
                        parts = re.split(r'\s+for\s+', line, maxsplit=1, flags=re.IGNORECASE)
                        if len(parts) == 2:
                            indication = parts[1].strip()
                        j += 1
                        continue

                    # Status keywords
                    if line.lower() in ('pending', 'approved', 'under review'):
                        status = line.capitalize()
                        j += 1
                        continue

                    # Skip navigation/link lines
                    if line in ('-', 'Drug Status', 'Other Approvals', 'Outcome', 'Details'):
                        j += 1
                        continue

                    # FDA approval announcement
                    if 'FDA' in line and ('approv' in line.lower() or 'granted' in line.lower()):
                        description = line
                        status = 'Complete - Approved'
                        j += 1
                        continue

                    # If we hit the next company name (no parens, followed by "("), stop
                    if j + 2 < len(lines) and lines[j + 1] == '(':
                        break

                    j += 1

                cat_type = self._detect_catalyst_type(f"{drug_name} {description}")
                if cat_type == 'Other' and catalyst_date:
                    cat_type = 'PDUFA'

                events.append({
                    'ticker': ticker,
                    'company': company,
                    'drug_name': drug_name[:200],
                    'indication': indication[:200],
                    'catalyst_type': cat_type,
                    'catalyst_date': catalyst_date,
                    'phase': self._detect_phase(f"{drug_name} {description}"),
                    'status': status,
                    'source': 'rttnews',
                    'source_url': url,
                })

                i = j  # Skip past this event
                continue

            i += 1

        return events

    def _parse_rttnews_links(self, soup, url: str) -> List[Dict]:
        """Extract events from links and surrounding text (last resort)."""
        events = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if '/Content/Company' not in href:
                continue
            text = link.get_text(strip=True)
            ticker_match = re.search(r'\(([A-Z]{1,5})\)', text)
            if not ticker_match:
                parent = link.parent
                if parent:
                    parent_text = parent.get_text(strip=True)
                    ticker_match = re.search(r'\(([A-Z]{1,5})\)', parent_text)

            if ticker_match:
                ticker = ticker_match.group(1)
                parent_text = link.parent.get_text(' ', strip=True) if link.parent else ''
                date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', parent_text)
                date_str = self._parse_date(date_match.group(1)) if date_match else ''

                events.append({
                    'ticker': ticker,
                    'company': re.sub(r'\s*\([A-Z]+\)', '', text).strip(),
                    'drug_name': '',
                    'indication': '',
                    'catalyst_type': self._detect_catalyst_type(parent_text),
                    'catalyst_date': date_str,
                    'phase': self._detect_phase(parent_text),
                    'status': 'Upcoming',
                    'source': 'rttnews',
                    'source_url': url,
                })

        return events

    # ─── Source 3: Drugs.com ─────────────────────────────────────────────

    async def _scrape_drugs_com(self) -> List[Dict]:
        """Scrape Drugs.com new drug approvals."""
        events = []
        url = "https://www.drugs.com/newdrugs.html"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        return events

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    for article in soup.find_all(['div', 'article'], class_=lambda x: x and any(
                        word in str(x).lower() for word in ['drug-info', 'news-item', 'ddc-media-item']
                    )):
                        try:
                            title_elem = article.find(['h2', 'h3', 'h4', 'a'])
                            if not title_elem:
                                continue

                            title = title_elem.get_text(strip=True)
                            text = article.get_text(' ', strip=True)

                            drug_name = title.split(' (')[0] if ' (' in title else title.split(' - ')[0]

                            ticker = ''
                            ticker_match = re.search(r'\(([A-Z]{1,5})\)', text)
                            if ticker_match:
                                ticker = ticker_match.group(1)

                            date_match = re.search(r'(\w+ \d{1,2},? \d{4})', text)
                            date_str = date_match.group(1) if date_match else ''

                            indication = ''
                            ind_match = re.search(r'(?:for|treats?|treatment of)\s+(.+?)(?:\.|,|$)', text, re.IGNORECASE)
                            if ind_match:
                                indication = ind_match.group(1).strip()[:200]

                            link = article.find('a', href=True)
                            source_url = link['href'] if link else url
                            if source_url and not source_url.startswith('http'):
                                source_url = f"https://www.drugs.com{source_url}"

                            if drug_name:
                                events.append({
                                    'ticker': ticker,
                                    'company': '',
                                    'drug_name': drug_name[:200],
                                    'indication': indication,
                                    'catalyst_type': 'Approval',
                                    'catalyst_date': self._parse_date(date_str),
                                    'phase': 'Approved',
                                    'status': 'Complete',
                                    'source': 'drugs_com',
                                    'source_url': source_url,
                                })
                        except Exception:
                            continue

        except Exception as e:
            print(f"Drugs.com error: {e}")

        return events

    # ─── Source 4: ClinicalTrials.gov ────────────────────────────────────

    async def _scrape_clinicaltrials_gov(self) -> List[Dict]:
        """Query ClinicalTrials.gov API for Phase 3 biotech trials nearing completion."""
        events = []
        base_url = "https://clinicaltrials.gov/api/v2/studies"

        params = {
            'query.term': 'AREA[Phase](PHASE3) AND AREA[StudyType](INTERVENTIONAL)',
            'filter.overallStatus': 'ACTIVE_NOT_RECRUITING,COMPLETED',
            'sort': 'LastUpdatePostDate:desc',
            'pageSize': 50,
            'fields': 'NCTId,BriefTitle,Condition,InterventionName,LeadSponsorName,Phase,OverallStatus,PrimaryCompletionDate,CompletionDate',
            'format': 'json',
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(base_url, params=params, headers=self.headers,
                                       timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        print(f"ClinicalTrials.gov returned {response.status}")
                        return events

                    data = await response.json()
                    studies = data.get('studies', [])

                    for study in studies:
                        try:
                            protocol = study.get('protocolSection', {})
                            id_module = protocol.get('identificationModule', {})
                            status_module = protocol.get('statusModule', {})
                            design_module = protocol.get('designModule', {})
                            sponsor_module = protocol.get('sponsorCollaboratorsModule', {})
                            conditions_module = protocol.get('conditionsModule', {})
                            interventions_module = protocol.get('armsInterventionsModule', {})

                            nct_id = id_module.get('nctId', '')
                            title = id_module.get('briefTitle', '')
                            sponsor = sponsor_module.get('leadSponsor', {}).get('name', '')

                            conditions = conditions_module.get('conditions', [])
                            indication = ', '.join(conditions[:3]) if conditions else ''

                            interventions = interventions_module.get('interventions', [])
                            drug_names = [i.get('name', '') for i in interventions if i.get('type') == 'DRUG']
                            drug_name = drug_names[0] if drug_names else ''

                            completion = status_module.get('primaryCompletionDateStruct', {})
                            comp_date = completion.get('date', '')

                            ticker = self._sponsor_to_ticker(sponsor)

                            if not comp_date:
                                continue

                            phase = ', '.join(design_module.get('phases', []))
                            overall_status = status_module.get('overallStatus', '')

                            events.append({
                                'ticker': ticker,
                                'company': sponsor,
                                'drug_name': drug_name,
                                'indication': indication,
                                'catalyst_type': 'Phase3',
                                'catalyst_date': self._parse_date(comp_date),
                                'phase': phase or 'Phase 3',
                                'status': overall_status,
                                'source': 'clinicaltrials_gov',
                                'source_url': f"https://clinicaltrials.gov/study/{nct_id}",
                                'nct_id': nct_id,
                                'trial_title': title,
                            })
                        except Exception:
                            continue

        except Exception as e:
            print(f"ClinicalTrials.gov error: {e}")

        return events

    # ─── Source 5: CheckRare Orphan Drug PDUFA Dates ─────────────────────

    async def _scrape_checkrare(self) -> List[Dict]:
        """Scrape CheckRare orphan drug PDUFA dates — well-structured HTML tables."""
        events = []
        current_year = datetime.now().year
        urls = [
            f"https://checkrare.com/{current_year}-orphan-drugs-pdufa-dates-and-fda-approvals/",
            f"https://checkrare.com/{current_year + 1}-orphan-drugs-pdufa-dates-and-fda-approvals/",
        ]

        for url in urls:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status != 200:
                            continue

                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')

                        # CheckRare uses structured tables with date, drug, company, indication
                        tables = soup.find_all('table')
                        for table in tables:
                            rows = table.find_all('tr')
                            if not rows:
                                continue

                            # Try to find header row
                            header_row = rows[0]
                            headers = [th.get_text(strip=True).lower() for th in header_row.find_all(['th', 'td'])]

                            for row in rows[1:]:
                                cells = row.find_all(['td', 'th'])
                                if len(cells) < 3:
                                    continue

                                cell_texts = [c.get_text(strip=True) for c in cells]
                                data = {}
                                for i, h in enumerate(headers):
                                    if i < len(cell_texts):
                                        data[h] = cell_texts[i]

                                event = self._parse_checkrare_row(data, cell_texts, url)
                                if event:
                                    events.append(event)

                        # Also try article content with structured lists
                        if not events:
                            events.extend(self._parse_checkrare_article(soup, url))

            except Exception as e:
                print(f"CheckRare error ({url}): {e}")

        return events

    def _parse_checkrare_row(self, data: Dict, cell_texts: List[str], url: str) -> Optional[Dict]:
        """Parse a CheckRare table row."""
        # Try header-mapped data first
        date_str = data.get('date', data.get('pdufa date', data.get('action date', '')))
        drug_name = data.get('drug', data.get('drug name', data.get('product', '')))
        company = data.get('company', data.get('sponsor', data.get('manufacturer', '')))
        indication = data.get('indication', data.get('disease', data.get('condition', '')))
        status = data.get('status', data.get('outcome', data.get('result', '')))

        # Fallback: positional parsing (CheckRare typically: date, drug, company, indication, status)
        if not date_str and len(cell_texts) >= 2:
            for ct in cell_texts:
                d = self._parse_date(ct)
                if d:
                    date_str = ct
                    break
        if not drug_name and len(cell_texts) >= 2:
            drug_name = cell_texts[1] if len(cell_texts) > 1 else ''
        if not company and len(cell_texts) >= 3:
            company = cell_texts[2] if len(cell_texts) > 2 else ''
        if not indication and len(cell_texts) >= 4:
            indication = cell_texts[3] if len(cell_texts) > 3 else ''
        if not status and len(cell_texts) >= 5:
            status = cell_texts[4] if len(cell_texts) > 4 else ''

        parsed_date = self._parse_date(date_str)
        if not parsed_date and not drug_name:
            return None

        # Resolve ticker from company name
        ticker = self._sponsor_to_ticker(company)

        # Also try to find ticker in parentheses
        if not ticker:
            for text in cell_texts:
                tm = re.search(r'\(([A-Z]{1,5})\)', text)
                if tm:
                    ticker = tm.group(1)
                    break

        # Determine catalyst type from status/text
        full_text = ' '.join(cell_texts)
        cat_type = self._detect_catalyst_type(full_text)
        if cat_type == 'Other':
            # CheckRare is primarily PDUFA dates
            if 'approved' in status.lower():
                cat_type = 'Approval'
            elif 'complete response' in status.lower() or 'crl' in status.lower():
                cat_type = 'CRL'
            elif 'bla' in full_text.lower():
                cat_type = 'BLA'
            elif 'nda' in full_text.lower() or 'snda' in full_text.lower():
                cat_type = 'NDA'
            else:
                cat_type = 'PDUFA'

        return {
            'ticker': ticker,
            'company': company[:200] if company else '',
            'drug_name': drug_name[:200] if drug_name else '',
            'indication': indication[:200] if indication else '',
            'catalyst_type': cat_type,
            'catalyst_date': parsed_date,
            'phase': self._detect_phase(full_text),
            'status': self._detect_status(full_text) if status else 'Upcoming',
            'source': 'checkrare',
            'source_url': url,
        }

    def _parse_checkrare_article(self, soup, url: str) -> List[Dict]:
        """Parse CheckRare article content for PDUFA dates (non-table format)."""
        events = []
        content = soup.find('article') or soup.find('div', class_=lambda x: x and 'content' in str(x).lower())
        if not content:
            return events

        # Look for structured headings with dates followed by drug info
        for heading in content.find_all(['h2', 'h3', 'h4']):
            heading_text = heading.get_text(strip=True)
            date_match = self._parse_date(heading_text)

            if date_match:
                # Get following paragraphs/lists
                sibling = heading.find_next_sibling()
                while sibling and sibling.name not in ['h2', 'h3', 'h4']:
                    text = sibling.get_text(' ', strip=True)
                    if text and len(text) > 10:
                        ticker = ''
                        tm = re.search(r'\(([A-Z]{1,5})\)', text)
                        if tm:
                            ticker = tm.group(1)

                        # Extract company
                        company = ''
                        for key, val in COMPANY_TICKER_MAP.items():
                            if key in text.lower():
                                company = key.title()
                                if not ticker:
                                    ticker = val
                                break

                        if ticker or company:
                            drug_match = re.search(r'(\w[\w\s-]+(?:mab|nib|lib|tide|cel|parin|vir|stat|cept|umab|zumab|ximab|tinib|rafenib|lisib|ciclib|parib))', text, re.IGNORECASE)
                            drug_name = drug_match.group(1).strip() if drug_match else ''

                            events.append({
                                'ticker': ticker,
                                'company': company,
                                'drug_name': drug_name[:200],
                                'indication': '',
                                'catalyst_type': 'PDUFA',
                                'catalyst_date': date_match,
                                'phase': '',
                                'status': 'Upcoming',
                                'source': 'checkrare',
                                'source_url': url,
                            })
                    sibling = sibling.find_next_sibling()

        return events

    # ─── Source 6: FDATracker.com ────────────────────────────────────────

    async def _scrape_fdatracker(self) -> List[Dict]:
        """
        Scrape FDATracker.com FDA Calendar page.
        The standard calendar is a Google Calendar embed; we parse any available
        structured data from the page and also try the blog/list format.
        """
        events = []

        urls = [
            "https://www.fdatracker.com/fda-calendar/",
            "https://www.fdatracker.com/2015/01/the-most-comprehensive-fda-pdufa-date-calendar/",
        ]

        for url in urls:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status != 200:
                            continue

                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')

                        # Strategy 1: Look for Google Calendar iframe and extract calendar ID
                        iframes = soup.find_all('iframe')
                        for iframe in iframes:
                            src = iframe.get('src', '')
                            if 'calendar.google.com' in src:
                                cal_events = await self._scrape_google_calendar_embed(src)
                                events.extend(cal_events)

                        # Strategy 2: Parse any tables on the page
                        tables = soup.find_all('table')
                        for table in tables:
                            rows = table.find_all('tr')
                            for row in rows[1:]:  # skip header
                                cells = row.find_all('td')
                                if len(cells) < 2:
                                    continue
                                cell_texts = [c.get_text(strip=True) for c in cells]
                                text = ' '.join(cell_texts)
                                ticker_match = re.search(r'\b([A-Z]{2,5})\b', text)
                                if ticker_match:
                                    ticker = ticker_match.group(1)
                                    if ticker in EXCLUDED_TICKERS:
                                        continue
                                    date_str = ''
                                    for ct in cell_texts:
                                        d = self._parse_date(ct)
                                        if d:
                                            date_str = d
                                            break
                                    events.append({
                                        'ticker': ticker,
                                        'company': '',
                                        'drug_name': '',
                                        'indication': '',
                                        'catalyst_type': self._detect_catalyst_type(text),
                                        'catalyst_date': date_str,
                                        'phase': self._detect_phase(text),
                                        'status': 'Upcoming',
                                        'source': 'fdatracker',
                                        'source_url': url,
                                    })

                        # Strategy 3: Parse any structured content divs
                        if not events:
                            for elem in soup.find_all(['li', 'p', 'div']):
                                text = elem.get_text(strip=True)
                                if len(text) < 10 or len(text) > 500:
                                    continue
                                ticker_match = re.search(r'\(([A-Z]{1,5})\)', text)
                                if not ticker_match:
                                    continue
                                ticker = ticker_match.group(1)
                                if ticker in EXCLUDED_TICKERS:
                                    continue
                                date_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\w+ \d{1,2},? \d{4})', text)
                                date_str = self._parse_date(date_match.group(1)) if date_match else ''
                                events.append({
                                    'ticker': ticker,
                                    'company': '',
                                    'drug_name': '',
                                    'indication': '',
                                    'catalyst_type': self._detect_catalyst_type(text),
                                    'catalyst_date': date_str,
                                    'phase': self._detect_phase(text),
                                    'status': 'Upcoming',
                                    'source': 'fdatracker',
                                    'source_url': url,
                                })

            except Exception as e:
                print(f"FDATracker error ({url}): {e}")

        return events

    async def _scrape_google_calendar_embed(self, embed_url: str) -> List[Dict]:
        """Try to extract events from a Google Calendar embed URL."""
        events = []
        try:
            # Extract calendar ID from embed URL
            cal_id_match = re.search(r'[?&]src=([^&]+)', embed_url)
            if not cal_id_match:
                return events

            calendar_id = cal_id_match.group(1)
            # URL-decode
            import urllib.parse
            calendar_id = urllib.parse.unquote(calendar_id)

            # Try to fetch public iCal feed
            ical_url = f"https://calendar.google.com/calendar/ical/{urllib.parse.quote(calendar_id)}/public/basic.ics"

            async with aiohttp.ClientSession() as session:
                async with session.get(ical_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        return events

                    ical_text = await response.text()
                    events.extend(self._parse_ical_events(ical_text))

        except Exception as e:
            print(f"Google Calendar embed error: {e}")

        return events

    def _parse_ical_events(self, ical_text: str) -> List[Dict]:
        """Parse iCal format to extract FDA events."""
        events = []
        current_event = {}

        for line in ical_text.split('\n'):
            line = line.strip()
            if line == 'BEGIN:VEVENT':
                current_event = {}
            elif line == 'END:VEVENT':
                if current_event.get('summary'):
                    event = self._ical_event_to_fda(current_event)
                    if event:
                        events.append(event)
                current_event = {}
            elif ':' in line and current_event is not None:
                key, _, value = line.partition(':')
                # Handle properties with parameters (e.g., DTSTART;VALUE=DATE:20260208)
                key = key.split(';')[0]
                if key == 'SUMMARY':
                    current_event['summary'] = value
                elif key == 'DTSTART':
                    current_event['dtstart'] = value
                elif key == 'DESCRIPTION':
                    current_event['description'] = value
                elif key == 'LOCATION':
                    current_event['location'] = value

        return events

    def _ical_event_to_fda(self, ical_event: Dict) -> Optional[Dict]:
        """Convert an iCal event to FDA event format."""
        summary = ical_event.get('summary', '')
        if not summary:
            return None

        # Extract ticker from summary (e.g., "RGNX REGENXBIO - RGX-121 BLA Decision")
        ticker = ''
        ticker_match = re.match(r'^([A-Z]{1,5})\b', summary)
        if ticker_match:
            ticker = ticker_match.group(1)
        if not ticker:
            ticker_match = re.search(r'\(([A-Z]{1,5})\)', summary)
            if ticker_match:
                ticker = ticker_match.group(1)

        if not ticker or ticker in EXCLUDED_TICKERS:
            return None

        # Parse date
        dtstart = ical_event.get('dtstart', '')
        date_str = ''
        if re.match(r'^\d{8}$', dtstart):
            date_str = f"{dtstart[:4]}-{dtstart[4:6]}-{dtstart[6:8]}"
        elif re.match(r'^\d{8}T', dtstart):
            date_str = f"{dtstart[:4]}-{dtstart[4:6]}-{dtstart[6:8]}"
        else:
            date_str = self._parse_date(dtstart)

        # Extract company and drug from summary
        company = ''
        drug_name = ''
        # Pattern: "TICKER CompanyName - DrugName (Type)"
        parts = re.split(r'\s*[-–]\s*', summary, maxsplit=1)
        if len(parts) >= 2:
            company_part = parts[0].replace(ticker, '').strip()
            company = company_part
            drug_name = parts[1].strip()

        description = ical_event.get('description', '')
        full_text = f"{summary} {description}"

        return {
            'ticker': ticker,
            'company': company[:200],
            'drug_name': drug_name[:200],
            'indication': '',
            'catalyst_type': self._detect_catalyst_type(full_text),
            'catalyst_date': date_str,
            'phase': self._detect_phase(full_text),
            'status': 'Upcoming',
            'source': 'fdatracker',
            'source_url': 'https://www.fdatracker.com/fda-calendar/',
        }

    # ─── Approval Probability Estimation ─────────────────────────────────

    def _estimate_approval_probability(self, event: Dict) -> Dict:
        """
        Estimate FDA approval probability based on historical base rates.

        Base rates (FDA historical data 2015-2025):
        - Overall NDA/BLA first-cycle approval: ~85%
        - sBLA/sNDA (supplement for approved drug): ~93%
        - Priority Review: ~90%
        - Orphan Drug: ~90-95%
        - Phase 3 completion → approval: ~55-60%
        - Phase 2 → approval: ~30-35%
        - Phase 1 → approval: ~10-15%
        - CRL received (already rejected): 0% for this cycle
        - Post-AdCom positive vote: ~95%

        Returns dict with: probability (0-100), confidence, reasoning
        """
        cat_type = event.get('catalyst_type', '')
        status = (event.get('status') or '').lower()
        drug_name = (event.get('drug_name') or '').lower()
        indication = (event.get('indication') or '').lower()
        phase = (event.get('phase') or '').lower()
        full_text = f"{drug_name} {indication} {phase} {cat_type}".lower()
        sources = event.get('sources', [])

        probability = 50  # default
        confidence = 'Low'
        factors = []

        # ── Already decided events ──
        if 'approved' in status or 'complete - approved' in status:
            return {'probability': 100, 'confidence': 'Confirmed', 'factors': ['FDA approved']}
        if 'rejected' in status or 'crl' in status.lower():
            return {'probability': 0, 'confidence': 'Confirmed', 'factors': ['CRL / Rejected']}
        if cat_type == 'CRL':
            return {'probability': 0, 'confidence': 'Confirmed', 'factors': ['Complete Response Letter issued']}
        if cat_type == 'Approval':
            return {'probability': 100, 'confidence': 'Confirmed', 'factors': ['Already approved']}

        # ── PDUFA / NDA / BLA dates (drug already submitted, under FDA review) ──
        if cat_type in ('PDUFA', 'NDA', 'BLA'):
            probability = 85
            factors.append('NDA/BLA under FDA review (base: 85%)')
            confidence = 'Medium'

            # Supplemental (sBLA/sNDA) — extending approved drug to new indication
            if 'sbla' in full_text or 'snda' in full_text or 'supplemental' in full_text:
                probability = 93
                factors[-1] = 'Supplemental application for approved drug (base: 93%)'
                confidence = 'High'

            # Orphan drug designation — historically higher approval
            if any(w in full_text for w in ['orphan', 'rare disease', 'ultra-rare']):
                probability = min(probability + 5, 96)
                factors.append('Orphan drug designation (+5%)')

            # Specific rare diseases often get high approval
            rare_indicators = ['mucopolysaccharidosis', 'phenylketonuria', 'achondroplasia',
                             'leukocyte adhesion', 'gaucher', 'menkes', 'leber',
                             'arginase deficiency', 'hunter syndrome']
            if any(r in full_text for r in rare_indicators):
                probability = min(probability + 3, 96)
                factors.append('Rare/orphan disease indication (+3%)')

            # Breakthrough therapy / priority review indicators
            if any(w in full_text for w in ['breakthrough', 'priority', 'accelerated', 'fast track']):
                probability = min(probability + 3, 96)
                factors.append('Priority/breakthrough designation (+3%)')

            # Well-known drugs with established safety (extension to new indication)
            established_drugs = ['keytruda', 'opdivo', 'dupixent', 'darzalex', 'palynziq',
                               'sarclisa', 'filspari', 'vyvgart', 'inqovi']
            if any(d in full_text for d in established_drugs):
                probability = min(probability + 4, 96)
                factors.append('Established drug (extension) (+4%)')

            # Gene therapy / cell therapy — historically more variable
            if any(w in full_text for w in ['gene therapy', 'cell therapy', 'autotemcel',
                                            'lanparvovec', 'lentiviral']):
                probability = max(probability - 5, 70)
                factors.append('Gene/cell therapy (higher variability, -5%)')

            # Multiple sources confirming the event increases confidence
            if len(sources) >= 2:
                confidence = 'High'
                factors.append(f'Confirmed by {len(sources)} sources')

        # ── AdCom (Advisory Committee) ──
        elif cat_type == 'AdCom':
            probability = 75
            factors.append('Advisory Committee meeting (base: 75%)')
            confidence = 'Medium'

        # ── Phase 3 trials ──
        elif cat_type == 'Phase3':
            probability = 58
            factors.append('Phase 3 trial (historical success: ~58%)')
            confidence = 'Low'

            if 'pivotal' in full_text:
                probability = 62
                factors[-1] = 'Pivotal Phase 3 trial (62%)'

        # ── Phase 2 trials ──
        elif cat_type == 'Phase2':
            probability = 33
            factors.append('Phase 2 trial (historical success: ~33%)')
            confidence = 'Low'

        # ── Phase 1 trials ──
        elif cat_type == 'Phase1':
            probability = 12
            factors.append('Phase 1 trial (historical success: ~12%)')
            confidence = 'Low'

        # ── Other / unknown ──
        else:
            probability = 50
            factors.append('Insufficient data for estimate')
            confidence = 'Low'

        return {
            'probability': probability,
            'confidence': confidence,
            'factors': factors,
        }

    # ─── Company-to-Ticker Resolution ────────────────────────────────────

    def _sponsor_to_ticker(self, sponsor: str) -> str:
        """Map known pharma/biotech sponsors to tickers."""
        if not sponsor:
            return ''
        sponsor_lower = sponsor.lower().strip()
        for name, ticker in COMPANY_TICKER_MAP.items():
            if name in sponsor_lower:
                return ticker
        return ''

    # ─── Merge & Deduplicate ─────────────────────────────────────────────

    def _merge_and_deduplicate(self, all_events: List[Dict]) -> List[Dict]:
        """
        Deduplicate events with smart merging:
        1. Exact match: (ticker, date, type)
        2. Near match: same ticker within 3 days + compatible types (PDUFA/NDA/BLA merge)
        3. Filter non-tradeable tickers
        """
        # First pass: filter out non-tradeable and tickerless events
        valid_events = []
        for event in all_events:
            ticker = (event.get('ticker') or '').upper()
            if not ticker:
                continue
            if ticker in NON_TRADEABLE_TICKERS:
                continue
            if ticker in EXCLUDED_TICKERS:
                continue
            event['ticker'] = ticker
            valid_events.append(event)

        # Compatible types that should merge (same FDA decision, different naming)
        MERGE_TYPES = {
            frozenset({'PDUFA', 'NDA'}), frozenset({'PDUFA', 'BLA'}),
            frozenset({'NDA', 'BLA'}), frozenset({'PDUFA', 'NDA', 'BLA'}),
        }

        def types_compatible(t1, t2):
            if t1 == t2:
                return True
            return any(t1 in s and t2 in s for s in MERGE_TYPES)

        def date_diff_days(d1, d2):
            """Return abs days between two date strings, or 999 if unparseable."""
            if not d1 or not d2:
                return 999
            try:
                dt1 = datetime.strptime(d1, '%Y-%m-%d')
                dt2 = datetime.strptime(d2, '%Y-%m-%d')
                return abs((dt1 - dt2).days)
            except ValueError:
                return 999

        def merge_into(existing, new_event):
            """Merge new_event data into existing event."""
            for field in ['company', 'drug_name', 'indication', 'phase', 'nct_id', 'trial_title']:
                if not existing.get(field) and new_event.get(field):
                    existing[field] = new_event[field]
                # Prefer longer/more detailed values
                elif existing.get(field) and new_event.get(field):
                    if len(str(new_event[field])) > len(str(existing[field])):
                        existing[field] = new_event[field]
            sources = existing.get('sources', [existing.get('source', '')])
            new_source = new_event.get('source', '')
            if new_source and new_source not in sources:
                sources.append(new_source)
            existing['sources'] = sources
            # Keep the more specific catalyst type (PDUFA > NDA > BLA > Other)
            type_priority = {'PDUFA': 4, 'NDA': 3, 'BLA': 3, 'AdCom': 2, 'Approval': 5, 'CRL': 5}
            if type_priority.get(new_event.get('catalyst_type', ''), 0) > type_priority.get(existing.get('catalyst_type', ''), 0):
                existing['catalyst_type'] = new_event['catalyst_type']

        # Second pass: exact dedup
        seen = {}
        for event in valid_events:
            ticker = event['ticker']
            date = event.get('catalyst_date', '')
            cat_type = event.get('catalyst_type', '')
            key = (ticker, date, cat_type)

            if key in seen:
                merge_into(seen[key], event)
            else:
                event['sources'] = [event.get('source', '')]
                seen[key] = event

        # Third pass: near-date dedup (within 3 days, compatible types)
        merged = list(seen.values())
        final = []
        used = set()

        for i, event in enumerate(merged):
            if i in used:
                continue
            for j in range(i + 1, len(merged)):
                if j in used:
                    continue
                other = merged[j]
                if event['ticker'] != other['ticker']:
                    continue
                if not types_compatible(event.get('catalyst_type', ''), other.get('catalyst_type', '')):
                    continue
                if date_diff_days(event.get('catalyst_date', ''), other.get('catalyst_date', '')) <= 3:
                    merge_into(event, other)
                    used.add(j)

            final.append(event)

        return final

    # ─── Normalization Helpers ───────────────────────────────────────────

    def _normalize_catalyst_type(self, raw_type: str) -> str:
        """Map raw type strings to standard catalyst types."""
        if not raw_type:
            return 'Other'

        raw_lower = raw_type.lower().strip()

        if 'pdufa' in raw_lower or 'user fee' in raw_lower:
            return 'PDUFA'
        elif 'adcom' in raw_lower or 'advisory' in raw_lower or 'committee' in raw_lower:
            return 'AdCom'
        elif 'phase 3' in raw_lower or 'phase3' in raw_lower or 'phase iii' in raw_lower:
            return 'Phase3'
        elif 'phase 2' in raw_lower or 'phase2' in raw_lower or 'phase ii' in raw_lower:
            return 'Phase2'
        elif 'phase 1' in raw_lower or 'phase1' in raw_lower or 'phase i' in raw_lower:
            return 'Phase1'
        elif 'snda' in raw_lower or 'snda' in raw_lower:
            return 'NDA'
        elif 'nda' in raw_lower:
            return 'NDA'
        elif 'sbla' in raw_lower:
            return 'BLA'
        elif 'bla' in raw_lower:
            return 'BLA'
        elif 'crl' in raw_lower or 'complete response' in raw_lower:
            return 'CRL'
        elif 'approv' in raw_lower:
            return 'Approval'
        elif 'reject' in raw_lower or 'refus' in raw_lower:
            return 'Rejection'
        else:
            return 'Other'

    def _detect_catalyst_type(self, text: str) -> str:
        """Detect catalyst type from free text."""
        if not text:
            return 'Other'
        text_lower = text.lower()
        # Check for specific FDA action types in order of specificity
        if 'pdufa' in text_lower:
            return 'PDUFA'
        elif 'advisory committee' in text_lower or 'adcom' in text_lower:
            return 'AdCom'
        elif 'complete response letter' in text_lower or 'crl' in text_lower:
            return 'CRL'
        elif 'snda' in text_lower or 'sbla' in text_lower:
            return 'PDUFA'  # supplemental NDA/BLA are still PDUFA decisions
        elif 'bla' in text_lower and ('decision' in text_lower or 'accept' in text_lower or 'submit' in text_lower or 'approv' in text_lower):
            return 'BLA'
        elif 'nda' in text_lower and ('decision' in text_lower or 'accept' in text_lower or 'submit' in text_lower or 'approv' in text_lower):
            return 'NDA'
        elif 'approved' in text_lower or 'fda approves' in text_lower:
            return 'Approval'
        elif 'fda decision' in text_lower or 'action date' in text_lower:
            return 'PDUFA'
        elif 'phase 3' in text_lower or 'phase iii' in text_lower or 'pivotal' in text_lower:
            return 'Phase3'
        elif 'phase 2' in text_lower or 'phase ii' in text_lower:
            return 'Phase2'
        elif 'phase 1' in text_lower or 'phase i' in text_lower:
            return 'Phase1'
        elif 'reject' in text_lower or 'refus' in text_lower:
            return 'Rejection'
        elif 'bla' in text_lower:
            return 'BLA'
        elif 'nda' in text_lower:
            return 'NDA'
        return 'Other'

    def _detect_phase(self, text: str) -> str:
        """Detect clinical trial phase from text."""
        text_lower = text.lower()
        if 'phase 3' in text_lower or 'phase iii' in text_lower or 'pivotal' in text_lower:
            return 'Phase 3'
        elif 'phase 2' in text_lower or 'phase ii' in text_lower:
            return 'Phase 2'
        elif 'phase 1' in text_lower or 'phase i' in text_lower:
            return 'Phase 1'
        elif 'snda' in text_lower or 'sbla' in text_lower:
            return 'NDA/BLA'
        elif 'nda' in text_lower or 'bla' in text_lower:
            return 'NDA/BLA'
        elif 'approved' in text_lower:
            return 'Approved'
        return ''

    def _detect_status(self, text: str) -> str:
        """Detect event status from text."""
        text_lower = text.lower()
        if 'approved' in text_lower or 'granted' in text_lower:
            return 'Complete - Approved'
        elif 'rejected' in text_lower or 'refused' in text_lower or 'complete response letter' in text_lower:
            return 'Complete - Rejected'
        elif 'crl' in text_lower:
            return 'Complete - CRL'
        elif 'under review' in text_lower or 'pending' in text_lower or 'accepted' in text_lower:
            return 'Under Review'
        elif 'upcoming' in text_lower or 'scheduled' in text_lower:
            return 'Upcoming'
        return 'Upcoming'

    def _parse_date(self, date_str: str) -> str:
        """Robust date parser handling multiple formats."""
        if not date_str:
            return ''

        date_str = date_str.strip()

        # ISO format: 2024-03-15
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str

        # US format: 03/15/2024 or 3/15/2024
        m = re.match(r'^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$', date_str)
        if m:
            try:
                return f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
            except Exception:
                pass

        # US format with dots: 1.5.2026
        m = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', date_str)
        if m:
            try:
                return f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
            except Exception:
                pass

        # Named month: March 15, 2024 or Mar 15 2024 or Feb 1, 2026
        m = re.search(r'(\w+)\s+(\d{1,2}),?\s+(\d{4})', date_str)
        if m:
            try:
                dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", '%B %d %Y')
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                try:
                    dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", '%b %d %Y')
                    return dt.strftime('%Y-%m-%d')
                except ValueError:
                    pass

        # Quarter: Q1 2024, Q2 2024
        m = re.match(r'Q(\d)\s*(\d{4})', date_str)
        if m:
            quarter = int(m.group(1))
            year = int(m.group(2))
            month = (quarter - 1) * 3 + 1
            return f"{year}-{month:02d}-01"

        # Half: H1 2024, H2 2024
        m = re.match(r'H(\d)\s*(\d{4})', date_str)
        if m:
            half = int(m.group(1))
            year = int(m.group(2))
            month = 1 if half == 1 else 7
            return f"{year}-{month:02d}-01"

        # Year-Month: 2024-03 or March 2024
        m = re.match(r'^(\d{4})-(\d{2})$', date_str)
        if m:
            return f"{m.group(1)}-{m.group(2)}-01"

        m = re.search(r'(\w+)\s+(\d{4})', date_str)
        if m:
            try:
                dt = datetime.strptime(f"{m.group(1)} 1 {m.group(2)}", '%B %d %Y')
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                try:
                    dt = datetime.strptime(f"{m.group(1)} 1 {m.group(2)}", '%b %d %Y')
                    return dt.strftime('%Y-%m-%d')
                except ValueError:
                    pass

        return ''
