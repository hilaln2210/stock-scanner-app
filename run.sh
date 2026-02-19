#!/bin/bash

# Quick run script (runs both backend and frontend)

echo "Starting Stock Scanner Dashboard..."

# Start backend in background
echo "Starting backend..."
cd backend
source venv/bin/activate
uvicorn app.main:app --reload &
BACKEND_PID=$!

# Wait a bit for backend to start
sleep 3

# Start frontend
echo "Starting frontend..."
cd ../frontend
npm run dev &
FRONTEND_PID=$!

# Trap Ctrl+C to kill both processes
trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT

echo ""
echo "==================================="
echo "Stock Scanner Dashboard is running"
echo "==================================="
echo ""
echo "Backend API: http://localhost:8000"
echo "API Docs:    http://localhost:8000/docs"
echo "Frontend:    http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop both servers"
echo ""

# Wait for both processes
wait
