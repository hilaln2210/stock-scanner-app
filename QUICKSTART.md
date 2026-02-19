# Quick Start Guide

## Option 1: Automated Setup (Recommended)

```bash
./setup.sh
```

This will:
- Create Python virtual environment
- Install all Python dependencies
- Install all Node.js dependencies
- Create .env configuration file

## Option 2: Manual Setup

### Backend Setup
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Frontend Setup
```bash
cd frontend
npm install
```

## Running the Application

### Option A: Run Both (Automated)
```bash
./run.sh
```

### Option B: Run Separately (Recommended for Development)

**Terminal 1 - Backend:**
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

## Access Points

- **Dashboard**: http://localhost:3000
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## First Steps

1. Wait 30 seconds for initial scrape to complete
2. Dashboard will populate with signals and news
3. Use filters to search by ticker, score, or stance
4. Click "Trigger Scrape" for manual refresh
5. Click any signal row to see full details

## Configuration

Edit `backend/.env` to customize:
- `SCRAPE_INTERVAL_MINUTES` - How often to scrape (default: 10)
- `FINVIZ_COOKIE` - Add your Finviz Elite cookie for enhanced data (optional)

## Troubleshooting

**Port already in use:**
```bash
# Kill processes on ports 3000 and 8000
killall -9 node
pkill -f uvicorn
```

**Dependencies errors:**
```bash
# Backend
cd backend
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Frontend
cd frontend
rm -rf node_modules package-lock.json
npm install
```

**No signals appearing:**
- Wait for initial scrape (check backend terminal for "Starting scheduled scrape...")
- Click "Trigger Scrape" button in UI
- Check backend logs for errors

## Next Steps

- Read [README.md](README.md) for full documentation
- Explore API at http://localhost:8000/docs
- Customize signal patterns in `backend/app/services/signal_engine.py`
- Add more data sources in `backend/app/scrapers/`
