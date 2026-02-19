#!/bin/bash

echo "==================================="
echo "Stock Scanner Dashboard - Setup"
echo "==================================="

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check Python
echo -e "\n${BLUE}Checking Python...${NC}"
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Please install Python 3.11+"
    exit 1
fi
echo -e "${GREEN}✓ Python found: $(python3 --version)${NC}"

# Check Node
echo -e "\n${BLUE}Checking Node.js...${NC}"
if ! command -v node &> /dev/null; then
    echo "Node.js is not installed. Please install Node.js 18+"
    exit 1
fi
echo -e "${GREEN}✓ Node.js found: $(node --version)${NC}"

# Setup Backend
echo -e "\n${BLUE}Setting up backend...${NC}"
cd backend

echo "Creating virtual environment..."
python3 -m venv venv

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Creating .env file..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "${GREEN}✓ .env file created${NC}"
else
    echo ".env file already exists"
fi

cd ..

# Setup Frontend
echo -e "\n${BLUE}Setting up frontend...${NC}"
cd frontend

echo "Installing Node dependencies..."
npm install

cd ..

echo -e "\n${GREEN}==================================="
echo "Setup Complete!"
echo "===================================${NC}"

echo -e "\nTo run the application:"
echo -e "\n${BLUE}Terminal 1 (Backend):${NC}"
echo "  cd backend"
echo "  source venv/bin/activate"
echo "  uvicorn app.main:app --reload"
echo -e "\n${BLUE}Terminal 2 (Frontend):${NC}"
echo "  cd frontend"
echo "  npm run dev"
echo -e "\n${GREEN}Dashboard will be available at: http://localhost:3000${NC}"
