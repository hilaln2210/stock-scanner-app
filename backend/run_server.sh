#!/bin/bash
# Activate virtual environment
source venv/bin/activate

# Check if requirements are installed
echo "Checking dependencies..."
pip list | grep -q uvicorn || pip install -r requirements.txt

# Start server
echo "Starting Stock Scanner API..."
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
