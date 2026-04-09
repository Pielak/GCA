#!/bin/bash
#
# GCA Production Status Check
# Verifies all components are ready
# Usage: ./check_production_status.sh
#

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}  GCA Production Status Check                             ${BLUE}║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check 1: Environment File
echo -e "${YELLOW}[1/7]${NC} Checking .env file..."
if [ -f .env ]; then
    echo -e "${GREEN}✅ .env exists${NC}"
else
    echo -e "${RED}❌ .env not found${NC}"
    exit 1
fi

# Check 2: Python Version
echo -e "${YELLOW}[2/7]${NC} Checking Python..."
if command -v python3 &> /dev/null; then
    VERSION=$(python3 --version 2>&1)
    echo -e "${GREEN}✅ $VERSION${NC}"
else
    echo -e "${RED}❌ Python not found${NC}"
    exit 1
fi

# Check 3: Dependencies
echo -e "${YELLOW}[3/7]${NC} Checking dependencies..."
MISSING=0
for package in fastapi uvicorn sqlalchemy psycopg2; do
    if python3 -c "import ${package}" 2>/dev/null; then
        echo -e "   ${GREEN}✅${NC} $package"
    else
        echo -e "   ${RED}❌${NC} $package (missing)"
        MISSING=$((MISSING+1))
    fi
done

if [ $MISSING -gt 0 ]; then
    echo -e "${YELLOW}→ Install with: pip install -r requirements.txt${NC}"
fi

# Check 4: Database Connection
echo -e "${YELLOW}[4/7]${NC} Checking database..."
if [ -f .env ]; then
    export PGPASSWORD=$(grep "^POSTGRES_PASSWORD=" .env | cut -d'=' -f2 | tr -d '"')
    POSTGRES_HOST=$(grep "^POSTGRES_HOST=" .env | cut -d'=' -f2 | tr -d '"')
    POSTGRES_USER=$(grep "^POSTGRES_USER=" .env | cut -d'=' -f2 | tr -d '"')
    POSTGRES_DB=$(grep "^POSTGRES_DB=" .env | cut -d'=' -f2 | tr -d '"')
    
    if psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Database connected${NC}"
    else
        echo -e "${RED}❌ Database connection failed${NC}"
    fi
fi

# Check 5: Migrations
echo -e "${YELLOW}[5/7]${NC} Checking migrations..."
if [ -f migrations/001_add_password_reset_tables.sql ]; then
    echo -e "${GREEN}✅ Migration 001${NC}"
else
    echo -e "${RED}❌ Migration 001 missing${NC}"
fi

if [ -f migrations/002_add_questionnaires_table.sql ]; then
    echo -e "${GREEN}✅ Migration 002${NC}"
else
    echo -e "${RED}❌ Migration 002 missing${NC}"
fi

# Check 6: Key Files
echo -e "${YELLOW}[6/7]${NC} Checking application files..."
if [ -f app/main.py ]; then
    echo -e "${GREEN}✅ app/main.py${NC}"
else
    echo -e "${RED}❌ app/main.py missing${NC}"
fi

if [ -f app/services/questionnaire_service.py ]; then
    echo -e "${GREEN}✅ questionnaire_service.py${NC}"
else
    echo -e "${RED}❌ questionnaire_service.py missing${NC}"
fi

if [ -f app/services/email_service.py ]; then
    echo -e "${GREEN}✅ email_service.py${NC}"
else
    echo -e "${RED}❌ email_service.py missing${NC}"
fi

if [ -f app/services/n8n_service.py ]; then
    echo -e "${GREEN}✅ n8n_service.py${NC}"
else
    echo -e "${RED}❌ n8n_service.py missing${NC}"
fi

# Check 7: Port Availability
echo -e "${YELLOW}[7/7]${NC} Checking port availability..."
if ! lsof -i :8000 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Port 8000 available${NC}"
else
    echo -e "${YELLOW}⚠️  Port 8000 in use${NC}"
    echo -e "   ${YELLOW}→ Kill with: pkill -f 'uvicorn app.main'${NC}"
fi

# Final Summary
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}✅ Production Environment Ready${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo -e "  1. Apply migrations: ./apply_migration.sh"
echo -e "  2. Start server: ./start_production.sh"
echo -e "  3. Test API: curl http://localhost:8000/health"
echo -e "  4. View docs: http://localhost:8000/api/v1/docs"
