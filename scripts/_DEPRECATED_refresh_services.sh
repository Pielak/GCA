#!/bin/bash
# GCA — Refresh de servicos a cada 2 horas
# Reinicia containers + verifica cloudflared
# Log em /home/luiz/GCA/logs/refresh.log

LOG="/home/luiz/GCA/logs/refresh.log"
mkdir -p /home/luiz/GCA/logs

echo "========================================" >> "$LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Refresh iniciado" >> "$LOG"

# Restart containers
cd /home/luiz/GCA
docker compose restart >> "$LOG" 2>&1

# Verificar cloudflared
if ! systemctl is-active --quiet cloudflared; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] cloudflared estava parado. Reiniciando..." >> "$LOG"
    sudo systemctl restart cloudflared >> "$LOG" 2>&1
fi

# Health check (aguardar frontend buildar)
sleep 30
BACKEND=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs)
FRONTEND=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5173)
N8N=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5678)
EXTERNAL=$(curl -s -o /dev/null -w "%{http_code}" https://gca.code-auditor.com.br)

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Health: backend=$BACKEND frontend=$FRONTEND n8n=$N8N external=$EXTERNAL" >> "$LOG"

# Se algum servico falhou, tentar docker compose up
if [ "$BACKEND" != "200" ] || [ "$FRONTEND" != "200" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ALERTA: servico fora. Executando docker compose up -d" >> "$LOG"
    docker compose up -d >> "$LOG" 2>&1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Refresh concluido" >> "$LOG"
