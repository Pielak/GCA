# 🚀 Quick Start: Deploy em Novo Servidor

## Pré-requisitos

```bash
# Servidor com:
- Ubuntu 20.04+ LTS
- Docker + Docker Compose
- Git
- 2GB RAM mínimo
- 20GB disco mínimo
```

## Deploy em 5 Minutos

### 1. Conectar ao Servidor

```bash
ssh user@seu-servidor.com
```

### 2. Instalar Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

### 3. Clonar Repositório

```bash
cd /opt
git clone https://github.com/Pielak/GCA_Project.git
cd GCA_Project
```

### 4. Configurar Variáveis

```bash
cp .env.example .env
# Editar valores de produção
nano .env

# Valores mínimos necessários:
SECRET_KEY=openssl rand -hex 32
DATABASE_PASSWORD=senhaforte
```

### 5. Iniciar Serviços

```bash
docker-compose -f docker-compose.production.yml up -d

# Aguardar 30s
sleep 30

# Verificar status
docker-compose ps
```

### 6. Acessar Aplicação

```
Frontend: http://seu-servidor:5173
Backend:  http://seu-servidor:8000
API Docs: http://seu-servidor:8000/api/v1/docs
```

---

## Com SSL/TLS (Let's Encrypt)

### Instalar Certbot

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot certonly --standalone -d seu-dominio.com
```

### Configurar Nginx Reverse Proxy

Ver `docs/DEPLOYMENT.md` para configuração completa.

---

## Troubleshooting

### Ver Logs

```bash
docker-compose logs -f backend
docker-compose logs -f frontend
```

### Reiniciar Serviços

```bash
docker-compose restart
```

### Parar Tudo

```bash
docker-compose down -v
```

---

## Monitoramento

```bash
# Health check backend
curl http://localhost:8000/health

# Ver métricas
docker stats

# Logs persistentes
docker-compose logs --tail=100 backend
```

---

## Proximos Passos

1. Configurar domínio + DNS
2. Setup SSL com Let's Encrypt
3. Nginx reverso proxy
4. Backups automáticos
5. Monitoramento (Prometheus + Grafana)

Para instruções detalhadas, consulte **docs/DEPLOYMENT.md**

