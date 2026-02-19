# Implementation Roadmap - Stock Scanner Dashboard

## Overview
פירוק המערכת ל-6 מילסטונים עיקריים, כאשר כל אחד מספק ערך עצמאי וניתן לבדיקה. גישה iterative שמאפשרת לקבל feedback מהר ולהתאים את הכיוון.

**סך הכל זמן משוער:** 8-12 שבועות לגרסה פונקציונלית ראשונה (MVP)

---

## Milestone 1: Foundation & Data Ingestion (Week 1-2)

### Objective
בניית תשתית בסיסית + חיבור ל-2 מקורות נתונים ראשוניים

### Deliverables

#### 1.1 Project Setup
- [ ] Repository initialization
  - Git structure: `/backend`, `/frontend`, `/docs`
  - Docker Compose for local development
  - Environment variables template (`.env.example`)
- [ ] Backend scaffolding (Node.js + TypeScript)
  - Express.js API server
  - Project structure: `/src/{services,models,routes,utils}`
  - ESLint + Prettier configuration
- [ ] Database setup
  - Docker container: PostgreSQL 15 + TimescaleDB extension
  - Docker container: Redis
  - Database migrations framework (TypeORM / Prisma)
- [ ] CI/CD skeleton
  - GitHub Actions: lint + test on PR

#### 1.2 Data Source Integration - Finviz
- [ ] Finviz scraper module
  ```
  /backend/src/services/ingestion/finviz/
    ├── auth.ts          # Login & session management
    ├── scraper.ts       # HTML parsing logic
    ├── news.ts          # News feed parser
    ├── screener.ts      # Screener results parser
    └── types.ts         # Type definitions
  ```
- [ ] Authentication flow
  - Login with Elite credentials
  - Cookie persistence in Redis
  - Auto re-authentication on 401
- [ ] News feed scraper (`finviz.com/news.ashx`)
  - Parse: headline, timestamp, URL, ticker(s)
  - Handle pagination
  - Deduplication (by URL)
- [ ] Rate limiter implementation
  - Token bucket algorithm
  - 100 requests/minute limit
  - Exponential backoff on errors

#### 1.3 Data Source Integration - FMP
- [ ] FMP API client
  ```
  /backend/src/services/ingestion/fmp/
    ├── client.ts        # HTTP client wrapper
    ├── news.ts          # News endpoint
    ├── filings.ts       # SEC filings endpoint
    ├── fundamentals.ts  # Company data
    └── types.ts
  ```
- [ ] Endpoints implementation:
  - `/v3/stock_news` - Real-time news
  - `/v3/sec_filings/{symbol}` - 8-K, 10-Q, 10-K
  - `/v3/profile/{symbol}` - Company profile + market cap
- [ ] Rate limiter (250 calls/min)
- [ ] Error handling + retry logic

#### 1.4 Data Normalization Pipeline
- [ ] Unified `MarketEvent` schema implementation
- [ ] Source-specific mappers:
  ```typescript
  interface DataMapper {
    normalize(raw: any): MarketEvent;
    validate(event: MarketEvent): ValidationResult;
  }

  class FinvizNewsMapper implements DataMapper { ... }
  class FMPNewsMapper implements DataMapper { ... }
  ```
- [ ] Validation rules:
  - Required fields check
  - Symbol format validation
  - Timestamp sanity check
  - Duplicate detection

#### 1.5 Storage Layer
- [ ] TimescaleDB schema creation
  ```sql
  CREATE TABLE market_events (...);
  CREATE HYPERTABLE ...;
  CREATE INDEXES ...;
  ```
- [ ] Repository pattern implementation
  ```typescript
  class MarketEventRepository {
    async save(event: MarketEvent): Promise<void>;
    async findBySymbol(symbol: string, limit: number): Promise<MarketEvent[]>;
    async findRecent(minutes: number): Promise<MarketEvent[]>;
  }
  ```

#### 1.6 Testing
- [ ] Unit tests for parsers (80%+ coverage)
- [ ] Integration tests for database operations
- [ ] Mock data fixtures for development

### Success Criteria
- ✅ Successfully scrape Finviz news every 5 minutes
- ✅ Successfully fetch FMP news via API
- ✅ Store normalized events in TimescaleDB
- ✅ No crashes for 24 hours continuous run
- ✅ All tests passing

### Technical Risks
- **Finviz HTML changes** → Implement robust selectors + monitoring
- **Rate limiting** → Conservative limits + queue system
- **Session expiration** → Automatic re-auth flow

---

## Milestone 2: Basic Analytics & Scoring (Week 3-4)

### Objective
מנוע ניקוד בסיסי שמחשב Opportunity Score לכל אירוע

### Deliverables

#### 2.1 Real-Time Price Data Integration
- [ ] Polygon.io WebSocket client
  ```typescript
  class PolygonWebSocketClient {
    connect(): void;
    subscribe(symbols: string[]): void;
    onTrade(callback: (trade: Trade) => void): void;
  }
  ```
- [ ] Price cache in Redis
  - Key: `price:{symbol}` → `{price: 123.45, timestamp: ...}`
  - TTL: 5 seconds
- [ ] Fallback to REST API if WebSocket fails

#### 2.2 Technical Indicators Service
- [ ] Indicators calculation module
  ```typescript
  class TechnicalIndicators {
    calculateRSI(symbol: string, period: number): Promise<number>;
    calculateSMA(symbol: string, period: number): Promise<number>;
    getVolumeProfile(symbol: string, days: number): Promise<VolumeData>;
    detectBreakout(symbol: string): Promise<boolean>;
  }
  ```
- [ ] Use existing library (e.g., `technicalindicators` npm package)
- [ ] Cache results (Redis, TTL: 5 minutes)

#### 2.3 Opportunity Score Engine - Core
- [ ] Implement 6 scoring components (see OPPORTUNITY_SCORE.md):
  1. Signal Quality calculator
  2. Impact Potential calculator
  3. Technical Confluence calculator
  4. Sentiment Momentum calculator (basic version)
  5. Volume Confirmation calculator
  6. Historical Win Rate (stub for now - will implement in Milestone 4)

- [ ] Master formula implementation:
  ```typescript
  class OpportunityScorer {
    async calculateScore(event: MarketEvent): Promise<OpportunityScore>;
  }
  ```

#### 2.4 Risk Assessment Module
- [ ] Risk factors detection:
  - Liquidity risk (volume check)
  - Spread risk (bid-ask)
  - Dilution risk (balance sheet check)
  - Price-in risk (pre-news price movement)
- [ ] Risk multiplier calculation
- [ ] Risk explanation generation (text)

#### 2.5 Signal Generation Service
- [ ] Listen to `market_events` stream (Kafka or direct DB)
- [ ] For each event:
  1. Fetch live price
  2. Calculate technical indicators
  3. Calculate opportunity score
  4. Assess risks
  5. Generate reasoning text
  6. Save to `signals` table
- [ ] Store signals:
  ```sql
  CREATE TABLE signals (
    signal_id UUID PRIMARY KEY,
    event_id UUID REFERENCES market_events(event_id),
    symbol VARCHAR(10),
    opportunity_score NUMERIC(5,2),
    direction VARCHAR(10),  -- BULLISH | BEARISH | NEUTRAL
    confidence NUMERIC(3,2),
    entry_price NUMERIC(12,4),
    reasoning TEXT,
    risks JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
  );
  ```

#### 2.6 Testing
- [ ] Unit tests for each scoring component
- [ ] Integration test: end-to-end from event → signal
- [ ] Test with historical data (manually collected samples)

### Success Criteria
- ✅ Generate opportunity score for every incoming event
- ✅ Scores reflect expected patterns (e.g., high for FDA approvals, low for routine 10-Q)
- ✅ Processing latency < 2 seconds (p95)
- ✅ All components tested with realistic data

### Technical Risks
- **Inaccurate indicators** → Validate against known values (e.g., Yahoo Finance)
- **Slow calculations** → Cache aggressively, optimize queries
- **Missing price data** → Graceful degradation (lower score, flag as incomplete)

---

## Milestone 3: REST API & Basic Frontend (Week 5-6)

### Objective
דשבורד פשוט שמציג סיגנלים בזמן אמת

### Deliverables

#### 3.1 REST API Endpoints
```typescript
// GET /api/signals
// Query params: ?limit=50&min_score=70&direction=BULLISH&symbol=AAPL
router.get('/api/signals', SignalController.getSignals);

// GET /api/signals/:signal_id
router.get('/api/signals/:id', SignalController.getSignalDetail);

// GET /api/events
// Query params: ?symbol=AAPL&event_type=FDA_APPROVAL&hours=24
router.get('/api/events', EventController.getEvents);

// GET /api/stocks/:symbol
// Returns: profile, live price, recent signals, technicals
router.get('/api/stocks/:symbol', StockController.getStockInfo);

// GET /api/screener
// Run custom screener with filters
router.get('/api/screener', ScreenerController.runScreener);

// Health check
router.get('/health', HealthController.check);
```

#### 3.2 API Documentation
- [ ] OpenAPI (Swagger) specification
- [ ] Interactive docs at `/api-docs`

#### 3.3 Frontend Setup (React + TypeScript)
- [ ] Vite project setup
- [ ] React Router v6
- [ ] TanStack Query for data fetching
- [ ] Zustand for UI state
- [ ] shadcn/ui components library
- [ ] Tailwind CSS

#### 3.4 Frontend - Signals Screen
- [ ] Signals table component
  - Columns: Symbol, Event, Score, Direction, Price, Time, Actions
  - Virtual scrolling (TanStack Virtual) for performance
  - Real-time updates (polling every 10 seconds initially)
- [ ] Filter panel:
  - Min score slider (0-100)
  - Direction toggle (All / Bullish / Bearish)
  - Event type multi-select
  - Symbol search
- [ ] Signal detail modal
  - Full event description
  - Opportunity score breakdown (bar chart)
  - Risks list
  - Mini price chart (optional in this milestone)

#### 3.5 Frontend - Overview Screen
- [ ] Live signal feed (latest 20 signals, auto-refresh)
- [ ] Top movers widget (top 10 by % change today)
- [ ] Market sentiment gauge (aggregate sentiment)
- [ ] Stats cards:
  - Total signals today
  - Avg opportunity score
  - Hot sectors

#### 3.6 Frontend - Stock Detail Page
- [ ] Route: `/stock/:symbol`
- [ ] Display:
  - Company name, sector, market cap
  - Current price (live)
  - Recent signals (last 7 days)
  - Recent events (last 7 days)
  - Basic technical data (RSI, MAs)

#### 3.7 Error Handling & Loading States
- [ ] Global error boundary
- [ ] Skeleton loaders for tables
- [ ] Toast notifications (success/error)

### Success Criteria
- ✅ Frontend displays live signals from API
- ✅ Filtering works correctly
- ✅ Modal shows full signal details
- ✅ Page loads < 2 seconds on 3G connection
- ✅ Mobile responsive (basic)

### Technical Risks
- **API performance** → Add database indexes, implement caching
- **Large result sets** → Implement cursor-based pagination
- **Real-time updates** → Will add WebSockets in Milestone 5

---

## Milestone 4: Advanced Analytics & Historical Data (Week 7-8)

### Objective
הוספת backtest, historical win rate, ו-sentiment analysis

### Deliverables

#### 4.1 Historical Data Backfill
- [ ] Script to fetch historical data:
  - FMP: news archive (last 3 months)
  - FMP: SEC filings archive
  - Polygon: historical prices (last 6 months)
- [ ] Run once to populate database
- [ ] Document process for future backfills

#### 4.2 Sentiment Analysis Service
- [ ] Integrate sentiment provider:
  - **Option A**: Alpha Vantage `/NEWS_SENTIMENT` API
  - **Option B**: Local NLP model (e.g., FinBERT)
  - **Option C**: Simple keyword-based (interim solution)
- [ ] Enrich `market_events` with sentiment score (-1 to +1)
- [ ] Aggregate sentiment per symbol (24h rolling window)

#### 4.3 Historical Win Rate Calculator
- [ ] Query similar historical signals:
  ```typescript
  class HistoricalAnalyzer {
    async findSimilarSignals(
      event_type: EventType,
      sector: string,
      market_cap_range: [number, number],
      lookback_days: number
    ): Promise<Signal[]>;

    async calculateWinRate(signals: Signal[]): Promise<number>;
  }
  ```
- [ ] Outcome determination logic:
  - Fetch price 1d, 3d after signal
  - Compare to entry price
  - Win if moved >5% in expected direction
- [ ] Integrate into Opportunity Score calculation (Component #6)

#### 4.4 Backtesting Framework
- [ ] Replay historical events through current scoring algorithm
- [ ] Generate report:
  - Total signals generated
  - Win rate by score range (e.g., 80-100: 68%, 60-79: 52%)
  - Avg return per score range
  - Max drawdown simulation
- [ ] Store results in `backtest_results` table

#### 4.5 Calibration Tool
- [ ] Compare predicted score ranges vs actual outcomes
- [ ] Highlight components that need retuning
- [ ] Suggest weight adjustments (manual for now, auto later)

#### 4.6 Analytics Dashboard (Frontend)
- [ ] New screen: `/analytics`
- [ ] Widgets:
  - Win rate by score range (bar chart)
  - Win rate by event type (table)
  - Cumulative returns chart (simulate $10k starting capital)
  - Source reliability comparison
  - Sector performance heatmap

### Success Criteria
- ✅ Historical win rate component returns realistic values (40-70%)
- ✅ Backtesting shows overall win rate >50% for scores >70
- ✅ Sentiment scores correlate with actual news tone
- ✅ Analytics dashboard loads in <3 seconds

### Technical Risks
- **Historical data quality** → Validate against known events
- **Survivorship bias** → Include delisted stocks if possible
- **Overfitting** → Keep validation set separate (last 30 days)

---

## Milestone 5: Real-Time WebSockets & Alerts (Week 9-10)

### Objective
עדכונים בזמן אמת + מערכת התראות

### Deliverables

#### 5.1 WebSocket Server
- [ ] Implement WebSocket endpoint: `wss://api.yourapp.com/live`
- [ ] Event types:
  ```typescript
  type WSMessage =
    | { type: 'signal_new', data: Signal }
    | { type: 'signal_update', data: Signal }
    | { type: 'price_update', data: { symbol: string, price: number } }
    | { type: 'event_new', data: MarketEvent };
  ```
- [ ] Authentication (optional for MVP, required for multi-user)
- [ ] Room-based subscriptions:
  ```typescript
  ws.send({ type: 'subscribe', room: 'signals' });
  ws.send({ type: 'subscribe', room: 'prices', symbols: ['AAPL', 'TSLA'] });
  ```

#### 5.2 Event Broadcasting Service
- [ ] Listen to new signals from database (or Kafka topic)
- [ ] Broadcast to all connected WebSocket clients
- [ ] Throttle: max 1 message per symbol per 5 seconds (prevent spam)

#### 5.3 Frontend - WebSocket Integration
- [ ] WebSocket hook:
  ```typescript
  const { lastMessage, sendMessage } = useWebSocket('wss://...');

  useEffect(() => {
    if (lastMessage?.type === 'signal_new') {
      queryClient.setQueryData(['signals'], (old) => [lastMessage.data, ...old]);
      toast(`🚀 New signal: ${lastMessage.data.symbol}`);
    }
  }, [lastMessage]);
  ```
- [ ] Auto-reconnect on disconnect
- [ ] Connection status indicator (green dot in navbar)

#### 5.4 Alert Rules System (Backend)
- [ ] Database schema:
  ```sql
  CREATE TABLE alert_rules (
    rule_id UUID PRIMARY KEY,
    user_id UUID,  -- NULL for single-user MVP
    name VARCHAR(100),
    conditions JSONB,  -- {min_score: 80, symbols: [...], event_types: [...]}
    channels TEXT[],   -- ['in_app', 'email']
    throttle_minutes INT DEFAULT 15,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ
  );
  ```
- [ ] Alert matcher service:
  ```typescript
  class AlertMatcher {
    async checkSignal(signal: Signal): Promise<AlertRule[]>;
    async sendAlert(rule: AlertRule, signal: Signal): Promise<void>;
  }
  ```

#### 5.5 Alert Channels
- [ ] **In-App**: WebSocket message `{ type: 'alert', ... }`
- [ ] **Email**: SendGrid integration
  - Template: HTML email with signal details
  - Rate limit: max 10 emails/hour per user
- [ ] **Telegram Bot** (optional):
  - Bot setup with BotFather
  - `/start` command to get chat ID
  - `/subscribe AAPL` command
  - Rich message formatting

#### 5.6 Frontend - Alert Configuration
- [ ] New screen: `/alerts`
- [ ] Alert rules CRUD:
  - Create new rule form
  - List existing rules (enable/disable toggle)
  - Edit rule modal
  - Delete rule (with confirmation)

### Success Criteria
- ✅ WebSocket delivers new signals within 1 second of generation
- ✅ Browser notifications work (with permission)
- ✅ Email alerts sent successfully
- ✅ No duplicate alerts within throttle window
- ✅ Reconnection works after network interruption

### Technical Risks
- **WebSocket scalability** → Use Socket.io with Redis adapter for multi-instance
- **Browser notification spam** → Respect throttle, allow mute
- **Email deliverability** → Avoid spam filters (SPF, DKIM, proper content)

---

## Milestone 6: Watchlists, Advanced Features & Polish (Week 11-12)

### Objective
פיצ'רים נוספים + UX improvements

### Deliverables

#### 6.1 Watchlist System (Backend)
- [ ] MongoDB schema:
  ```javascript
  {
    _id: ObjectId,
    user_id: null,  // Future: user authentication
    name: "High Momentum Plays",
    symbols: ["NVDA", "AMD"],
    filters: {
      min_score: 75,
      event_types: ["earnings_report", "fda_approval"]
    },
    created_at: ISODate
  }
  ```
- [ ] API endpoints:
  ```
  POST   /api/watchlists          - Create watchlist
  GET    /api/watchlists          - List watchlists
  PUT    /api/watchlists/:id      - Update watchlist
  DELETE /api/watchlists/:id      - Delete watchlist
  POST   /api/watchlists/:id/symbols - Add symbol
  DELETE /api/watchlists/:id/symbols/:symbol - Remove symbol
  ```

#### 6.2 Frontend - Watchlist Screen
- [ ] Route: `/watchlists`
- [ ] Multiple watchlist support (tabs)
- [ ] Symbol table with live prices:
  - Symbol | Name | Price | Change % | Last Signal | Score | Actions
- [ ] Add symbol button (search autocomplete)
- [ ] Quick actions: Remove, View Details, Set Alert
- [ ] Export to CSV

#### 6.3 News & Catalysts Screen
- [ ] Route: `/news`
- [ ] Timeline view (grouped by date)
- [ ] Filters:
  - Date range picker
  - Event type multi-select
  - Symbols in watchlist toggle
  - Min impact score slider
- [ ] Sentiment heatmap (grid: symbols × dates)
- [ ] Earnings calendar widget (upcoming earnings in next 2 weeks)

#### 6.4 Stock Charts Integration
- [ ] Add lightweight-charts or Recharts
- [ ] Candlestick chart with:
  - Price overlay (SMA 20, 50, 200)
  - Volume bars
  - Event markers (dots at signal timestamps)
- [ ] Timeframe selector (1D, 5D, 1M, 3M)
- [ ] Embed in:
  - Signal detail modal
  - Stock detail page

#### 6.5 Performance Optimizations
- [ ] Database query optimization:
  - Add composite indexes for common queries
  - Analyze slow queries (pg_stat_statements)
- [ ] API response caching:
  - Redis cache for `/api/signals` (TTL: 30s)
  - ETags for conditional requests
- [ ] Frontend optimizations:
  - Code splitting (React.lazy)
  - Image optimization (WebP)
  - Service worker for offline access

#### 6.6 Error Monitoring & Logging
- [ ] Integrate Sentry (error tracking)
- [ ] Structured logging (Winston/Pino)
  - Correlation IDs for request tracing
  - Log levels: debug, info, warn, error
- [ ] Metrics collection (Prometheus):
  - Request count/latency by endpoint
  - Signal generation rate
  - WebSocket connection count

#### 6.7 UI/UX Polish
- [ ] Dark mode support
- [ ] Keyboard shortcuts:
  - `/` - Focus search
  - `Ctrl+K` - Command palette (filter, navigate)
  - `Esc` - Close modal
- [ ] Tooltips for technical terms (RSI, P/E, etc.)
- [ ] Loading skeletons (replace spinners)
- [ ] Empty states (no signals, no watchlists)

#### 6.8 Documentation
- [ ] README.md:
  - Project overview
  - Setup instructions (Docker Compose)
  - Environment variables reference
- [ ] API documentation (Swagger UI)
- [ ] User guide:
  - How to interpret opportunity scores
  - How to set up alerts
  - How to use watchlists

### Success Criteria
- ✅ Watchlists persist and update in real-time
- ✅ Charts render smoothly (60 FPS)
- ✅ All screens have empty states
- ✅ Dark mode works across entire app
- ✅ Documentation is complete and clear

### Technical Risks
- **Chart performance** → Limit data points, use canvas rendering
- **MongoDB vs Postgres** → Consider moving watchlists to Postgres if sync issues arise

---

## Post-MVP Enhancements (Future Roadmap)

### Phase 2: Intelligence & Automation (Month 4-5)
- [ ] Machine learning layer (XGBoost for scoring)
- [ ] Options flow integration (unusual activity)
- [ ] Automated trading integration (broker APIs - Alpaca, IBKR)
- [ ] Paper trading simulator

### Phase 3: Multi-User & Collaboration (Month 6)
- [ ] User authentication (Auth0 / Clerk)
- [ ] Multi-user support (separate watchlists, alerts)
- [ ] Shared watchlists & social features
- [ ] Performance tracking (trades log, P&L)

### Phase 4: Advanced Data Sources (Month 7-8)
- [ ] Social media sentiment (Twitter/Reddit APIs)
- [ ] Insider trading detailed analysis (Form 4 parsing)
- [ ] Short interest data
- [ ] Institutional holdings (13F filings)
- [ ] Whale wallet tracking (for crypto, if expanding)

### Phase 5: Mobile App (Month 9-10)
- [ ] React Native app (iOS + Android)
- [ ] Push notifications
- [ ] Biometric authentication
- [ ] Offline mode

---

## Resource Requirements

### Development Team (Ideal)
- **Full-Stack Engineer** (1) - Lead developer
- **Data Engineer** (0.5 FTE) - Data pipelines, optimization
- **DevOps Engineer** (0.25 FTE) - Infrastructure, CI/CD
- **UI/UX Designer** (0.25 FTE) - Design system, user flows

### For Solo Developer
- Prioritize:
  1. Core functionality (Milestones 1-3)
  2. Analytics (Milestone 4)
  3. Real-time updates (Milestone 5)
  4. Polish (Milestone 6 - iterative)
- Skip initially:
  - Telegram bot
  - Complex charts
  - Machine learning
- Use managed services to reduce DevOps burden:
  - Railway / Render for hosting
  - Supabase for database + auth (future)
  - Vercel for frontend

---

## Risk Mitigation Summary

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Finviz blocks scraping | HIGH | Monitor for bans, implement delays, add CAPTCHA detection |
| API cost overruns | MEDIUM | Set billing alerts, implement request quotas |
| Database performance | MEDIUM | Optimize queries early, use TimescaleDB compression |
| WebSocket scaling issues | LOW | Use Socket.io with Redis adapter, load test |
| Scoring algorithm inaccuracy | MEDIUM | Backtest continuously, A/B test changes |
| Data quality problems | MEDIUM | Robust validation, cross-source verification |

---

## Success Metrics (KPIs)

### Technical Metrics
- **Uptime**: >99% (max 7 hours downtime/month)
- **Latency**: API p95 <100ms, signal generation <2s
- **Throughput**: Handle 1000 events/minute
- **Test coverage**: >70%

### Product Metrics (Post-Launch)
- **Signal accuracy**: Win rate >55% for scores 70-100
- **User engagement**: >5 sessions per week per active user
- **Alert value**: >30% of alerts result in watchlist add
- **Data freshness**: 90% of signals within 5 minutes of news

---

## Budget Recap

### Monthly Recurring Costs
- **Data APIs**: ~$337/month
- **Infrastructure**: ~$300/month
- **Total**: ~$637/month

### One-Time Costs
- **Domain + SSL**: $20/year
- **Development tools**: $0 (use free tiers: VS Code, Git, etc.)

### Cost Optimization Tips
- Start with free tiers (Finnhub, Alpha Vantage)
- Use single VPS instead of Kubernetes initially (DigitalOcean $50/month)
- Limit historical data retention (30 days vs 1 year)
- **Reduced MVP budget: ~$400/month**

---

## Next Immediate Steps

1. **Day 1**:
   - Create GitHub repository
   - Set up Docker Compose (Postgres + Redis)
   - Initialize backend + frontend projects

2. **Day 2-3**:
   - Implement Finviz scraper (auth + news parser)
   - Create database schema
   - Write unit tests

3. **Day 4-5**:
   - Integrate FMP API
   - Build normalization pipeline
   - Test end-to-end ingestion

4. **End of Week 1**:
   - Have data flowing into database
   - Deploy to staging (Railway/Render)
   - Set up monitoring (Sentry)

5. **Week 2**:
   - Begin Milestone 2 (Analytics)
   - ...

---

**Ready to start building?** פתח issue חדש עבור Milestone 1.1 והתחל לקודד! 🚀

**Version:** 1.0
**Last Updated:** 2026-02-05
