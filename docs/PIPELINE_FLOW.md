# Pipeline GCA — Fluxo Canônico Simplificado

**Versão:** 3.0
**Data:** 2026-05-01
**Status:** Simplificado (Fase 2: 5 personas canônicas)

---

## 1. Visão Geral

Pipeline simplificado: entrada única (Questionário Técnico) → 5 personas → OCG → Gatekeeper → Backlog/CodeGen.
Nenhum desvio, nenhum sistema paralelo.

```
Questionário Técnico (1)
    │
    ▼
┌──────────────────────────────────────────────┐
│ 1. PERSONAS (5)        questionnaire.py      │
│    gp, arquiteto, dba, dev_sr, qa           │
│    Cada persona avalia respostas             │
│    Cria PersonaResponse com ocg_delta        │
│    Dispara geração OCG quando 5/5 completam  │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ 2. OCG (legacy)        generate_ocg_task     │
│    Pipeline 8-agentes consolida respostas     │
│    Gera OCG com versão e ocg_data            │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ 3. GATEKEEPER          gatekeeper_service    │
│    Avalia 7 pilares de qualidade             │
│    Score 0-100 por pilar                     │
│    P1 (Conformidade) bloqueante (<60)        │
│    Demais pilares: avisos/recomendações      │
│    Controla ready_for_codegen                │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ 4. BACKLOG             backlog_service       │
│    Itens acionáveis ordenados por prioridade  │
│    critical > high > medium > low (MoSCoW)   │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ 5. CODEGEN            codegen_service        │
│    Gera código baseado em OCG + Gatekeeper   │
└──────────────────────────────────────────────┘
```

**Regra de ouro:** Nenhum estágio avança sem o anterior completo.

---

## 2. Estágios Detalhados

### 2.1 Questionário Técnico (`technical_questionnaire_router.py`)

**Entrada:** Formulário com respostas técnicas
**Saída:** Disparo de 5 personas paralelas

**Fluxo:**
1. User submete questionário (`submit=true` via PATCH)
2. Dispara 5 `evaluate_persona_task` em paralelo (Celery group):
   - `gp` — Gerente de Projetos
   - `arquiteto` — Arquiteto de Software
   - `dba` — Administrador de Banco de Dados
   - `dev_sr` — Desenvolvedor Sênior
   - `qa` — Quality Assurance
3. Dispara regeneração de Pilares Vivos (async)

### 2.2 Personas (`questionnaire.py`)

**Entrada:** Respostas do questionário
**Saída:** `PersonaResponse` (1 por persona) com `ocg_delta`

**Fluxo:**
1. Cada persona recebe perguntas + respostas do questionário
2. Chama LLM do projeto (provider configurável via AIKeyResolver)
3. Gera `PersonaResponse` com parecer, risco, recomendação
4. Quando 5/5 completam → `generate_ocg_task` é disparado

### 2.3 OCG (`generate_ocg_task` → `QuestionnaireService._generate_ocg()`)

**Entrada:** 5 PersonaResponse + respostas do questionário
**Saída:** `OCG` (legacy, FK `questionnaire_id`)

**Fluxo:**
1. Pipeline de 8 agentes especializados processa respostas
2. Consolida em documento OCG estruturado
3. Salva com versão e `ocg_data` (JSON)
4. Disponibiliza para Gatekeeper, Arguidor e CodeGen

### 2.4 Gatekeeper (`gatekeeper_service.py`)

**Entrada:** OCG + dados do projeto
**Saída:** Scores por pilar + status (approved/blocked/needs_review)

**Detalhes:**
- 7 pilares avaliados: Conformidade, Arquitetura, Segurança, Performance, Testabilidade, Manutenibilidade, Documentação
- Score 0-100 por pilar
- P1 (Conformidade): score < 60 = bloqueante
- Admin pode fazer override de bloqueios
- Controla `ready_for_codegen`

### 2.5 Backlog (`backlog_service.py`)

**Entrada:** Gatekeeper items
**Saída:** Itens ordenados por prioridade (MoSCoW)

### 2.6 CodeGen (`codegen_service.py`)

**Entrada:** OCG + Gatekeeper aprovado
**Saída:** Código gerado por módulo

---

## 3. Histórico de Simplificação

### 2026-05-01 — Fase 2 Simplificação

**O que foi removido:**
1. `persona_tasks.py` — 7 personas da ingestão (IA_DBA, IA_Compliance, IA_Security, IA_Arquiteto, IA_Dev, IA_Tester, IA_QA)
2. `OCGIndividual` — modelo ORM (análise individual por persona de ingestão)
3. `OCGIndividualRefined` — modelo ORM (refinamento pós-follow-up)
4. `PersonaFollowUpQuestion` — modelo ORM (perguntas de clarificação)
5. `OCGGlobal` — modelo ORM (consolidação das 7 personas de ingestão)
6. `ocg_consolidation_service.py` — serviço de consolidação OCGIndividual → OCGGlobal
7. `follow_up_service.py` — serviço de follow-up questions
8. `analysis_dashboard_router.py` — dashboard de análise de personas
9. `ocg_override_router.py` — override manual de conflitos OCGGlobal
10. Botão "Exportar PDF" (sem onClick) do formulário de questionário

**Guardrails removidos:**
- DT-AUDITORIA-003 (≥7 OCGIndividual no Arguidor)
- Fallback OCGGlobal no OCGUpdater
- Dispatch de persona_tasks na ingestion_router

**Pipeline resultante:**
```
Questionário → 5 Personas → OCG (legacy) → Gatekeeper → Backlog → CodeGen
```
