#!/bin/bash
# ═══════════════════════════════════════════════════════════
# Stock Scanner — One-Click Deploy Script
# Run this ON THE REMOTE SERVER after cloning the project
# ═══════════════════════════════════════════════════════════

set -e

echo "══════════════════════════════════════"
echo "  Stock Scanner — Server Setup"
echo "══════════════════════════════════════"

# 1. Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    echo "Docker installed. You may need to log out and back in."
    echo "Then re-run this script."
    exit 0
fi

# 2. Install docker-compose if not present
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null 2>&1; then
    echo "Installing docker-compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# 3. Check .env file
if [ ! -f backend/.env ]; then
    echo ""
    echo "ERROR: backend/.env not found!"
    echo "Copy backend/.env.example to backend/.env and fill in your credentials."
    echo "  cp backend/.env.example backend/.env"
    echo "  nano backend/.env"
    exit 1
fi

# 4. Build and start
echo ""
echo "Building and starting Stock Scanner..."
docker compose up -d --build

echo ""
echo "══════════════════════════════════════"
echo "  ✓ Stock Scanner is running!"
echo "══════════════════════════════════════"
echo ""
echo "  Open in browser: http://$(hostname -I | awk '{print $1}'):8000"
echo "  API docs:        http://$(hostname -I | awk '{print $1}'):8000/docs"
echo ""
echo "  Commands:"
echo "    docker compose logs -f    # View logs"
echo "    docker compose restart    # Restart"
echo "    docker compose down       # Stop"
echo ""
