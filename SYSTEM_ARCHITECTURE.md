# Stock Scanner & Trading Dashboard - System Architecture

## Executive Summary
מערכת מסחר אלגוריתמית מקצועית לזיהוי הזדמנויות מסחר קצר-טווח בזמן אמת, המשלבת מקורות נתונים מרובים עם מנוע ניתוח חכם ודשבורד אינטראקטיבי.

---

## 1. System Overview

### 1.1 Core Architecture Pattern
**Event-Driven Microservices Architecture** עם real-time data streaming

```
┌─────────────────────────────────────────────────────────────────┐
│                        Data Ingestion Layer                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Finviz   │  │   FMP    │  │ Polygon  │  │ NewsAPI  │  ...  │
│  │ Scraper  │  │   API    │  │   API    │  │  Stream  │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
└───────┼─────────────┼─────────────┼─────────────┼──────────────┘
        │             │             │             │
        └─────────────┴─────────────┴─────────────┘
                      │
        ┌─────────────▼──────────────┐
        │   Message Queue (Kafka)     │
        │  Topics: raw-news, raw-     │
        │  filings, raw-prices, etc   │
        └─────────────┬───────────────┘
                      │
        ┌─────────────▼──────────────┐
        │  Normalization Pipeline     │
        │  • Deduplication            │
        │  • Validation               │
        │  • Entity Resolution        │
        │  • Timestamp Alignment      │
        └─────────────┬───────────────┘
                      │
        ┌─────────────▼──────────────┐
        │   Time-Series Database      │
        │   (TimescaleDB/InfluxDB)    │
        │   + Document Store (Mongo)  │
        └─────────────┬───────────────┘
                      │
        ┌─────────────▼──────────────┐
        │    Analytics Engine         │
        │  • Signal Detection         │
        │  • Opportunity Scoring      │
        │  • Risk Assessment          │
        │  • Sentiment Analysis       │
        └─────────────┬───────────────┘
                      │
        ┌─────────────▼──────────────┐
        │      Cache Layer            │
        │      (Redis Cluster)        │
        └─────────────┬───────────────┘
                      │
        ┌─────────────▼──────────────┐
        │   WebSocket Server          │
        │   + REST API Gateway        │
        └─────────────┬───────────────┘
                      │
        ┌─────────────▼──────────────┐
        │    Frontend Dashboard       │
        │    (React + TanStack)       │
        └─────────────────────────────┘
```

---

## 2. Data Sources & Integration

### 2.1 Primary Data Sources

#### A. **Finviz Elite** (Primary Scanner)
- **Access Method**: Web scraping + potential Elite API access
- **Authentication**:
  - Session-based cookies (POST to login endpoint)
  - Elite subscription credentials
  - Rate limiting: ~100 requests/minute (estimated)
- **Data Points**:
  - Real-time screener results
  - News feed (finviz.com/news.ashx)
  - Insider trading activity
  - Unusual volume alerts
- **Challenges**:
  - No official API documentation
  - Requires cookie management & session persistence
  - HTML parsing (may break with UI changes)
- **Mitigation**:
  - Implement robust CSS selector fallbacks
  - Monitor for parsing errors
  - Add captcha detection & alerts

#### B. **Financial Modeling Prep (FMP)**
- **Authentication**: API Key (Header: `X-API-KEY`)
- **Endpoints**:
  - `/v3/sec_filings/{symbol}` - 8-K, 10-Q, 10-K
  - `/v3/stock_news` - Real-time news
  - `/v4/insider-trading` - Insider transactions
  - `/v3/ratios/{symbol}` - Financial ratios
- **Rate Limit**: 250 calls/minute (Professional plan)
- **Cost**: $49/month (Professional)

#### C. **Polygon.io** (Real-Time Market Data)
- **Authentication**: API Key (Query param: `apiKey=xxx`)
- **Endpoints**:
  - WebSocket: `wss://socket.polygon.io/stocks`
  - REST: `/v2/aggs/ticker/{symbol}/range/...`
  - `/v2/reference/news` - Market news
- **Rate Limit**: 5 requests/second (Starter), unlimited (Pro)
- **Cost**: $99/month (Starter), $249/month (Developer)

#### D. **newsfilter.io** (Real-Time News Stream)
- **Authentication**: API Key + WebSocket connection
- **Features**:
  - Real-time article stream (socket.io)
  - SEC filing alerts (8-K, 10-Q immediate notifications)
  - Sentiment scores
- **Rate Limit**: Unlimited stream (subscription-based)
- **Cost**: Contact for pricing

#### E. **Alpha Vantage** (Sentiment & Economic Data)
- **Authentication**: API Key
- **Endpoints**:
  - `/query?function=NEWS_SENTIMENT` - News + AI sentiment
  - `/query?function=TOP_GAINERS_LOSERS`
- **Rate Limit**: 25 calls/day (free), 500/day (premium)
- **Cost**: Free tier available, $49.99/month (Premium)

#### F. **Finnhub** (Supplementary Data)
- **Authentication**: API Key
- **Endpoints**:
  - `/news` - Company news
  - `/calendar/earnings` - Earnings calendar
- **Rate Limit**: 60 calls/minute (free)
- **Cost**: Free tier available

### 2.2 Data Ingestion Strategy

#### Rate Limit Management
```python
# Pseudo-implementation
class DataSourceManager:
    sources = {
        'finviz': RateLimiter(100, window=60),  # 100/min
        'fmp': RateLimiter(250, window=60),
        'polygon': RateLimiter(5, window=1),
        # ... etc
    }

    async def fetch_with_backoff(source, endpoint, params):
        limiter = sources[source]
        await limiter.acquire()
        try:
            return await http_client.get(endpoint, params)
        except RateLimitError:
            await exponential_backoff()
            return await fetch_with_backoff(...)
```

#### Session Management (Finviz)
- Store cookies in Redis with TTL
- Automatic re-authentication on 401/403
- Detect "Login Required" HTML patterns
- Fallback to headless browser (Playwright) if needed

#### Deduplication Logic
```sql
-- Example: Dedupe news articles
CREATE UNIQUE INDEX idx_news_dedupe
ON news_events (source, article_url, published_at);

-- For cross-source dedupe: fuzzy matching
SELECT * FROM news_events
WHERE levenshtein(title, $1) < 5
  AND abs(published_at - $2) < INTERVAL '10 minutes';
```

---

## 3. Data Schema

### 3.1 Unified Event Schema
All incoming data normalized to:

```typescript
interface MarketEvent {
  event_id: string;              // UUID v7 (time-ordered)
  event_type: EventType;         // NEWS | FILING | INSIDER | VOLUME_SPIKE | ...
  symbol: string;                // Ticker symbol
  timestamp: Date;               // Original publication time
  ingested_at: Date;             // When we received it
  source: DataSource;            // FINVIZ | FMP | POLYGON | ...

  // Core data
  title: string;
  summary: string;
  url?: string;

  // Metadata
  tags: string[];                // ['earnings', 'fda_approval', 'merger']
  sector?: string;
  market_cap?: number;

  // Enrichments (computed)
  sentiment_score: number;       // -1 (bearish) to +1 (bullish)
  impact_score: number;          // 0-100 (potential price impact)
  signal_quality: number;        // 0-100 (confidence in signal)

  // Raw payload
  raw_data: JSONB;
}

enum EventType {
  NEWS = 'news',
  FILING_8K = 'filing_8k',
  FILING_10Q = 'filing_10q',
  FILING_10K = 'filing_10k',
  EARNINGS_REPORT = 'earnings_report',
  INSIDER_BUY = 'insider_buy',
  INSIDER_SELL = 'insider_sell',
  VOLUME_SPIKE = 'volume_spike',
  PRICE_BREAKOUT = 'price_breakout',
  ANALYST_UPGRADE = 'analyst_upgrade',
  ANALYST_DOWNGRADE = 'analyst_downgrade',
  FDA_APPROVAL = 'fda_approval',
  MERGER_ACQUISITION = 'merger_acquisition',
}

enum DataSource {
  FINVIZ = 'finviz',
  FMP = 'fmp',
  POLYGON = 'polygon',
  NEWSFILTER = 'newsfilter',
  ALPHAVANTAGE = 'alphavantage',
  FINNHUB = 'finnhub',
}
```

### 3.2 Database Schema

#### TimescaleDB (Time-Series Events)
```sql
CREATE TABLE market_events (
  event_id UUID PRIMARY KEY,
  event_type VARCHAR(50) NOT NULL,
  symbol VARCHAR(10) NOT NULL,
  timestamp TIMESTAMPTZ NOT NULL,
  ingested_at TIMESTAMPTZ DEFAULT NOW(),
  source VARCHAR(20) NOT NULL,

  title TEXT NOT NULL,
  summary TEXT,
  url TEXT,

  tags TEXT[],
  sector VARCHAR(50),
  market_cap BIGINT,

  sentiment_score NUMERIC(3,2),
  impact_score NUMERIC(5,2),
  signal_quality NUMERIC(5,2),

  raw_data JSONB
);

-- Hypertable for time-series optimization
SELECT create_hypertable('market_events', 'timestamp');

-- Indexes
CREATE INDEX idx_symbol_time ON market_events (symbol, timestamp DESC);
CREATE INDEX idx_event_type ON market_events (event_type);
CREATE INDEX idx_signal_quality ON market_events (signal_quality DESC)
  WHERE signal_quality > 70;
```

#### MongoDB (Rich Document Storage)
```javascript
// Collection: stock_profiles
{
  _id: "AAPL",
  symbol: "AAPL",
  name: "Apple Inc.",
  sector: "Technology",
  industry: "Consumer Electronics",
  market_cap: 3000000000000,

  fundamentals: {
    pe_ratio: 30.5,
    eps: 6.15,
    revenue_ttm: 394000000000,
    // ... more ratios
  },

  technical: {
    sma_20: 175.30,
    sma_50: 170.80,
    rsi_14: 65.2,
    // ... more indicators
  },

  last_updated: ISODate("2026-02-05T10:30:00Z")
}

// Collection: watchlists
{
  _id: ObjectId("..."),
  user_id: "user123",  // Future: multi-user support
  name: "High Momentum Plays",
  symbols: ["NVDA", "AMD", "TSLA"],
  filters: {
    min_signal_quality: 75,
    event_types: ["earnings_report", "fda_approval"]
  },
  created_at: ISODate("...")
}
```

---

## 4. Analytics Engine

### 4.1 Signal Detection Pipeline

```python
class SignalDetector:
    """
    Multi-stage pipeline for opportunity identification
    """

    async def process_event(event: MarketEvent) -> Signal:
        # Stage 1: Event Classification
        event_category = classify_event(event)

        # Stage 2: Historical Pattern Matching
        similar_events = find_similar_historical_events(
            event_type=event.event_type,
            symbol_sector=event.sector,
            market_cap_range=(event.market_cap * 0.5, event.market_cap * 2)
        )
        historical_outcomes = analyze_outcomes(similar_events)

        # Stage 3: Real-Time Context
        current_price = get_live_price(event.symbol)
        volume_profile = get_volume_data(event.symbol, period='1d')
        sentiment = aggregate_sentiment(event.symbol, lookback_hours=24)

        # Stage 4: Technical Confluence
        technicals = get_technical_indicators(event.symbol)
        confluence = calculate_confluence(technicals, event)

        # Stage 5: Risk Factors
        risks = identify_risks(event, technicals, volume_profile)

        # Stage 6: Opportunity Scoring
        score = calculate_opportunity_score(
            event, historical_outcomes, confluence, sentiment, risks
        )

        return Signal(
            event_id=event.event_id,
            symbol=event.symbol,
            opportunity_score=score,
            direction="BULLISH" | "BEARISH" | "NEUTRAL",
            confidence=score.confidence,
            entry_price=current_price,
            targets=[...],
            stop_loss=calculate_stop_loss(current_price, technicals),
            risks=risks,
            reasoning=generate_reasoning(event, score)
        )
```

### 4.2 Opportunity Score Algorithm

**Formula:**
```
Opportunity_Score = (
    Signal_Quality * 0.25 +
    Impact_Potential * 0.20 +
    Technical_Confluence * 0.20 +
    Sentiment_Momentum * 0.15 +
    Volume_Confirmation * 0.10 +
    Historical_Win_Rate * 0.10
) * Risk_Multiplier

where Risk_Multiplier = (1 - Risk_Score)
```

#### Components:

**1. Signal Quality (0-100)**
```python
def calculate_signal_quality(event):
    quality = 50  # baseline

    # Source reliability
    if event.source in ['FMP', 'POLYGON']:
        quality += 15
    elif event.source == 'FINVIZ':
        quality += 10

    # Timeliness
    age_minutes = (now() - event.timestamp).total_seconds() / 60
    if age_minutes < 5:
        quality += 20
    elif age_minutes < 15:
        quality += 10

    # Event type importance
    if event.event_type in ['FDA_APPROVAL', 'EARNINGS_BEAT']:
        quality += 15
    elif event.event_type in ['INSIDER_BUY', 'ANALYST_UPGRADE']:
        quality += 10

    return min(quality, 100)
```

**2. Impact Potential (0-100)**
- Historical price movement after similar events (50%)
- Market cap impact (20% - smaller caps = higher impact)
- Volume spike magnitude (30%)

**3. Technical Confluence (0-100)**
- Price at key level (support/resistance): +20
- RSI favorable (<30 for bullish, >70 for bearish): +15
- Volume > 2x average: +20
- Breakout from consolidation: +25
- Moving average alignment: +20

**4. Sentiment Momentum (0-100)**
- News sentiment aggregate (last 24h): 40%
- Social media buzz (if available): 30%
- Sector sentiment: 30%

**5. Volume Confirmation (0-100)**
```python
volume_ratio = current_volume / avg_volume_20d
if volume_ratio > 5:
    score = 100
elif volume_ratio > 3:
    score = 80
elif volume_ratio > 2:
    score = 60
else:
    score = 40
```

**6. Historical Win Rate (0-100)**
- Backtest similar events in same sector
- Calculate % of times price moved favorably in next 1-3 days

**Risk Multiplier:**
```python
risk_score = 0

# Liquidity risk
if avg_daily_volume < 100_000:
    risk_score += 0.3

# Dilution risk (for biotech)
if sector == 'Healthcare' and event_type == 'FDA_APPROVAL':
    if balance_sheet['cash'] < 10_000_000:
        risk_score += 0.2

# Already priced in
if price_moved_before_news > 10%:
    risk_score += 0.25

# News verification
if source_count < 2:
    risk_score += 0.15

risk_multiplier = 1 - min(risk_score, 0.8)
```

---

## 5. Technology Stack

### 5.1 Backend Services

#### Core Services (Node.js/TypeScript)
- **Ingestion Service**: Data fetching + normalization
- **Analytics Service**: Signal detection + scoring
- **Alert Service**: WebSocket broadcasting + notifications
- **API Gateway**: REST endpoints + rate limiting

#### Message Queue
- **Apache Kafka**
  - Topics: raw-events, normalized-events, signals, alerts
  - Partitioning by symbol for parallel processing
  - Retention: 7 days (for replay/debugging)

#### Databases
- **TimescaleDB** (PostgreSQL extension)
  - Time-series events
  - Automatic compression after 7 days
  - Continuous aggregates for dashboards

- **MongoDB**
  - Stock profiles
  - Watchlists
  - User preferences (future)

- **Redis Cluster**
  - Live prices cache (TTL: 1 second)
  - Signal cache (TTL: 5 minutes)
  - Session management
  - Rate limiter state

#### Background Jobs (BullMQ + Redis)
- Periodic screener runs (every 5 minutes)
- Historical data backfill
- Technical indicator calculations
- Alert delivery

### 5.2 Frontend

#### Framework: **React 18** + **TypeScript**

#### State Management & Data Fetching
- **TanStack Query (React Query)** - Server state
- **Zustand** - UI state
- **WebSocket (native)** - Real-time updates

#### UI Components
- **shadcn/ui** + **Radix UI** - Accessible components
- **Recharts** - Stock charts
- **TanStack Table** - Data tables with virtual scrolling

#### Real-Time Updates
```typescript
// WebSocket connection
const ws = new WebSocket('wss://api.yourapp.com/live');

ws.onmessage = (event) => {
  const signal = JSON.parse(event.data);
  queryClient.setQueryData(['signals'], (old) => [signal, ...old]);

  // Toast notification for high-quality signals
  if (signal.opportunity_score > 80) {
    toast.success(`🚀 ${signal.symbol}: ${signal.title}`);
  }
};
```

### 5.3 Infrastructure

#### Deployment
- **Docker Compose** (local dev)
- **Kubernetes** (production) - AWS EKS or DigitalOcean Kubernetes

#### CI/CD
- **GitHub Actions**
  - Run tests on PR
  - Build Docker images
  - Deploy to staging → prod

#### Monitoring
- **Prometheus** + **Grafana**: Metrics (request latency, queue lag, error rates)
- **Sentry**: Error tracking
- **Loki**: Log aggregation

---

## 6. Dashboard Screens

### 6.1 Overview Screen
**Purpose**: At-a-glance market pulse

**Components:**
- Live signal feed (top 10, auto-refreshing)
- Top movers (% change, volume)
- Market sentiment gauge (aggregate)
- Active alerts count
- Hot sectors

### 6.2 Signals Screen
**Purpose**: Actionable opportunities

**Features:**
- Filterable table:
  - Min opportunity score slider (0-100)
  - Event types (multi-select)
  - Sectors
  - Direction (Bullish/Bearish/Neutral)
- Columns:
  - Symbol | Event | Score | Direction | Price | Time | Actions
- Click row → Detail modal:
  - Full reasoning
  - Risks
  - Chart with entry/targets/stop
  - "Add to Watchlist" button

### 6.3 Watchlist Screen
**Purpose**: Track selected stocks

**Features:**
- Multiple watchlists (tabs)
- Live price updates
- Alert configuration per symbol
- Quick chart previews
- Export to CSV

### 6.4 News & Catalysts Screen
**Purpose**: Comprehensive event feed

**Features:**
- Timeline view (today, this week)
- Filter by:
  - Event type
  - Symbols in watchlist
  - Min impact score
- Sentiment heatmap
- Earnings calendar integration

### 6.5 Analytics Screen
**Purpose**: Historical performance

**Features:**
- Signal accuracy metrics (win rate by event type)
- Top performing signals (last 30 days)
- Source reliability comparison
- Sector performance

---

## 7. Alert System

### 7.1 Alert Channels

#### In-App (WebSocket)
- Browser notifications (with permission)
- Toast messages
- Badge counts

#### Email
- Digest (daily summary)
- Immediate (high-priority signals)
- Using SendGrid/AWS SES

#### Telegram Bot
- Real-time messages
- Rich formatting (chart images, buttons)
- `/subscribe AAPL` commands

### 7.2 Alert Logic
```typescript
interface AlertRule {
  id: string;
  name: string;
  condition: {
    min_opportunity_score?: number;
    event_types?: EventType[];
    symbols?: string[];
    sectors?: string[];
    direction?: 'BULLISH' | 'BEARISH';
  };
  channels: ('in_app' | 'email' | 'telegram')[];
  throttle_minutes: number;  // Prevent spam
}

// Example
const rule: AlertRule = {
  name: "High-conviction biotech plays",
  condition: {
    min_opportunity_score: 85,
    event_types: ['FDA_APPROVAL', 'CLINICAL_TRIAL'],
    sectors: ['Healthcare']
  },
  channels: ['in_app', 'telegram'],
  throttle_minutes: 15
};
```

---

## 8. Risk Mitigation & Reliability

### 8.1 Data Quality

#### Validation Layer
```python
class EventValidator:
    def validate(event: MarketEvent) -> ValidationResult:
        errors = []

        # Required fields
        if not event.symbol or not event.title:
            errors.append("Missing required fields")

        # Symbol format
        if not re.match(r'^[A-Z]{1,5}$', event.symbol):
            errors.append(f"Invalid symbol: {event.symbol}")

        # Timestamp sanity
        if event.timestamp > now() + timedelta(minutes=5):
            errors.append("Timestamp in future")

        # Duplicate check
        if exists_in_last_hour(event.source, event.url):
            errors.append("Duplicate event")

        return ValidationResult(valid=len(errors)==0, errors=errors)
```

### 8.2 Fault Tolerance

#### Circuit Breaker Pattern
```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, timeout=60):
        self.failures = 0
        self.state = 'CLOSED'  # CLOSED | OPEN | HALF_OPEN

    async def call(self, func):
        if self.state == 'OPEN':
            if self.should_attempt_reset():
                self.state = 'HALF_OPEN'
            else:
                raise CircuitOpenError()

        try:
            result = await func()
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise e
```

#### Graceful Degradation
- If Finviz fails → rely on FMP + Polygon
- If real-time WebSocket fails → fall back to polling
- If sentiment API fails → use keyword-based fallback

### 8.3 Rate Limit Handling
- Exponential backoff (1s, 2s, 4s, 8s, 16s)
- Queue requests when approaching limit
- Monitor usage via `/health` endpoint

### 8.4 Data Retention
- Raw events: 30 days (hot storage), 1 year (cold storage/S3)
- Aggregated signals: 1 year
- Logs: 14 days
- User data: Indefinite (with GDPR compliance for future)

---

## 9. Performance Targets

### 9.1 Latency
- **Event ingestion → signal generation**: < 2 seconds (p95)
- **API response time**: < 100ms (p95)
- **WebSocket message delivery**: < 500ms

### 9.2 Throughput
- Handle 1000 events/minute across all sources
- Support 100 concurrent WebSocket connections
- Process 50 screener queries/second

### 9.3 Availability
- **Uptime SLA**: 99.5% (allow ~3.6 hours downtime/month)
- **Database backup**: Every 6 hours
- **Disaster recovery**: RTO = 4 hours, RPO = 1 hour

---

## 10. Security Considerations

### 10.1 API Keys
- Store in environment variables (never in code)
- Use secret manager (AWS Secrets Manager / HashiCorp Vault)
- Rotate keys quarterly

### 10.2 Authentication (Future Multi-User)
- JWT tokens with refresh mechanism
- Rate limiting per user
- Role-based access control (admin, trader, viewer)

### 10.3 Data Privacy
- No PII collection (initially)
- Audit logs for data access
- Encrypted data at rest (database encryption)

---

## 11. Cost Estimation (Monthly)

### Data Sources
- Finviz Elite: $39.50
- FMP Professional: $49
- Polygon Starter: $99
- newsfilter.io: ~$100 (estimated)
- Alpha Vantage Premium: $49.99
- **Total**: ~$337/month

### Infrastructure (AWS/DigitalOcean)
- Kubernetes cluster (3 nodes): $150
- TimescaleDB (managed): $50
- MongoDB Atlas (M10): $50
- Redis Cloud: $30
- S3 storage: $10
- SendGrid/SES: $10
- **Total**: ~$300/month

### **Grand Total**: ~$637/month

---

## 12. Next Steps → See IMPLEMENTATION_ROADMAP.md
