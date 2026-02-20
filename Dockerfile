# Stage 1: Use pre-built frontend dist (committed to repo)
# (No npm install/build needed — dist is pre-built locally and committed)

# Stage 2: Python backend + built frontend
FROM python:3.12-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Copy pre-built frontend dist
COPY frontend/dist ./frontend/dist

# Set working directory to backend
WORKDIR /app/backend

# Expose port (Railway uses dynamic PORT env var)
EXPOSE 8000

# Run the app — uses $PORT if set (Railway/Render), otherwise 8000
CMD sh -c "python3 -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
