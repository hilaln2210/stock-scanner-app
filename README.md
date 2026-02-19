# Stock Scanner Dashboard

Real-time stock market signal detection and news aggregation dashboard.

## Features

- **Multi-Source News Ingestion**: Scrapes news from Finviz, Yahoo Finance, and MarketWatch
- **Signal Detection**: Automatically detects trading signals (FDA approvals, earnings beats/misses, analyst upgrades, M&A, etc.)
- **Opportunity Scoring**: Assigns scores (0-100) to each signal based on multiple factors
- **Real-Time Dashboard**: Clean UI with live signals, news feed, and filtering
- **Auto-Refresh**: Configurable auto-refresh (30s to 10min)
- **Deduplication**: Prevents duplicate news from multiple sources

## Tech Stack

### Backend
- Python 3.11+
- FastAPI (REST API)
- SQLAlchemy + SQLite (database)
- APScheduler (background scraping)
- BeautifulSoup4 + aiohttp (web scraping)

### Frontend
- React 18 + Vite
- TanStack Query (data fetching)
- TailwindCSS (styling)
- Lucide React (icons)

## Installation & Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- Git

### 1. Clone and Setup Backend

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Create .env file (optional)
cp .env.example .env
# Edit .env if you want to customize settings
```

### 2. Setup Frontend

```bash
cd frontend

# Install dependencies
npm install
```

## Running the Application

### Start Backend (Terminal 1)

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at http://localhost:8000
- API Docs: http://localhost:8000/docs

### Start Frontend (Terminal 2)

```bash
cd frontend
npm run dev
```

The dashboard will be available at http://localhost:3000

## Configuration

### Environment Variables (backend/.env)

```bash
# Scraping interval (minutes)
SCRAPE_INTERVAL_MINUTES=10

# Max news age to keep (hours)
MAX_NEWS_AGE_HOURS=48

# Optional: Finviz Elite credentials
FINVIZ_EMAIL=your-email@example.com
FINVIZ_PASSWORD=your-password
FINVIZ_COOKIE=your-cookie-string
```

**Note**: Finviz Elite is optional. The scraper works with public Finviz data. If you have Elite access, you can add credentials for enhanced data.

## Usage

1. **Initial Scrape**: The backend automatically scrapes on startup and then every 10 minutes (configurable)

2. **Manual Scrape**: Click "Trigger Scrape" button in the UI to force an immediate scrape

3. **Filtering**:
   - Search by ticker (e.g., "AAPL")
   - Filter by minimum score (0-100)
   - Filter by stance (All/Bullish/Bearish/Watchlist)
   - Set auto-refresh interval

4. **Signal Details**: Click any row in the signals table to see full details

## API Endpoints

### GET /api/signals
Get signals with optional filtering

Query Parameters:
- `ticker` (optional): Filter by ticker symbol
- `stance` (optional): Bullish, Bearish, or Watchlist
- `min_score` (optional): Minimum score threshold
- `limit` (optional): Max results (default: 100)

### GET /api/news
Get recent news events

Query Parameters:
- `source` (optional): Filter by source (finviz, yahoo, marketwatch)
- `ticker` (optional): Filter by ticker
- `hours` (optional): Lookback period in hours (default: 48)

### GET /api/dashboard/stats
Get dashboard statistics

Returns:
- Total signals
- Bullish/Bearish counts
- Average score
- Top tickers

### POST /api/scrape/trigger
Manually trigger a scrape cycle

## Signal Types Detected

- `earnings_beat` / `earnings_miss`
- `fda_approval` / `fda_rejection`
- `analyst_upgrade` / `analyst_downgrade`
- `merger_acquisition`
- `guidance_raise` / `guidance_lower`
- `offering` (dilutive)
- `lawsuit`
- `partnership`

## Score Calculation

Scores (0-100) are calculated based on:

1. **Base Score**: Each signal type has a base score (55-85)
2. **Sentiment Alignment**: Boost if sentiment matches stance (+0 to +10)
3. **Recency**: Recent news gets a boost (+0 to +10)
4. **Source Reliability**: Trusted sources get a boost (+3 to +5)

Higher scores indicate stronger opportunities.

## Project Structure

```
Stocks/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + scheduler
│   │   ├── config.py            # Configuration
│   │   ├── database.py          # Database setup
│   │   ├── models.py            # SQLAlchemy models
│   │   ├── schemas.py           # Pydantic schemas
│   │   ├── api/
│   │   │   └── routes.py        # API endpoints
│   │   ├── services/
│   │   │   ├── ingestion.py     # Orchestrates scrapers
│   │   │   ├── normalization.py # Data normalization
│   │   │   └── signal_engine.py # Signal generation
│   │   └── scrapers/
│   │       ├── finviz.py        # Finviz scraper
│   │       ├── yahoo.py         # Yahoo Finance scraper
│   │       └── marketwatch.py   # MarketWatch scraper
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Main app component
│   │   ├── main.jsx             # Entry point
│   │   ├── api/
│   │   │   └── client.js        # API client
│   │   └── components/
│   │       ├── StatsCards.jsx
│   │       ├── SignalsTable.jsx
│   │       ├── NewsPanel.jsx
│   │       └── FilterPanel.jsx
│   ├── package.json
│   └── vite.config.js
└── README.md
```

## Database

SQLite database (`stocks.db`) is created automatically with two main tables:

1. **news_events**: Stores normalized news from all sources
2. **signals**: Stores generated trading signals

To reset the database, simply delete `stocks.db` and restart the backend.

## Adding More Data Sources

To add a new scraper:

1. Create `backend/app/scrapers/your_source.py`
2. Implement a class with `async def scrape() -> List[ScraperResult]`
3. Add to `IngestionService` in `services/ingestion.py`

Example scraper template:

```python
from app.scrapers import ScraperResult
from typing import List

class YourScraper:
    async def scrape(self) -> List[ScraperResult]:
        results = []
        # Your scraping logic here
        results.append(ScraperResult(
            source="your_source",
            title="News title",
            url="https://...",
            published_at=datetime.now(),
            summary="Summary text",
            tickers=["AAPL", "TSLA"]
        ))
        return results
```

## Troubleshooting

### Backend won't start
- Check Python version: `python3 --version` (needs 3.11+)
- Ensure virtual environment is activated
- Check for port conflicts (port 8000)

### Frontend won't start
- Check Node version: `node --version` (needs 18+)
- Clear node_modules: `rm -rf node_modules && npm install`
- Check for port conflicts (port 3000)

### No signals appearing
- Wait for initial scrape to complete (~30 seconds)
- Click "Trigger Scrape" to force a scrape
- Check backend logs for errors
- Verify internet connection (scrapers need external access)

### Scraper errors
- Some sources may block requests (rate limiting, IP blocking)
- Try increasing scrape interval
- Add delays between requests
- Consider using a VPN or proxy

## Future Enhancements

- [ ] Add more data sources (SEC EDGAR, Reddit, Twitter)
- [ ] Machine learning for better signal scoring
- [ ] Price data integration (live charts)
- [ ] Alert notifications (email, Telegram, Discord)
- [ ] Backtesting framework
- [ ] User authentication and personalized watchlists
- [ ] PostgreSQL support for production
- [ ] Docker deployment
- [ ] Technical indicator integration

## License

MIT

## Disclaimer

This software is for educational and informational purposes only. It is not financial advice. Always do your own research before making investment decisions.
