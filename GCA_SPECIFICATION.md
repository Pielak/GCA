# GCA_SPECIFICATION.md — Produto + Decisões

**Versão:** 2.0 | **Data:** 2026-05-05 | **Status:** Canônico

> Requisitos técnicos: `GCA_TECHNICAL_REFERENCE.md`  
> Workflow operacional: `GCA_CLAUDE.md`  
> MVPs + Roadmap: `GCA_MVP_ROADMAP.md`

---

## §1. Definição do Produto

**GCA (Gestão de Codificação Assistida)** é uma meta-plataforma para construir sistemas com:

- Ingestão estruturada de requisitos (Questionário + Documentos)
- Validação assistida por 12 personas LLM em paralelo (n8n)
- OCG (Objeto de Contexto Global) cumulativo como fonte única de verdade
- CodeGen liberado **somente quando OCG ≥ 95% em todos 7 pilares**
- Supervisão humana obrigatória em toda liberação (Gatekeeper 5-porteiros)

**GCA NÃO é ponto final**: gera, não decide sozinho. Toda saída crítica requer aprovação + auditoria.

---

## §2. Modelo de Deployment

- ✅ **Instalável por cliente** (on-premises). Uma instância = um cliente.
- ❌ NÃO é SaaS multi-tenant compartilhado.
- ✅ Isolamento **por projeto** dentro da instância.
- ✅ `gca.code-auditor.com.br` é **dogfood**, não prova de SaaS.
- ✅ Toda query de dado de projeto inclui `project_id` no WHERE.

---

## §3. RBAC Canônico (Conjunto A — 5 papéis humanos)

| Papel | Escopo | Autoridades |
|-------|--------|-------------|
| **Admin** | Instância | Configura provedores, aprova projetos, opera globalmente |
| **GP** | Projeto | Soberano do projeto; opera CodeGen, pipeline |
| **Dev** | Código | Implementa, ingestão, Arguidor; **não aprova** Gatekeeper |
| **Tester** | Testes | Cria/executa testes, registra evidências |
| **QA** | Qualidade | Revisa/aprova resultados, valida maturity |

**Porta:** `is_active_integrated_member()` filtra `is_active AND joined_at IS NOT NULL`.

---

## §4. 12 Personas LLM (Conjunto B — agentes de IA)

**NÃO são papéis humanos.** Validam documentos no pipeline n8n em paralelo.

| Tag | Persona | Papel |
|-----|---------|-------|
| AUD | Auditor | Router — classifica doc, despacha para especialistas |
| GP | Gerente de Projetos | **Orquestrador** — supervisiona equipe |
| ARQ | Arquiteto | Valida stack, padrões, NFRs |
| DBA | DBA | Valida schema, migrações, retenção |
| DEV | Dev Sênior | Valida implementabilidade, dependências |
| QA | QA | Valida testes, cobertura, BDD |
| UX | UX Designer | Jornada, acessibilidade, WCAG |
| UI | UI Designer | Design system, responsividade |
| SEG | Security | OWASP, AuthN/Z, superfície de ataque |
| **CONF** | **Conformidade** | **BLOQUEANTE** — score <60 bloqueia ingestão |
| LGPD | Proteção de Dados | Dados pessoais, base legal, retenção |
| NEG | Negócio | Valor estratégico, ROI, risco |

**Orquestração:** n8n fan-out paralelo + Redis accumulator → update OCG único.

---

## §5. OCG — Invariantes Canônicas

### Regra 1: OCG Não Contrai
- ✅ OCG cresce com informação útil
- ❌ OCG não sobrescreve, não descarta
- Ingestão ruim → **quarentena**, OCG intocado

### Regra 2: OCG Versionado
- Tabela `ocg_delta_log` — hash chain imutável
- Cada change: `change_type`, `trigger_source`, versão
- Auditável, reversível

### Regra 3: OCG Gate ≥95%
- **Limiar:** `SCORE_MATURIDADE = 95` em `ocg_gate.py:64`
- **Decisão GP 2 (2026-05-04):** Todos 7 pilares (P1-P7) ≥95%
- Um pilar <95% → CodeGen bloqueado
- 5 níveis de bloqueio: `hard_block`, `insufficient` (<60), `immature` (<95), `pillar_immature`, `no_ocg`

---

## §6. Criticidade de IA (3 níveis)

| Nível | Exemplos | Provider |
|-------|----------|----------|
| **Baixa** | Classificação, extração, normalização | Local/Ollama ✅ |
| **Média** | Perguntas dirigidas, pré-análise | Qualquer ✅ |
| **Alta** | OCG consolidação, Gatekeeper, CodeGen | Premium obrigatório ❌ fallback proibido |

**Porta única:** `AIKeyResolver.resolve_project_provider_chain(db, project_id)`.

---

## §7. Gatekeeper — 5 Porteiros Sequenciais

Ordem fixa, **não pular**.

```
1. Gerente de Projetos   → Veredito: escopo + viabilidade + negócio
2. Arquiteto              → Veredito: stack + padrões + NFRs
3. DBA                    → Veredito: schema + migrações (ou N/A)
4. Dev Sênior             → Implementação completa
5. Tester/QA              → Veredito: testes + cobertura + regressão
   → preparar-release (skill) → checklist final
```

Cada porteiro responde em formato canônico:
1. Veredito (Aprovado | Reprovado | Ressalvas)
2. Achados principais
3. Riscos
4. Correções obrigatórias
5. Correções recomendadas
6. Arquivos impactados
7. Critério de aceite
8. Próxima ação

---

## §8. Pipeline Canônico (MVP 35 + MVP 34)

1. **Questionário Técnico** (MVP 35):
   - Camada 1: RulesEvaluator (30 regras DSL determinísticas)
   - Camada 2: LLM sanity check (verificação semântica)
   
2. **Ingestão Documental:**
   - Upload + validação conformidade
   
3. **Pipeline n8n** (135s com DeepSeek):
   - AUD classifica → fan-out aos 11 especialistas
   - 12 personas em paralelo
   - Redis accumulator → update OCG único
   
4. **Soft-delete + Revert** (MVP 34):
   - GP soft-deleta documento (`deleted_at IS NOT NULL`)
   - OCGUpdaterService recomputa ignorando doc deletado
   - `ocg_delta_log` entry → `REVERT_DOCUMENT_DELETE`
   - Módulos órfãos → `archived`

---

## §9. Compliance & Dados

### LGPD
- ✅ Criptografia pgcrypto em `project_secrets`
- ✅ Audit log global (hash chain)
- ⚠️ Purge físico pendente (DT-086, future MVP)

### Erro Determinístico (Nunca Silencioso)
```python
try:
    # operação
except Exception as e:
    logger.error(...); raise  # NUNCA except: pass
```

---

## §10. Provider de IA — Escolha do Cliente

- ✅ Cliente usa suas próprias chaves
- ✅ Sistema oferece análise de adequação
- ✅ Modo híbrido por tipo de tarefa (configurável)

**Providers implementados:** Anthropic, OpenAI, DeepSeek  
**DTs abertas:** DT-079 (hardcode Anthropic em alguns pontos)

---

## §11. Histórico MVPs (Últimos 7)

| MVP | Status | Data | Descrição |
|-----|--------|------|-----------|
| 35 | ✅ | 2026-05-03 | Validação canônica Questionário Técnico |
| 34 | ✅ | 2026-05-03 | Reversão soft-delete + OCG recompute |
| 33 | ✅ | 2026-05-02 | Expansão para 12 personas |
| 32 | ✅ | 2026-05-02 | OCG Updater funcional |
| 31 | ✅ | 2026-05-02 | OCG Cumulativo + CodeGen Gate |
| 30 | ✅ | 2026-05-02 | Pipeline n8n 12 personas end-to-end |
| 29 | ✅ | 2026-04-28 | Hardening Celery |

**Baseline:** 35 MVPs fechados, ~245+ testes passing, 0 DTs críticas.

---

## §12. DTs Abertas (8)

| ID | Sev | Tema | Status |
|----|----|------|--------|
| DT-079 | Major | Hardcode Anthropic em `module_codegen_service.py` | Aberta |
| DT-080 | Minor | Formato `arguider_analysis` em `ocg_individual` | Aberta |
| DT-082 | Minor | Cleanup (não aplicar gate HTTP) | Aberta |
| DT-083 | Minor | Testes regredidos MVP 31 | Aberta |
| DT-084 | Major | 5 testes legado falhando (MVP 33) | Aberta |
| DT-086 | Major | Purge físico LGPD | Future |
| DT-087 | Minor | FK `ingested_documents.uploaded_by` | Aberta |

---

**Última atualização:** 2026-05-05 (Fase 2)
