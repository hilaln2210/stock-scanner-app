"""
SEC EDGAR 8-K Filing Service.

Fetches recent 8-K filings from SEC EDGAR to identify stocks with material news events.
Uses the EDGAR atom feed + company_tickers.json CIK→ticker mapping.

8-K Classification (based on SEC regulations + Investopedia 8-K guide):
  8-K must be filed within 4 business days of a material event.
  We parse the item numbers from the filing summary to classify each event.
  Key items for traders:
    2.02 → Earnings Results (most important for briefing)
    1.01 → Material Agreement (major contracts, M&A, licensing)
    2.01 → Completion of Acquisition or Disposition
    5.01 → Change of Control (takeover)
    5.02 → Director/Officer Changes (CEO/CFO)
    7.01 → Regulation FD Disclosure (guidance, investor day)
    8.01 → Other Material Events (catch-all)
    1.03 → Bankruptcy ⚠️  (bearish — excluded from bullish candidates)
    4.02 → Financial Restatement ⚠️ (bearish — excluded from bullish candidates)
    3.01 → Delisting Warning ⚠️ (bearish — excluded from bullish candidates)
    9.01 → Exhibits only (admin — skipped)

Rate limit note: SEC asks for max 10 req/sec with a valid User-Agent.
"""

import html as html_lib
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import aiohttp

# ── Cache ─────────────────────────────────────────────────────────────────────

_cik_ticker_cache: Optional[Dict[int, str]] = None
_cik_ticker_cache_at: Optional[datetime] = None
_8k_cache: Optional[Dict[str, dict]] = None
_8k_cache_at: Optional[datetime] = None

_CIK_MAP_TTL = 86400   # 24 hours
_8K_TTL      = 3600    # 1 hour

_HEADERS = {
    'User-Agent': 'StockScanner/1.0 contact@stockscanner.local',
    'Accept-Encoding': 'gzip, deflate',
}


# ── 8-K Item Classification ────────────────────────────────────────────────────
#
# Mapping: item_code → (hebrew_label, sentiment)
# Sentiment: 'bullish' | 'bearish' | 'neutral'
# None → admin/exhibit only, no standalone trading significance

_8K_ITEM_LABELS: Dict[str, Optional[Tuple[str, str]]] = {
    # ── Significant Business Events ──────────────────────────────────────────
    '1.01': ('הסכם מהותי',       'bullish'),  # Entry into Material Definitive Agreement
    '1.02': ('ביטול הסכם',       'bearish'),  # Termination of Material Definitive Agreement
    '1.03': ('פשיטת רגל',        'bearish'),  # Bankruptcy or Receivership ⚠️
    '1.04': ('בטיחות מכרות',     'neutral'),  # Mine Safety

    # ── Financial Information ─────────────────────────────────────────────────
    '2.01': ('רכישה/מכירה',      'bullish'),  # Completion of Acquisition or Disposition of Assets
    '2.02': ('תוצאות רבעוניות',  'bullish'),  # Results of Operations and Financial Condition (EARNINGS)
    '2.03': ('התחייבות פיננסית', 'neutral'),  # Creation of a Direct Financial Obligation
    '2.04': ('האצת חוב',         'bearish'),  # Triggering Events That Accelerate Financial Obligation
    '2.05': ('ארגון מחדש',       'neutral'),  # Costs Associated with Exit or Disposal Activities
    '2.06': ('הפחתת ערך',        'bearish'),  # Material Impairments

    # ── Securities and Trading ────────────────────────────────────────────────
    '3.01': ('אזהרת רישום',      'bearish'),  # Notice of Delisting / Listing Rule Failure ⚠️
    '3.02': ('מכירת ניירות',     'neutral'),  # Unregistered Sales of Equity Securities
    '3.03': ('שינוי זכויות',     'neutral'),  # Material Modification to Rights of Security Holders

    # ── Accountants ───────────────────────────────────────────────────────────
    '4.01': ('שינוי רואה חשבון', 'neutral'),  # Changes in Registrant's Certifying Accountant
    '4.02': ('תיקון דו"ח',       'bearish'),  # Non-Reliance on Prior Financial Statements (RESTATEMENT) ⚠️

    # ── Corporate Governance ─────────────────────────────────────────────────
    '5.01': ('שינוי שליטה',      'bullish'),  # Changes in Control of Registrant (takeover)
    '5.02': ('שינוי הנהלה',      'neutral'),  # Departure/Election/Appointment of Directors or Officers
    '5.03': ('תיקון תקנון',      'neutral'),  # Amendments to Articles of Incorporation or Bylaws
    '5.04': ('הגבלת מסחר',       'neutral'),  # Temporary Suspension of Trading Under Employee Benefit Plans
    '5.05': ('תיקון אתיקה',      'neutral'),  # Amendment to Code of Ethics or Waiver
    '5.06': ('שינוי מעמד',       'neutral'),  # Change in Shell Company Status
    '5.07': ('הצבעת בעלי מניות', 'neutral'),  # Submission of Matters to a Vote of Security Holders
    '5.08': ('מינוי דירקטורים',  'neutral'),  # Shareholder Director Nominations

    # ── Asset-Backed Securities ───────────────────────────────────────────────
    '6.01': ('ABS',              'neutral'),
    '6.02': ('ABS',              'neutral'),
    '6.03': ('ABS',              'neutral'),
    '6.04': ('ABS',              'neutral'),
    '6.05': ('ABS',              'neutral'),

    # ── Regulation FD ─────────────────────────────────────────────────────────
    '7.01': ('עדכון תחזית',      'bullish'),  # Regulation FD Disclosure (guidance, investor day)

    # ── Other Events ─────────────────────────────────────────────────────────
    '8.01': ('אירוע מהותי',      'neutral'),  # Other Events (material but unclassified)

    # ── Financial Statements / Exhibits ──────────────────────────────────────
    # These are supporting documents, not the actual event — no standalone trading significance
    '9.01': None,
}

# Priority for choosing the "primary" item when multiple items are filed
_ITEM_PRIORITY = [
    '1.03', '4.02',       # Most urgent: bankruptcy, restatement
    '3.01',               # Delisting warning
    '2.02',               # Earnings results (core briefing signal)
    '5.01', '2.01',       # M&A: change of control, acquisition
    '1.01', '1.02',       # Material agreements
    '5.02',               # Leadership changes (CEO/CFO)
    '7.01',               # Regulation FD (guidance/investor presentations)
    '2.06', '2.04',       # Negative financial events
    '2.05',               # Restructuring
    '2.03',               # New debt
    '8.01',               # Other material events
]

# Items with no standalone trading relevance (admin/exhibit only)
_ADMIN_ONLY_ITEMS = frozenset({
    '9.01', '5.03', '5.04', '5.05', '5.06', '5.07', '5.08',
    '3.02', '3.03', '4.01',
    '6.01', '6.02', '6.03', '6.04', '6.05',
    '1.04',
})

# Items representing clear bearish signals → exclude these tickers from bullish briefing additions
BEARISH_EXCLUDE_ITEMS = frozenset({'1.03', '4.02', '3.01'})


# ── Item Parsing ───────────────────────────────────────────────────────────────

def _parse_8k_items(entry: str) -> List[str]:
    """
    Extract 8-K item numbers from an EDGAR atom feed entry's <summary> field.

    EDGAR atom feed summaries typically contain:
      Filed: 2024-01-15  AccNo: 0001234567-24-000001  Type: 8-K
      Act: 34  File No.: 001-12345  Film No.: 24567890
      Items: 2.02, 9.01
      Period of Report: 2023-12-31
    """
    summary_m = re.search(r'<summary[^>]*>(.*?)</summary>', entry, re.DOTALL | re.IGNORECASE)
    if not summary_m:
        return []

    # Unescape HTML entities (&lt; → <, &gt; → >, &amp; → &, etc.)
    summary = html_lib.unescape(summary_m.group(1))
    # Strip remaining HTML tags
    summary = re.sub(r'<[^>]+>', ' ', summary)

    # Match "Items: 2.02, 9.01" or "Item: 2.02"
    items_m = re.search(r'\bItems?\s*[:\s]\s*([0-9][0-9.,\s]+)', summary, re.IGNORECASE)
    if items_m:
        return re.findall(r'\d+\.\d+', items_m.group(1))
    return []


def _classify_8k(items: List[str]) -> Tuple[Optional[str], str]:
    """
    Determine the primary Hebrew label and sentiment for an 8-K filing.

    Returns:
        (label, sentiment) where label may be None for admin-only filings
        and sentiment is 'bullish' | 'bearish' | 'neutral' | 'admin'
    """
    if not items:
        return (None, 'neutral')

    substantive = [i for i in items if i not in _ADMIN_ONLY_ITEMS]
    if not substantive:
        return (None, 'admin')

    primary = None
    for priority_item in _ITEM_PRIORITY:
        if priority_item in substantive:
            primary = priority_item
            break
    if primary is None:
        primary = substantive[0]

    label_info = _8K_ITEM_LABELS.get(primary)
    if label_info is None:
        return (None, 'neutral')

    label, sentiment = label_info
    return (label, sentiment)


# ── Financial Highlight Extraction ────────────────────────────────────────────

def _extract_highlights(text: str, items: List[str]) -> List[str]:
    """
    Extract 2-4 key financial highlights from 8-K press release text.
    Returns short Hebrew-labeled strings like "הכנסות: $113M (+700% YoY)".
    """
    highlights = []

    # Revenue / Sales ──────────────────────────────────────────────────────────
    rev_m = re.search(
        r'(?:total\s+)?(?:net\s+)?(?:revenue[s]?|sales)\s*'
        r'(?:of|were|was|totaled?|reached?)\s*'
        r'(?:approximately\s+)?\$\s*([\d,.]+)\s*(million|billion|M\b|B\b)',
        text, re.IGNORECASE
    )
    if not rev_m:
        # Alternative: "revenues of $X million"
        rev_m = re.search(
            r'\$([\d,.]+)\s*(million|billion)\s+in\s+(?:total\s+)?(?:revenue[s]?|sales)',
            text, re.IGNORECASE
        )
    if rev_m:
        amt = rev_m.group(1).replace(',', '')
        unit = rev_m.group(2)
        unit_s = 'M' if unit.lower().startswith('m') else 'B'
        rev_str = f"${amt}{unit_s}"

        # YoY growth near the revenue mention
        nearby = text[max(0, rev_m.start() - 100):rev_m.end() + 200]
        growth_m = re.search(
            r'(?:up|increase[d]?|grew?|growth)\s+(?:of\s+)?'
            r'(?:approximately\s+)?(\d[\d,.]+)%',
            nearby, re.IGNORECASE
        )
        if growth_m:
            highlights.append(f"הכנסות: {rev_str} (+{growth_m.group(1)}% YoY)")
        else:
            highlights.append(f"הכנסות: {rev_str}")

    # Standalone YoY growth (if revenue wasn't found with growth) ──────────────
    if not any('YoY' in h for h in highlights):
        growth_m = re.search(
            r'(?:revenue[s]?|sales)[^.]{0,60}?'
            r'(?:up|increased?|grew?|growth)[^.]{0,40}?'
            r'(\d[\d,.]+)%\s*(?:year.over.year|YoY|compared|versus)',
            text, re.IGNORECASE
        )
        if growth_m:
            highlights.append(f"גידול: +{growth_m.group(1)}% לעומת אשתקד")

    # EPS ──────────────────────────────────────────────────────────────────────
    eps_m = re.search(
        r'(?:GAAP\s+)?(?:diluted\s+)?'
        r'(?:EPS|earnings per (?:diluted\s+)?share)\s*'
        r'(?:of|was|were)?\s*\$\s*([\d.]+)',
        text, re.IGNORECASE
    )
    if eps_m:
        highlights.append(f"EPS: ${eps_m.group(1)}")

    # Regulatory approval ──────────────────────────────────────────────────────
    reg_m = re.search(
        r'(FDA|European Commission|EMA|Health Canada|MHRA)\s+'
        r'(?:has\s+)?(?:approved?|granted?|cleared?)[^.]{0,120}\.',
        text, re.IGNORECASE
    )
    if reg_m:
        agency = reg_m.group(1)
        highlights.append(f"אישור רגולטורי ({agency})")

    # Deal value (M&A, agreements) ─────────────────────────────────────────────
    ma_items = {'1.01', '2.01', '5.01'}
    if any(i in ma_items for i in items):
        deal_m = re.search(
            r'(?:transaction|acquisition|deal|agreement)[^.]{0,50}\$\s*([\d,.]+)\s*(million|billion)',
            text, re.IGNORECASE
        )
        if deal_m:
            amt = deal_m.group(1).replace(',', '')
            unit = deal_m.group(2)
            unit_s = 'M' if unit.lower().startswith('m') else 'B'
            highlights.append(f"עסקה: ${amt}{unit_s}")

    # Guidance ─────────────────────────────────────────────────────────────────
    guidance_m = re.search(
        r'(?:guidance|outlook|forecast)[^.]{0,40}\$\s*([\d,.]+)\s*(million|billion)',
        text, re.IGNORECASE
    )
    if guidance_m:
        amt = guidance_m.group(1).replace(',', '')
        unit = guidance_m.group(2)
        unit_s = 'M' if unit.lower().startswith('m') else 'B'
        highlights.append(f"תחזית: ${amt}{unit_s}")

    return highlights[:4]  # Max 4 highlights


# ── Fetch SEC Filing Highlights ────────────────────────────────────────────────

async def fetch_sec_highlights(
    session: aiohttp.ClientSession,
    sec_info: dict,
) -> Optional[dict]:
    """
    Fetch key financial highlights from an 8-K press release (Exhibit 99.1).

    Steps:
      1. Build filing index URL from CIK + accession number
      2. Fetch the EDGAR filing index page (lists all documents)
      3. Find Exhibit 99.1 (press release) or fallback to primary document
      4. Fetch the document and extract financial figures

    Returns:
        {filing_url, highlights: List[str]} or None on failure
    """
    cik = sec_info.get('cik')
    accession = sec_info.get('accession')
    if not cik or not accession:
        return None

    try:
        acc_nodash = accession.replace('-', '')
        cik_str = str(cik)

        # EDGAR filing index page
        # Format: https://www.sec.gov/Archives/edgar/data/{CIK}/{acc_nodash}/{accession}-index.htm
        index_url = (
            f'https://www.sec.gov/Archives/edgar/data/{cik_str}'
            f'/{acc_nodash}/{accession}-index.htm'
        )

        async with session.get(
            index_url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=8)
        ) as resp:
            if resp.status != 200:
                return None
            index_html = await resp.text()

        # ── Find Exhibit 99.1 (press release) ──────────────────────────────
        # EDGAR index table has links like: <a href="ex991.htm">EX-99.1</a>
        # Try Exhibit 99.1 first (best source for earnings/news details)
        doc_url = None

        # Pattern: href="..." followed by EX-99.1 or press release text nearby
        ex99_m = re.search(
            r'href="([^"]+\.(?:htm|html?))"[^>]*>(?:[^<]*EX-99|[^<]*99\.1)',
            index_html, re.IGNORECASE
        )
        if not ex99_m:
            # Try: document description column mentions "press release" or "99.1"
            ex99_m = re.search(
                r'<a href="([^"]+\.(?:htm|html?))"[^>]*>[^<]*</a>[^<]*'
                r'(?:<[^>]+>)*[^<]*(?:press release|99\.1)',
                index_html, re.IGNORECASE
            )
        if not ex99_m:
            # Also try links with "ex99" or "ex-99" in the filename
            ex99_m = re.search(
                r'href="([^"]+ex.?99[^"]*\.(?:htm|html?))"',
                index_html, re.IGNORECASE
            )

        if ex99_m:
            doc_path = ex99_m.group(1)
        else:
            # Fallback: first .htm link in the index (usually the 8-K main body)
            primary_m = re.search(r'href="([^"]+\.(?:htm|html?))"', index_html, re.IGNORECASE)
            if not primary_m:
                return {'filing_url': index_url, 'highlights': []}
            doc_path = primary_m.group(1)

        # Build full document URL
        if doc_path.startswith('/'):
            doc_url = f'https://www.sec.gov{doc_path}'
        elif doc_path.startswith('http'):
            doc_url = doc_path
        else:
            doc_url = (
                f'https://www.sec.gov/Archives/edgar/data/{cik_str}'
                f'/{acc_nodash}/{doc_path}'
            )

        # ── Fetch the press release document ───────────────────────────────
        async with session.get(
            doc_url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=8)
        ) as resp:
            if resp.status != 200:
                return {'filing_url': index_url, 'highlights': []}
            doc_html = await resp.text()

        # Strip style/script blocks, then HTML tags
        doc_text = re.sub(r'<style[^>]*>.*?</style>', ' ', doc_html, flags=re.DOTALL | re.IGNORECASE)
        doc_text = re.sub(r'<script[^>]*>.*?</script>', ' ', doc_text, flags=re.DOTALL | re.IGNORECASE)
        doc_text = re.sub(r'<[^>]+>', ' ', doc_text)
        doc_text = html_lib.unescape(doc_text)
        doc_text = re.sub(r'\s+', ' ', doc_text).strip()

        items = sec_info.get('items', [])
        highlights = _extract_highlights(doc_text, items)

        return {
            'filing_url': doc_url,
            'highlights': highlights,
        }

    except Exception as e:
        print(f"SEC highlights fetch failed: {e}")
        return None


# ── CIK → Ticker map ──────────────────────────────────────────────────────────

async def _get_cik_ticker_map(session: aiohttp.ClientSession) -> Dict[int, str]:
    """
    Fetch SEC company_tickers.json and build {cik_int: ticker} dict.
    Cached for 24 hours.
    """
    global _cik_ticker_cache, _cik_ticker_cache_at
    now = datetime.now()
    if (_cik_ticker_cache is not None and _cik_ticker_cache_at is not None
            and (now - _cik_ticker_cache_at).total_seconds() < _CIK_MAP_TTL):
        return _cik_ticker_cache

    try:
        async with session.get(
            'https://www.sec.gov/files/company_tickers.json',
            headers=_HEADERS,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                print(f"SEC: company_tickers.json HTTP {resp.status}")
                return _cik_ticker_cache or {}
            data = await resp.json(content_type=None)

        mapping: Dict[int, str] = {}
        for v in data.values():
            cik = int(v.get('cik_str', 0))
            ticker = str(v.get('ticker', '')).strip().upper()
            # Keep only common stock tickers: 1-5 alpha chars, no warrants/preferred/rights
            if (cik and ticker and 1 <= len(ticker) <= 5
                    and ticker.isalpha()
                    and not ticker.endswith(('W', 'P', 'R', 'U', 'L', 'Q'))):
                mapping[cik] = ticker

        _cik_ticker_cache = mapping
        _cik_ticker_cache_at = now
        print(f"SEC: loaded {len(mapping)} CIK→ticker entries")
        return mapping

    except Exception as e:
        print(f"SEC: company_tickers.json fetch failed: {e}")
        return _cik_ticker_cache or {}


# ── Recent 8-K filings ────────────────────────────────────────────────────────

async def get_recent_8k_tickers(
    session: aiohttp.ClientSession,
    days: int = 7,
) -> Dict[str, dict]:
    """
    Returns {ticker: {date, items, type, sentiment, cik, accession}} for companies
    that filed a trading-relevant 8-K in the past N days.

    Fields per ticker:
      date      — ISO date string (e.g. '2024-01-15')
      items     — list of item codes (e.g. ['2.02', '9.01'])
      type      — Hebrew label for primary item (e.g. 'תוצאות רבעוניות')
      sentiment — 'bullish' | 'bearish' | 'neutral'
      cik       — company CIK (int) — used for fetching full filing
      accession — accession number string e.g. '0001234567-24-000001'

    Admin-only filings (e.g. just Item 9.01 exhibits) are excluded.
    """
    global _8k_cache, _8k_cache_at
    now = datetime.now()
    if (_8k_cache is not None and _8k_cache_at is not None
            and (now - _8k_cache_at).total_seconds() < _8K_TTL):
        return _8k_cache

    try:
        cik_map = await _get_cik_ticker_map(session)

        # EDGAR recent 8-K filings (atom feed, latest 100)
        url = (
            'https://www.sec.gov/cgi-bin/browse-edgar'
            '?action=getcurrent&type=8-K&dateb=&owner=include&count=100&output=atom'
        )
        async with session.get(
            url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                print(f"SEC atom feed: HTTP {resp.status}")
                return _8k_cache or {}
            xml_text = await resp.text()

        cutoff = now - timedelta(days=days)
        result: Dict[str, dict] = {}

        # Each <entry> in the atom feed represents one filing
        entries = re.findall(r'<entry>(.*?)</entry>', xml_text, re.DOTALL)
        for entry in entries:
            # Title format: "8-K - COMPANY NAME (0000123456) (Reporting)"
            cik_match = re.search(r'\((\d{7,10})\)', entry)
            date_match = re.search(r'<updated>(\d{4}-\d{2}-\d{2})', entry)

            if not (cik_match and date_match):
                continue

            cik = int(cik_match.group(1))
            filed_date = date_match.group(1)

            # Skip filings outside the window
            try:
                if datetime.strptime(filed_date, '%Y-%m-%d') < cutoff:
                    continue
            except Exception:
                continue

            ticker = cik_map.get(cik)
            if not ticker:
                continue

            # Parse accession number from <id> field
            # Format: urn:tag:sec.gov,2008:accession-number=0001234567-24-000001
            accession = None
            acc_m = re.search(r'accession-number=([0-9]+-[0-9]+-[0-9]+)', entry)
            if acc_m:
                accession = acc_m.group(1)

            # Parse 8-K item numbers from the entry summary
            items = _parse_8k_items(entry)
            label, sentiment = _classify_8k(items)

            # Skip admin-only filings (e.g., pure exhibits with no substantive items)
            if sentiment == 'admin':
                continue

            # Keep most recent filing per ticker (prefer more meaningful items)
            if ticker not in result or filed_date > result[ticker]['date']:
                result[ticker] = {
                    'date': filed_date,
                    'items': items,
                    'type': label,
                    'sentiment': sentiment,
                    'cik': cik,
                    'accession': accession,
                }

        _8k_cache = result
        _8k_cache_at = now

        # Log breakdown by sentiment
        counts: Dict[str, int] = {}
        for v in result.values():
            s = v['sentiment']
            counts[s] = counts.get(s, 0) + 1
        print(
            f"SEC: {len(result)} tickers filed trading-relevant 8-K in past {days} days "
            f"(bullish: {counts.get('bullish', 0)}, "
            f"bearish: {counts.get('bearish', 0)}, "
            f"neutral: {counts.get('neutral', 0)})"
        )
        return result

    except Exception as e:
        print(f"SEC: 8-K fetch failed: {e}")
        return _8k_cache or {}
