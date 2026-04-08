# GCA Deployment Guide

**Versão**: 0.1.0 | **Data**: 2026-04-05

---

## 🚀 Deployment Options

### Option 1: Docker Compose (Local)
✅ Recomendado para desenvolvimento e teste

### Option 2: Kubernetes (Produção)
⏳ Para escalabilidade horizontal

### Option 3: Cloud (AWS/GCP/Azure)
⏳ Managed services (RDS, App Engine, etc)

---

## 📦 Docker Compose (Local)

### Pré-requisitos

```bash
# Docker & Docker Compose
docker --version
docker-compose --version

# Espaço em disco
df -h | grep "/$"  # Pelo menos 10GB livre

# Portas
lsof -i :8000 && echo "Porta 8000 em uso" || echo "OK"
lsof -i :5432 && echo "Porta 5432 em uso" || echo "OK"
```

### Deploy

```bash
# 1. Clonar repositório
git clone <repo-url> /opt/gca
cd /opt/gca

# 2. Copiar env
cp .env.example .env
# Editar .env com suas credenciais

# 3. Iniciar
docker-compose up -d

# 4. Verificar
docker-compose ps
docker-compose logs -f

# 5. Health check
curl http://localhost:8000/health
```

---

## 🔐 Variáveis de Ambiente

Criar `.env` na raiz do projeto:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@gca-postgres:5432/gca

# JWT
SECRET_KEY=sua-chave-secreta-aleatoria-minimo-32-chars

# SMTP
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=seu-email@gmail.com
SMTP_PASSWORD=app-password-16-chars

# IA Provider
IA_PROVIDER=anthropic
IA_API_KEY=sua-api-key

# Redis
REDIS_URL=redis://gca-redis:6379

# Frontend
VITE_API_BASE_URL=http://localhost:8000/api/v1

# Ambiente
ENVIRONMENT=development  # production, staging, development
DEBUG=false
```

---

## 🔧 Configuração de Produção

### 1. SSL/HTTPS

#### Option A: Cloudflare Tunnel (Recomendado)

```bash
# Instalar cloudflared
curl -L --output cloudflared.tgz https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.tgz
tar -xzf cloudflared.tgz

# Autenticar
./cloudflared login

# Criar túnel
./cloudflared tunnel create gca

# Rotar tráfego
./cloudflared tunnel route dns gca gca.seu-dominio.com
```

#### Option B: Let's Encrypt (nginx reverse proxy)

```nginx
server {
    listen 443 ssl http2;
    server_name gca.seu-dominio.com;

    ssl_certificate /etc/letsencrypt/live/gca.seu-dominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/gca.seu-dominio.com/privkey.pem;

    location / {
        proxy_pass http://localhost:5173;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
    }
}
```

### 2. Database Backup

```bash
# Daily backup (cron job)
0 2 * * * /home/gca/backup.sh

# backup.sh
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
docker-compose exec -T gca-postgres pg_dump -U postgres gca > /backups/gca_$DATE.sql
# Upload para S3/GCS/Azure Blob
```

### 3. Monitoramento

```bash
# Health check endpoint
curl http://localhost:8000/health

# Logs aggregation
docker-compose logs --follow
# OU: ELK Stack, Datadog, NewRelic

# Metrics
# Prometheus endpoint: http://localhost:8000/metrics (future)
```

### 4. Performance

```yaml
# docker-compose.yml - otimização
services:
  gca-backend:
    environment:
      - WORKERS=4
      - MAX_CONNECTIONS=50
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M
```

---

## 🆙 Upgrade Procedure

### 1. Backup

```bash
# Backup database
docker-compose exec gca-postgres pg_dump -U postgres gca > backup_pre_upgrade.sql

# Backup volumes
docker-compose exec gca-backend tar -czf /tmp/data_backup.tar.gz /data/
```

### 2. Update Code

```bash
git pull origin master
```

### 3. Rebuild & Restart

```bash
docker-compose build
docker-compose down
docker-compose up -d

# Verify
docker-compose logs -f gca-backend | grep "Application startup complete"
```

### 4. Test

```bash
# Health check
curl http://localhost:8000/health

# Login test
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"..."}' \
  http://localhost:8000/api/v1/auth/login
```

---

## 🔧 Troubleshooting

### Container won't start

```bash
# Ver logs
docker-compose logs gca-backend

# Troubleshooting comum:
# - Port já em uso
# - Database não iniciada
# - Env vars faltando
```

### Database connection timeout

```bash
# Verificar se postgres está pronto
docker-compose exec gca-postgres pg_isready -U postgres

# Se não responder, restart
docker-compose restart gca-postgres
```

### Out of disk space

```bash
# Limpar imagens antigas
docker image prune -a --filter "until=720h"

# Limpar volumes não usados
docker volume prune

# Ver tamanho de containers
docker ps -s
```

---

## 📊 Monitoring Checklist

- [ ] Health endpoint respondendo
- [ ] Database backups diários
- [ ] SSL certificate válido
- [ ] Logs centralizados
- [ ] Alertas configurados
- [ ] Rate limiting ativo
- [ ] CORS configurado
- [ ] Secrets não em git

---

## 🔐 Security Checklist

- [ ] JWT secret aleatório (32+ chars)
- [ ] HTTPS/SSL ativo
- [ ] Database password forte
- [ ] .env não versionado
- [ ] Rate limiting ON
- [ ] CORS restrictivo
- [ ] SQL injection proteção (SQLAlchemy ORM)
- [ ] XSS proteção (React sanitize)

---

**Versão**: 0.1.0 Beta | **Data**: 2026-04-05
