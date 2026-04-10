# GCA Production Environment

**Location**: `/home/luiz/GCA_Produção/`  
**Status**: ✅ Ready for Deployment  
**Date**: 2026-04-06  
**Version**: 0.1.0

---

## 📋 QUICK START

### 1️⃣ Apply Database Migration (First Time Only)

```bash
cd /home/luiz/GCA_Produção
./apply_migration.sh
```

**What it does**:
- Creates `questionnaires` table (16 columns)
- Creates 5 performance indexes
- Sets up RBAC (Role-Based Access Control) tables
- Verifies schema integrity

**Expected Output**:
```
✅ Database connection OK
✅ Migration 001 applied
✅ Migration 002 applied
```

---

### 2️⃣ Start Production Server

```bash
cd /home/luiz/GCA_Produção
./start_production.sh
```

**Or with custom configuration**:
```bash
PORT=9000 WORKERS=8 ./start_production.sh
```

**Expected Output**:
```
✅ Environment file: .env
✅ Python version: 3.11.x
✅ Database connection OK
✅ Starting GCA Production Server...
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

### 3️⃣ Verify Server is Running

```bash
# Health Check
curl http://localhost:8000/health

# API Documentation
curl http://localhost:8000/api/v1/docs

# Submit a questionnaire
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
```

---

## 📁 DIRECTORY STRUCTURE

```
/home/luiz/GCA_Produção/
├── .env                              # Production environment variables
├── requirements.txt                  # Python dependencies
├── start_production.sh                # Production startup script
├── apply_migration.sh                 # Database migration script
├── PRODUCTION_README.md               # This file
│
├── app/                               # Application code
│   ├── main.py                       # FastAPI app entry point
│   ├── core/                         # Configuration
│   ├── db/                           # Database connections
│   ├── models/                       # SQLAlchemy models
│   ├── routers/                      # API endpoints
│   ├── schemas/                      # Pydantic schemas
│   ├── services/                     # Business logic
│   │   ├── questionnaire_service.py  # Questionnaire handling
│   │   ├── email_service.py          # Email notifications
│   │   ├── n8n_service.py            # n8n integration
│   │   └── ...
│   └── ...
│
├── migrations/                        # Database migrations
│   ├── 001_add_password_reset_tables.sql
│   └── 002_add_questionnaires_table.sql
│
└── Documentation/
    ├── N8N_HYBRID_IMPLEMENTATION.md
    ├── PHASE5_DEPLOYMENT_CHECKLIST.md
    └── PHASES_COMPLETE_SUMMARY.md
```

---

## ⚙️ CONFIGURATION

### Environment Variables (in `.env`)

**Application Settings**:
```
APP_ENV=production          # Set to production (not development)
DEBUG=False                 # Disable debug mode in production
APP_VERSION=0.1.0          # Current version
PORT=8000                  # Server port
```

**Database**:
```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=gca
POSTGRES_USER=gca
POSTGRES_PASSWORD=gca_secret  # Change in production!
DATABASE_URL=postgresql+asyncpg://gca:gca_secret@localhost:5432/gca
```

**Email Service**:
```
SMTP_ENABLED=True
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=pielak.ctba@gmail.com
SMTP_PASSWORD=bvak gqef wdyt mbyi  # Gmail App Password
SMTP_FROM_NAME=GCA - Gerenciador Central de Arquiteturas
```

**n8n Integration** (Optional):
```
N8N_WEBHOOK_URL=https://your-n8n.com/webhook/gca-questionnaire
N8N_API_URL=https://your-n8n.com/api
N8N_API_KEY=your-api-key
```

### Recommended Production Settings

```bash
# In .env
DEBUG=False
APP_ENV=production
LOG_LEVEL=INFO

# For higher concurrency
PORT=8000
# Run with: WORKERS=8 ./start_production.sh
```

---

## 📊 MONITORING

### Check Server Status

```bash
# Health check endpoint
curl http://localhost:8000/health

# Check logs in real-time
tail -f /var/log/gca/app.log

# Monitor database
psql -h localhost -U gca -d gca -c \
  "SELECT COUNT(*) as questionnaires FROM questionnaires;"
```

### Key Metrics

- **Questionnaire Submissions**: Track via `questionnaires` table
- **Email Delivery**: Check SMTP logs
- **Response Time**: Should be <100ms for questionnaire submission
- **n8n Integration**: Check webhook dispatch logs

---

## 🧪 TESTING THE DEPLOYMENT

### Test 1: Health Check
```bash
curl -i http://localhost:8000/health
# Expected: 200 OK
```

### Test 2: Submit Questionnaire (Approval)
```bash
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

# Expected:
# - 200 OK
# - questionnaire_id in response
# - Email arrives in ~30 seconds
```

### Test 3: Submit Questionnaire (Revision)
```bash
curl -X POST http://localhost:8000/api/v1/questionnaires \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "550e8400-e29b-41d4-a716-446655440001",
    "gp_email": "pielak.ctba@gmail.com",
    "responses": {
      "frontend_stack": ["React", "Flutter"],
      "backend_stack": ["FastAPI"],
      "database_stack": [],
      "ai_automation": [],
      "security_controls": ["Autenticação"],
      "deliverables": ["Aplicação web"],
      "execution_mode": ["Cloud"],
      "architecture_target": ["Monólito"],
      "infra_support": []
    }
  }'

# Expected:
# - 200 OK
# - Score <85%
# - Email: "⚠️ Questão Precisa de Revisão"
```

### Test 4: Verify Database
```bash
psql -h localhost -U gca -d gca << 'EOF'
SELECT 
  id, 
  status, 
  adherence_score, 
  approved,
  submitted_at 
FROM questionnaires 
ORDER BY submitted_at DESC 
LIMIT 5;
EOF

# Expected: Latest questionnaires with their scores and statuses
```

---

## 🔐 SECURITY BEST PRACTICES

### Recommended for Production

1. **Passwords & Secrets**
   - ✅ Change POSTGRES_PASSWORD
   - ✅ Use strong SMTP_PASSWORD (Gmail App Password)
   - ✅ Generate new SECRET_KEY for production
   - ✅ Store .env securely (not in git)

2. **CORS Configuration**
   ```
   CORS_ORIGINS=["https://yourdomain.com"]  # Whitelist your domain only
   ```

3. **Database Backups**
   ```bash
   # Daily backup
   pg_dump gca > /backup/gca_$(date +%Y%m%d).sql
   ```

4. **Logging**
   - ✅ LOG_LEVEL=INFO (not DEBUG)
   - ✅ Rotate logs daily
   - ✅ Monitor for errors

5. **SSL/HTTPS**
   - ✅ Use reverse proxy (nginx) with SSL
   - ✅ Redirect HTTP to HTTPS
   - ✅ Update FRONTEND_URL to HTTPS

---

## 🚀 DEPLOYMENT COMMANDS

### Development (with auto-reload)
```bash
cd /home/luiz/GCA/backend
python3 -m uvicorn app.main:app --reload
```

### Production (this directory)
```bash
cd /home/luiz/GCA_Produção
./start_production.sh
```

### With systemd (Linux)
```bash
# Create service file
sudo tee /etc/systemd/system/gca.service > /dev/null << 'EOF'
[Unit]
Description=GCA Production Server
After=network.target

[Service]
Type=simple
User=luiz
WorkingDirectory=/home/luiz/GCA_Produção
ExecStart=/home/luiz/GCA_Produção/start_production.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable gca
sudo systemctl start gca

# Check status
sudo systemctl status gca
```

---

## 🐛 TROUBLESHOOTING

### Server won't start
```bash
# Check if port is in use
lsof -i :8000

# Kill existing process
pkill -f "uvicorn app.main"

# Try again
./start_production.sh
```

### Database connection error
```bash
# Verify connection
psql -h localhost -U gca -d gca -c "SELECT 1"

# Check .env
grep DATABASE_URL .env

# Reset connection pool
./start_production.sh
```

### Email not being sent
```bash
# Test SMTP manually
python3 << 'EOF'
import smtplib
server = smtplib.SMTP("smtp.gmail.com", 587)
server.starttls()
server.login("pielak.ctba@gmail.com", "bvak gqef wdyt mbyi")
print("✅ SMTP OK")
EOF

# Check SMTP settings in .env
grep SMTP .env
```

### Migration failed
```bash
# Re-run migration
./apply_migration.sh

# Check migration history
psql -h localhost -U gca -d gca -c \
  "SELECT * FROM information_schema.tables WHERE table_name='questionnaires';"
```

---

## 📈 PERFORMANCE TUNING

### For Higher Load

```bash
# Increase workers
WORKERS=8 ./start_production.sh

# Increase database pool
# In .env:
DATABASE_POOL_SIZE=30
DATABASE_MAX_OVERFLOW=20

# Use reverse proxy (nginx)
# Setup load balancing across multiple workers
```

### Database Optimization

```sql
-- Analyze query performance
VACUUM ANALYZE questionnaires;

-- Check index usage
SELECT * FROM pg_stat_user_indexes;

-- Monitor connections
SELECT count(*) FROM pg_stat_activity;
```

---

## 📖 DOCUMENTATION

- **Architecture**: See `N8N_HYBRID_IMPLEMENTATION.md`
- **Deployment**: See `PHASE5_DEPLOYMENT_CHECKLIST.md`
- **Project Status**: See `PHASES_COMPLETE_SUMMARY.md`
- **API Docs**: http://localhost:8000/api/v1/docs (running server)

---

## ✅ PRODUCTION CHECKLIST

Before going live:

- [ ] Database migration applied
- [ ] Server starts without errors
- [ ] All 4 test cases pass
- [ ] Emails are being sent
- [ ] Database is persisting data
- [ ] Logs are clean (no errors)
- [ ] .env is secure (not in git)
- [ ] Backups are configured
- [ ] Monitoring is in place
- [ ] SSL/HTTPS configured

---

## 🎯 NEXT STEPS

1. **Apply Migration**
   ```bash
   cd /home/luiz/GCA_Produção
   ./apply_migration.sh
   ```

2. **Start Server**
   ```bash
   ./start_production.sh
   ```

3. **Run Tests** (follow `PHASE5_DEPLOYMENT_CHECKLIST.md`)

4. **Monitor Logs**
   ```bash
   tail -f logs/app.log
   ```

5. **Configure n8n** (optional, when ready)
   - Set N8N_WEBHOOK_URL in .env
   - Create n8n workflow
   - Test Qwen AI integration

---

## 📞 SUPPORT

- **API Docs**: http://localhost:8000/api/v1/docs
- **Health Check**: http://localhost:8000/health
- **Git Repo**: https://github.com/Pielak/GCA
- **Issues**: Check PHASE5_DEPLOYMENT_CHECKLIST.md troubleshooting section

---

**Status**: 🟢 **READY FOR PRODUCTION**  
**Location**: `/home/luiz/GCA_Produção/`  
**Maintainer**: Claude Code (Session: Phases 1-5)

🚀 **Let's go live!**
