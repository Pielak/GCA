# Production Deployment Checklist

## Pre-Deployment

- [ ] Code review concluído
- [ ] Tests passando (12/28 minimum)
- [ ] Database backup feito
- [ ] .env.production configurado com credenciais reais
- [ ] SSL certificate obtido
- [ ] Cloudflare DNS apontando para servidor

## Deployment Steps

### 1. Build Docker Images

```bash
cd /home/luiz/GCA

# Backend
docker build -t gca-backend:latest ./backend

# Frontend
docker build -t gca-frontend:latest ./frontend
```

### 2. Deploy

```bash
# Parar containers antigos
docker-compose -f docker-compose.production.yml down

# Iniciar novos
docker-compose -f docker-compose.production.yml up -d

# Verificar
docker-compose -f docker-compose.production.yml ps
```

### 3. Health Checks

```bash
# Backend
curl https://gca.seu-dominio.com/health

# Login test
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"..."}' \
  https://gca.seu-dominio.com/api/v1/auth/login
```

### 4. Setup Monitoring

```bash
# Daily backup (cron)
0 2 * * * /home/luiz/GCA/scripts/backup.sh

# Hourly health check
0 * * * * /home/luiz/GCA/scripts/health-check.sh https://gca.seu-dominio.com
```

## Post-Deployment

- [ ] All pages accessible
- [ ] Login funciona
- [ ] Criar primeiro projeto
- [ ] Enviar email de teste
- [ ] Testar SMTP
- [ ] Monitorar logs por 1 hora

## Rollback Plan

```bash
# If something breaks
docker-compose -f docker-compose.production.yml down
docker-compose -f docker-compose.yml up -d  # Use staging version

# Or restore from backup
docker-compose exec gca-postgres psql -U postgres gca < backup_pre_deploy.sql
```

## Maintenance

### Daily
- Monitor health check logs
- Check error logs for issues

### Weekly
- Review performance metrics
- Test backup restoration

### Monthly
- Database cleanup
- Log rotation
- Security updates
