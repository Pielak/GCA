# GCA v0.1 — Scripts de Teste e Monitoramento

Conjunto de ferramentas Python para testar e monitorar o GCA v0.1 durante testes com usuário.

---

## 📋 Scripts Disponíveis

### 1. `smoke_test_gca_v01.py` — Teste Rápido do Pipeline

Executa todas as 4 fases do GCA v0.1 sem fazer requests reais à API:
1. M01Service gera questionnaire (35-50 questões)
2. User simula respostas
3. 5 Personas validam
4. Verifica integridade do output

**Uso:**
```bash
python smoke_test_gca_v01.py
```

**Output esperado:**
```
[1/4] M01Service gerando questionnaire...
  ✅ 35 questões em 0.00s
  ✅ 7 conceitos extraídos
  ✅ 3 gaps identificados
[2/4] Simulando respostas do user...
  ✅ 35 respostas geradas
[3/4] Personas validando...
  ✅ 5/5 personas aprovaram
[4/4] Validando integridade...
  ✅ SMOKE TEST PASSOU
```

**Tempo**: ~2 segundos

---

### 2. `output_validator_gca_v01.py` — Validador de Format

Verifica que os outputs dos endpoints estão no formato esperado:
- M01 retorna 30-50 questões com estrutura correta
- Validator retorna 5 personas com decisões válidas

**Uso:**
```bash
python output_validator_gca_v01.py --all              # Testar tudo
python output_validator_gca_v01.py --test-m01        # Testar apenas M01
python output_validator_gca_v01.py --test-validator  # Testar apenas Validator
```

**Validações:**
- ✅ M01: count em [30-50], conceitos, gaps, iteration_id
- ✅ Validator: 5 personas, status válidos, next_action correto

---

### 3. `generate_test_documents.py` — Gerador de Docs de Teste

Cria 3 variações de documentos AJA para testar diferentes cenários:

**Documentos gerados:**
1. **Simples** (~280 chars) — teste rápido, faltam requisitos
2. **Médio** (~2000 chars) — caso normal, requisitos claros
3. **Complexo** (~9300 chars) — edge case, muito detalhe

**Uso:**
```bash
python generate_test_documents.py --output-dir ./test_docs
```

**Output:**
```
✅ simple  → test_docs/AJA_v3.0_simple.txt (280 chars)
✅ medium  → test_docs/AJA_v3.0_medium.txt (2086 chars)
✅ complex → test_docs/AJA_v3.0_complex.txt (9336 chars)
```

**Próximos passos:**
1. Use esses para testar o endpoint M01
2. Compare outputs: quantas questões gera para cada um?
3. Valide com `output_validator_gca_v01.py`

---

### 4. `monitoring_dashboard.py` — Dashboard de Monitoramento

Monitora logs durante testes e fornece estatísticas em tempo real:
- Tempo de M01Service (geração)
- Tempo de PersonasConsolidator (validação)
- Erros encontrados
- Performance metrics

**Uso:**
```bash
# Modo normal (ler arquivo)
python monitoring_dashboard.py --log-file /var/log/gca/app.log

# Modo follow (tail -f style)
python monitoring_dashboard.py --follow
```

**Output exemplo:**
```
📊 M01SERVICE
  Execuções: 5
  Tempo médio: 0.42s
  Mínimo: 0.15s
  Máximo: 0.89s

🤖 PERSONAS
  Execuções: 5
  Tempo médio: 0.18s

❌ ERROS: 0
```

---

### 5. `db_backup_manager.py` — Backup do Banco de Dados

Cria snapshots do banco antes/depois de testes e permite rollback:

**Uso:**
```bash
# Criar snapshot
python db_backup_manager.py --create-snapshot "pre-test"

# Listar snapshots
python db_backup_manager.py --list-snapshots

# Restaurar snapshot
python db_backup_manager.py --restore-snapshot "pre-test"

# Limpar snapshots antigos (manter apenas 5 últimos)
python db_backup_manager.py --cleanup --keep-count 5
```

**Fluxo típico:**
```bash
# Antes de testar
python db_backup_manager.py --create-snapshot "pre-test-20260426"

# [fazer testes...]

# Se algo deu ruim
python db_backup_manager.py --restore-snapshot "pre-test-20260426"

# Ou continuar e fazer post-snapshot
python db_backup_manager.py --create-snapshot "post-test-20260426"
```

**Backups armazenados em:** `/home/luiz/GCA/backups/`

---

## 🚀 Fluxo de Teste Recomendado

### Pré-Teste

```bash
# 1. Verificar que tudo funciona
python smoke_test_gca_v01.py

# 2. Validar outputs esperados
python output_validator_gca_v01.py --all

# 3. Criar backup antes de testar
python db_backup_manager.py --create-snapshot "pre-test"
```

### Durante Teste

```bash
# Em outro terminal: monitorar em tempo real
python monitoring_dashboard.py --follow

# Você testa em localhost:3000/localhost:8000
# [fazer upload de AJA v3.0, responder questionnaire, etc]
```

### Pós-Teste

```bash
# Listar snapshots
python db_backup_manager.py --list-snapshots

# Se tudo OK: fazer post-snapshot
python db_backup_manager.py --create-snapshot "post-test"

# Se algo deu ruim: rollback
python db_backup_manager.py --restore-snapshot "pre-test"

# Limpar snapshots antigos
python db_backup_manager.py --cleanup
```

---

## 📊 Combinando Scripts

**Teste completo em 1 comando:**

```bash
#!/bin/bash

echo "🧪 TESTE COMPLETO GCA v0.1"

echo "1️⃣  Smoke test..."
python smoke_test_gca_v01.py || exit 1

echo "2️⃣  Validar outputs..."
python output_validator_gca_v01.py --all || exit 1

echo "3️⃣  Gerar documentos de teste..."
python generate_test_documents.py --output-dir ./test_docs

echo "4️⃣  Backup pré-teste..."
python db_backup_manager.py --create-snapshot "pre-test"

echo "✅ Pré-teste completo!"
echo "   Próximo: Upload de AJA v3.0 real"
echo "   Monitor: python monitoring_dashboard.py --follow"
```

---

## 🔧 Troubleshooting

### Erro: "ModuleNotFoundError: No module named 'app'"

**Solução:** Rode os scripts com Python venv:
```bash
/home/luiz/GCA/venv/bin/python scripts/smoke_test_gca_v01.py
```

### Erro: "Database connection refused"

**Solução:** Confirme que PostgreSQL está rodando:
```bash
docker ps | grep postgres  # Se usar Docker
# ou
psql gca -c "SELECT 1"     # Se PostgreSQL local
```

### Logs não sendo monitorados

**Solução:** Confirme o caminho do arquivo de log:
```bash
find /var/log -name "*gca*" -o -name "*app*"
# Ajuste --log-file se necessário
```

---

## 📝 Próximas Iterações

- [ ] Script de teste de carga (simular 100 users simultâneos)
- [ ] Exportador de métricas (Prometheus format)
- [ ] Integração com Slack (notificações de erro)
- [ ] Report HTML (sumário pós-teste)

---

## 📚 Referência Rápida

| Script | Tempo | Função |
|--------|-------|--------|
| `smoke_test_gca_v01.py` | 2s | Valida pipeline completo |
| `output_validator_gca_v01.py` | 1s | Verifica formato de output |
| `generate_test_documents.py` | <1s | Cria 3 docs de teste |
| `monitoring_dashboard.py` | ∞ | Monitora em tempo real |
| `db_backup_manager.py` | 10-60s | Backup/restore do DB |

---

**Desenvolvido para GCA v0.1 (2026-04-26)**
