# 🚀 GCA Production — QUICK DEPLOY GUIDE

**Location**: `/home/luiz/GCA_Produção/`  
**Status**: 🟢 Ready to deploy  
**Time needed**: 5 minutes

---

## 3-STEP DEPLOYMENT

### 1. Verify Environment (1 min)
```bash
cd /home/luiz/GCA_Produção
make check
```

Expected: All checks pass ✅

### 2. Apply Database (2 min)
```bash
make migrate
```

Expected: Migrations applied successfully ✅

### 3. Start Server (1 min)
```bash
make start
```

Expected:
```
✅ Database connection OK
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## 🧪 TEST IT (1 min)

In another terminal:
```bash
# Health check
curl http://localhost:8000/health

# Submit questionnaire
curl -X POST http://localhost:8000/api/v1/questionnaires \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "550e8400-e29b-41d4-a716-446655440000",
    "gp_email": "pielak.ctba@gmail.com",
    "responses": {
      "frontend_stack": ["React"],
      "backend_stack": ["FastAPI"],
      "database_stack": ["PostgreSQL"],
      "ai_automation": ["Anthropic"],
      "security_controls": ["Autenticação", "Autorização / RBAC"],
      "deliverables": ["Aplicação web"],
      "execution_mode": ["Cloud"],
      "architecture_target": ["Microserviços"],
      "infra_support": ["Kafka"],
      "test_types": ["Unitários"]
    }
  }'

# Run full test suite
make test
```

---

## 📖 USEFUL COMMANDS

```bash
# Check everything
make check

# Apply database migrations
make migrate

# Start server
make start

# Stop server
make stop

# View server logs (live)
make logs

# Run tests
make test

# Check server status
make status

# Clean temp files
make clean
```

---

## 🔧 ADVANCED

### Custom Port
```bash
PORT=9000 make start
```

### More Workers (Higher Load)
```bash
WORKERS=8 make start
```

### View API Documentation
```
http://localhost:8000/api/v1/docs
```

---

## ✅ WHAT YOU HAVE

- ✅ Complete production code
- ✅ Database migrations ready
- ✅ Email service configured (Gmail)
- ✅ n8n integration ready (optional Qwen AI)
- ✅ Analysis engine (15+ rules, 8+ gaps)
- ✅ Automatic email notifications
- ✅ Database persistence (PostgreSQL)
- ✅ Complete documentation
- ✅ Management scripts
- ✅ Production best practices

---

## 🎯 NEXT STEPS

1. **Now**: `make check` → `make migrate` → `make start`
2. **Test**: `make test` or use curl commands
3. **Monitor**: `make logs` to watch real-time logs
4. **Configure** (optional): Set N8N_WEBHOOK_URL in .env for Qwen AI
5. **Scale**: Add more workers with `WORKERS=N make start`

---

## 📊 KEY ENDPOINTS

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check |
| `/api/v1/docs` | GET | Interactive API docs |
| `/api/v1/questionnaires` | POST | Submit questionnaire |
| `/api/v1/questionnaires/{id}/status` | GET | Get questionnaire status |
| `/api/v1/webhooks/questionnaire` | POST | n8n webhook (analysis) |
| `/api/v1/webhooks/questionnaire-result` | POST | n8n callback (results) |

---

## 🆘 TROUBLESHOOTING

```bash
# Port already in use?
make stop
make start

# Database issues?
make check        # Verify connection
make migrate      # Re-apply migrations

# Dependencies missing?
pip install -r requirements.txt

# Check logs
make logs
```

---

## 📚 DOCUMENTATION

- **Full Guide**: `PRODUCTION_README.md`
- **Setup Summary**: `PRODUCTION_SETUP_SUMMARY.md`
- **Architecture**: `N8N_HYBRID_IMPLEMENTATION.md`
- **Deployment**: `PHASE5_DEPLOYMENT_CHECKLIST.md`
- **Project Status**: `PHASES_COMPLETE_SUMMARY.md`

---

🎉 **Ready to deploy! Execute `make check` to get started.**
