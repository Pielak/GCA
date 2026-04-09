#!/bin/bash
#
# GCA Production Startup Script
# Usage: ./start_production.sh
# Or with custom port: PORT=9000 ./start_production.sh
#

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PORT=${PORT:-8000}
WORKERS=${WORKERS:-4}
HOST=${HOST:-0.0.0.0}
LOG_LEVEL=${LOG_LEVEL:-info}

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}  GCA Production Server - Startup                          ${BLUE}║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"

# Check if .env exists
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo -e "${RED}❌ Error: .env file not found in $SCRIPT_DIR${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Environment file: .env${NC}"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Error: Python 3 not found${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✅ Python version: $PYTHON_VERSION${NC}"

# Check if uvicorn is installed
if ! python3 -c "import uvicorn" 2>/dev/null; then
    echo -e "${BLUE}ℹ️  Installing dependencies...${NC}"
    pip install -q -r "$SCRIPT_DIR/requirements.txt"
    echo -e "${GREEN}✅ Dependencies installed${NC}"
fi

# Check database connection
echo -e "${BLUE}ℹ️  Checking database connection...${NC}"
if python3 << 'EOF'
import os
os.chdir('/home/luiz/GCA_Produção')
try:
    from app.core.config import settings
    from sqlalchemy import create_engine
    engine = create_engine(str(settings.DATABASE_URL))
    with engine.connect() as conn:
        pass
    exit(0)
except Exception as e:
    print(f"Database error: {e}")
    exit(1)
EOF
then
    echo -e "${GREEN}✅ Database connection OK${NC}"
else
    echo -e "${RED}❌ Error: Cannot connect to database${NC}"
    exit 1
fi

# Start server
echo ""
echo -e "${BLUE}┌────────────────────────────────────────────────────────────┐${NC}"
echo -e "${BLUE}│${NC}  Starting GCA Production Server                            ${BLUE}│${NC}"
echo -e "${BLUE}│${NC}  Host: $HOST:$PORT                                         ${BLUE}│${NC}"
echo -e "${BLUE}│${NC}  Workers: $WORKERS                                          ${BLUE}│${NC}"
echo -e "${BLUE}│${NC}  Log Level: $LOG_LEVEL                                       ${BLUE}│${NC}"
echo -e "${BLUE}│${NC}  API Docs: http://localhost:$PORT/api/v1/docs              ${BLUE}│${NC}"
echo -e "${BLUE}│${NC}  Health Check: http://localhost:$PORT/health               ${BLUE}│${NC}"
echo -e "${BLUE}└────────────────────────────────────────────────────────────┘${NC}"
echo ""

# Start uvicorn server
cd "$SCRIPT_DIR"
exec python3 -m uvicorn app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level "$LOG_LEVEL"
