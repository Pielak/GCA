#!/bin/bash
#
# GCA Database Migration Script
# Applies database schema migrations
# Usage: ./apply_migration.sh
#

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}  GCA Database Migration                                   ${BLUE}║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"

# Check environment
if [ ! -f .env ]; then
    echo -e "${RED}❌ Error: .env file not found${NC}"
    echo -e "${YELLOW}Please run this script from the GCA_Produção directory${NC}"
    exit 1
fi

# Extract database connection from .env
export PGPASSWORD=$(grep "^POSTGRES_PASSWORD=" .env | cut -d'=' -f2 | tr -d '"')
POSTGRES_HOST=$(grep "^POSTGRES_HOST=" .env | cut -d'=' -f2 | tr -d '"')
POSTGRES_PORT=$(grep "^POSTGRES_PORT=" .env | cut -d'=' -f2 | tr -d '"')
POSTGRES_USER=$(grep "^POSTGRES_USER=" .env | cut -d'=' -f2 | tr -d '"')
POSTGRES_DB=$(grep "^POSTGRES_DB=" .env | cut -d'=' -f2 | tr -d '"')

echo -e "${GREEN}✅ Database Configuration:${NC}"
echo -e "   Host: $POSTGRES_HOST:$POSTGRES_PORT"
echo -e "   User: $POSTGRES_USER"
echo -e "   Database: $POSTGRES_DB"

# Test connection
echo ""
echo -e "${BLUE}ℹ️  Testing database connection...${NC}"
if psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Database connection OK${NC}"
else
    echo -e "${RED}❌ Error: Cannot connect to database${NC}"
    exit 1
fi

# Apply migrations
echo ""
echo -e "${BLUE}ℹ️  Applying migrations...${NC}"

# Migration 001
echo -e "${YELLOW}→ Migration 001: Password Reset Tables${NC}"
if [ -f migrations/001_add_password_reset_tables.sql ]; then
    psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        -f migrations/001_add_password_reset_tables.sql
    echo -e "${GREEN}✅ Migration 001 applied${NC}"
else
    echo -e "${YELLOW}⚠️  Migration 001 not found (may already be applied)${NC}"
fi

# Migration 002
echo ""
echo -e "${YELLOW}→ Migration 002: Questionnaires Table${NC}"
if [ -f migrations/002_add_questionnaires_table.sql ]; then
    psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        -f migrations/002_add_questionnaires_table.sql
    echo -e "${GREEN}✅ Migration 002 applied${NC}"
else
    echo -e "${RED}❌ Migration 002 not found${NC}"
    exit 1
fi

# Verify
echo ""
echo -e "${BLUE}ℹ️  Verifying schema...${NC}"

echo -e "${YELLOW}→ Checking questionnaires table:${NC}"
psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "SELECT table_name FROM information_schema.tables WHERE table_name='questionnaires';"

echo ""
echo -e "${YELLOW}→ Questionnaires table columns:${NC}"
psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "\d questionnaires"

# Success
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║${NC}  ✅ All migrations applied successfully!                ${GREEN}║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo -e "  1. Start the server: ./start_production.sh"
echo -e "  2. Check API docs: http://localhost:8000/api/v1/docs"
echo -e "  3. Test submission: curl -X POST http://localhost:8000/api/v1/questionnaires ..."
