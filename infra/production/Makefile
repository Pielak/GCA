.PHONY: help check migrate start stop logs test clean

# Colors
GREEN := \033[0;32m
BLUE := \033[0;34m
YELLOW := \033[1;33m
NC := \033[0m # No Color

help:
	@echo "$(BLUE)╔════════════════════════════════════════════════════════════╗$(NC)"
	@echo "$(BLUE)║$(NC)  GCA Production Management                               $(BLUE)║$(NC)"
	@echo "$(BLUE)╚════════════════════════════════════════════════════════════╝$(NC)"
	@echo ""
	@echo "$(GREEN)Available commands:$(NC)"
	@echo ""
	@echo "  $(YELLOW)make check$(NC)      - Check production environment status"
	@echo "  $(YELLOW)make migrate$(NC)    - Apply database migrations"
	@echo "  $(YELLOW)make start$(NC)      - Start production server"
	@echo "  $(YELLOW)make stop$(NC)       - Stop production server"
	@echo "  $(YELLOW)make logs$(NC)       - Show server logs (tail -f)"
	@echo "  $(YELLOW)make test$(NC)       - Run end-to-end tests"
	@echo "  $(YELLOW)make clean$(NC)      - Clean temporary files"
	@echo "  $(YELLOW)make help$(NC)       - Show this help message"
	@echo ""
	@echo "$(GREEN)Examples:$(NC)"
	@echo "  make check              # Check if everything is ready"
	@echo "  make migrate            # Apply database migrations"
	@echo "  make start              # Start the server"
	@echo "  PORT=9000 make start    # Start on custom port"
	@echo "  WORKERS=8 make start    # Start with 8 workers"
	@echo ""

check:
	@./check_production_status.sh

migrate:
	@./apply_migration.sh

start:
	@./start_production.sh

stop:
	@echo "$(YELLOW)Stopping GCA production server...$(NC)"
	@pkill -f "uvicorn app.main" || echo "$(YELLOW)No process found$(NC)"
	@echo "$(GREEN)✅ Server stopped$(NC)"

logs:
	@echo "$(BLUE)GCA Production Logs (Ctrl+C to exit)$(NC)"
	@echo ""
	@tail -f /var/log/gca/app.log 2>/dev/null || tail -f logs/app.log 2>/dev/null || echo "$(YELLOW)Log file not found$(NC)"

test:
	@echo "$(BLUE)Running end-to-end tests...$(NC)"
	@echo ""
	@echo "$(YELLOW)[1/4]$(NC) Health Check"
	@curl -s http://localhost:8000/health | jq . || echo "Server not responding"
	@echo ""
	@echo "$(YELLOW)[2/4]$(NC) Submit Questionnaire (Approval)"
	@curl -s -X POST http://localhost:8000/api/v1/questionnaires \
		-H "Content-Type: application/json" \
		-d '{"project_id":"550e8400-e29b-41d4-a716-446655440000","gp_email":"pielak.ctba@gmail.com","responses":{"frontend_stack":["React"],"backend_stack":["FastAPI"],"database_stack":["PostgreSQL"],"ai_automation":["Anthropic"],"security_controls":["Autenticação","Autorização / RBAC"],"deliverables":["Aplicação web"],"execution_mode":["Cloud"],"architecture_target":["Microserviços"],"infra_support":["Kafka"],"test_types":["Unitários"]}}' | jq .
	@echo ""
	@echo "$(YELLOW)[3/4]$(NC) Check Database"
	@psql -h localhost -U gca -d gca -c "SELECT COUNT(*) as questionnaires FROM questionnaires;" 2>/dev/null || echo "Database not accessible"
	@echo ""
	@echo "$(YELLOW)[4/4]$(NC) API Documentation"
	@echo "$(GREEN)✅ Available at: http://localhost:8000/api/v1/docs$(NC)"
	@echo ""

clean:
	@echo "$(YELLOW)Cleaning temporary files...$(NC)"
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name ".DS_Store" -delete 2>/dev/null || true
	@echo "$(GREEN)✅ Cleanup complete$(NC)"

install-deps:
	@echo "$(BLUE)Installing dependencies...$(NC)"
	@pip install -q -r requirements.txt
	@echo "$(GREEN)✅ Dependencies installed$(NC)"

verify-db:
	@echo "$(BLUE)Verifying database...$(NC)"
	@export PGPASSWORD=$$(grep POSTGRES_PASSWORD .env | cut -d'=' -f2 | tr -d '"'); \
	psql -h localhost -U gca -d gca -c "\dt questionnaires;" || echo "Table not found - run 'make migrate'"

version:
	@grep APP_VERSION .env | cut -d'=' -f2

status:
	@echo "$(BLUE)GCA Production Status$(NC)"
	@echo ""
	@if pgrep -f "uvicorn app.main" > /dev/null; then \
		echo "$(GREEN)✅ Server is running$(NC)"; \
		pgrep -f "uvicorn app.main" | xargs ps -p; \
	else \
		echo "$(YELLOW)⚠️  Server is not running$(NC)"; \
	fi
	@echo ""

.DEFAULT_GOAL := help
