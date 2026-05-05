# Operação: Restart Seguro (Sem Retrabalho)

## Problema

Reiniciar backend/DB durante processamento de documentos causa:
- ❌ **Retrabalho**: documento volta à fila e é reprocessado
- ❌ **Reespera**: usuário aguarda novamente
- ❌ **Erro silencioso**: doc pode ser marcado em erro incorretamente
- ❌ **Inconsistência**: estado desincronizado entre DB e processo

## Solução

**Sempre use o script `safe_restart.sh`** antes de qualquer restart manual. Ele verifica se existem documentos em processamento e aguarda automaticamente.

---

## Uso

### Opção 1: Aguardar automaticamente (RECOMENDADO)

```bash
# Aguarda até 120 segundos, depois reinicia
./backend/scripts/safe_restart.sh backend --wait 120

# Aguarda até 300 segundos (5 min) — útil para pipeline longo
./backend/scripts/safe_restart.sh backend --wait 300
```

**Fluxo:**
1. ✓ Detecta docs em processamento
2. ⏳ Aguarda até X segundos
3. ✓ Se todos terminarem antes do timeout → reinicia
4. ❌ Se timeout expirar → aviso, aborta restart

### Opção 2: Força restart (ÚLTIMO RECURSO)

```bash
# Força restart MESMO COM docs em processamento
# ⚠ Isso causa retrabalho!
./backend/scripts/safe_restart.sh backend --force
```

**Use apenas se:**
- Backend está travado/irresponsivo
- Mesmo assim, aguarde ~30s pra dar chance de recuperação natural

### Opção 3: Reiniciar database (sempre seguro)

```bash
# DB pode ser reiniciado a qualquer hora
./backend/scripts/safe_restart.sh db
```

### Opção 4: Restart completo (backend + DB)

```bash
# Aguarda backend, depois reinicia tudo
./backend/scripts/safe_restart.sh all --wait 180
```

---

## Exemplo Real

```bash
$ ./backend/scripts/safe_restart.sh backend --wait 120

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 Safe Restart Script — backend
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Pré-restart check: documentos em processamento?

❌ NÃO é seguro reiniciar!
   📊 Status atual:
      • 2 documento(s) em processamento (status='processing')
      • 1 documento(s) na fila (status='pending')

⏳ Aguardando até 120s para documentos finalizarem...
   Ainda 2 em processamento... 118s restante(s)
   Ainda 1 em processamento... 116s restante(s)
✓ Documentos finalizados! Seguro reiniciar agora.

🐋 Reiniciando container backend...
[container restart...]

⏳ Aguardando containers ficarem prontos...
uvicorn app.main:app running

✅ Restart concluído!
```

---

## Check Manual (sem restart)

Se só quer verificar status sem reiniciar:

```bash
python3 backend/scripts/check_before_restart.py

# Ou com espera:
python3 backend/scripts/check_before_restart.py --wait 60
```

**Exit codes:**
- `0` = seguro (nenhum doc em processamento)
- `1` = há docs em processamento
- `2` = erro de conexão

---

## Integração em Workflows

### Cron job (monitorado)

```bash
# Restart diário às 2am, com aguarde
0 2 * * * /home/luiz/GCA/backend/scripts/safe_restart.sh all --wait 300
```

### CI/CD pre-deploy

```yaml
# .github/workflows/deploy.yml
- name: Pré-restart check
  run: |
    cd /home/luiz/GCA
    python3 backend/scripts/check_before_restart.py --wait 300
    if [ $? -ne 0 ]; then
      echo "❌ Docs ainda em processamento. Deploy abortado."
      exit 1
    fi

- name: Restart services
  run: ./backend/scripts/safe_restart.sh all
```

---

## O Que Verificar Antes de Reiniciar Manualmente

Checklist se você quiser fazer restart RÁPIDO (sem aguardar):

```bash
# Terminal 1: Monitorar docs em processamento
watch -n 2 'psql -U gca -d gca -c "SELECT arguider_status, COUNT(*) FROM ingested_documents WHERE arguider_status IN ('"'"'processing'"'"', '"'"'pending'"'"') GROUP BY arguider_status;"'

# Terminal 2: Monitorar logs do pipeline
docker logs -f gca-backend 2>&1 | grep -E "pipeline|ingest|completed|error"

# Quando ambos ficarem silenciosos → seguro fazer restart
```

---

## Troubleshooting

### "NÃO é seguro reiniciar" mas logs mostram tudo pronto

Pode haver race condition:
- Doc foi marcado `processing` mas não começou de fato
- n8n workflow está lento
- LLM está demorando

**Solução:** aguarde mais tempo ou force:
```bash
./backend/scripts/safe_restart.sh backend --wait 300
./backend/scripts/safe_restart.sh backend --force  # último recurso
```

### Timeout expirou durante espera

Doc está realmente processando e levou > timeout:

```bash
# Ver qual doc está travado
psql -U gca -d gca -c "
SELECT substring(id::text, 1, 8) as doc_id,
       substring(original_filename, 1, 40) as fn,
       arguider_status, arguider_stage, updated_at
FROM ingested_documents
WHERE arguider_status='processing'
ORDER BY updated_at;"

# Se está travado por > 30min → force restart
./backend/scripts/safe_restart.sh backend --force
```

---

## Regra de Ouro

```
❌ NUNCA: docker compose restart backend (sem check)
✅ SEMPRE: ./backend/scripts/safe_restart.sh backend --wait 120
```

---

**Criado em:** 2026-05-05  
**Escopo:** Operação segura de restart (MVP 35 pós-simplificação)
