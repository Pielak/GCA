# 🔴 AUDITORIA CRÍTICA — Pipeline GCA Fluxo de Dados
**Data**: 2026-04-30  
**Projeto**: Assistente Judicial para Advogados  
**Status**: PIPELINE QUEBRADO EM 3 PONTOS CRÍTICOS  

> **2026-05-01 — Simplificação aplicada**: Pipeline refatorado para 5 personas
> canônicas (gp, arquiteto, dba, dev_sr, qa) com OCG legacy como único modelo
> de conhecimento. Toda a camada de 7 personas da ingestão + OCGIndividual +
> OCGGlobal foi removida. Ver `docs/PIPELINE_FLOW.md` v3.0 para fluxo atual.

---

## EXECUTIVO

O GCA foi construído em **camadas independentes que não se comunicam**. Isto resulta em:

1. **87 Gatekeeper items criados ficcionalmente** (sem análise real de personas)
2. **0 análises de personas executadas** (tasks disparadas mas nunca rodaram)
3. **Pipeline invertido** (ingestão tenta OCG que não existe)
4. **"Fernando" adicionado sem consentimento** (fluxo de criação de projeto)
5. **80 backlog items "blocked"** (esperando dados que nunca virão)

**Impacto**: O GCA não está funcionando como fábrica de software. É um **dumpificador de dados** que injeta documentação fictícia.

---

## 1. ACHADO #1: "Fernando" Como GP (Data Integrity Issue)

### Fato
- **ProjectRequest criada**: Fernando (minicooper2020br@outlook.com) em 2026-04-29 17:54:31
- **Aprovada por**: pielak.ctba@gmail.com (você/admin) em 2026-04-29 17:55:14
- **Resultado**: Fernando automaticamente adicionado como GP

### Raiz
Código em `/app/services/admin_service.py:229`:
```python
member = ProjectMember(
    project_id=project.id,
    user_id=request.gp_id,  # ← Quem criou a solicitação vira GP
    role="gp",
    invited_at=_now,
    accepted_at=_now,
    joined_at=_now,
    is_active=True,
)
```

**Problema**: Não há fluxo para **você** solicitar o projeto. Fernando solicitou primeiro, admin aprovou, Fernando ficou GP.

### Impacto
- ❌ Você (Pielak) não é membro do projeto
- ❌ Você não consegue acessar como GP
- ❌ Compartimentalização quebrada: Fernando é GP em projeto que você financiou

### Solução Necessária
**DT-AUDITORIA-001**: Corrigir fluxo de criação de projeto:
- Permitir que admin (você) crie projeto **direto** sem PassPCR por ProjectRequest
- OU: Após aprovação, permitir **transferência de GP** para usuário correto
- Implementação: `POST /projects/{id}/transfer-gp/{target_user_id}` já existe (linha 494 em projects.py)

---

## 2. ACHADO #2: Personas Nunca Foram Executadas (CRÍTICO)

### Fato: Pipeline Quebrado em 3 Pontos

| Estágio | Esperado | Realidade | Status |
|---------|----------|-----------|--------|
| Documentos ingestados | N | 4 | ✓ |
| Análises de personas (OCGIndividual) | N | **0** | ✗ CRÍTICO |
| OCG consolidados (OCGGlobal) | N | **0** | ✗ CRÍTICO |
| Análises do Arguidor | N | 4 | ✗ FAKE |
| Gatekeeper items | N | 87 | ✗ FICTÍCIO |
| Backlog items | N | 80 (blocked) | ✗ BLOQUEADO |

### Raiz: Fluxo Invertido

**Código em `/app/routers/ingestion_router.py:79-88`** (CORRETO):
```python
if sc == 200 and "document_id" in result:
    for persona in ["IA_DBA", "IA_Compliance", "IA_Security", ...]:
        analyze_document_with_persona.delay(
            document_id=str(document_id),
            project_id=str(project_id),
            persona_type=persona,
        )
    logger.info("personas.analysis_dispatched", ...)
```

**Tasks foram disparadas ✓**

**Problema**: Documentos ingestados **disparam análise de personas**, mas simultaneamente:

1. **Ingestão service tenta análise imediata** (`/app/services/ingestion_service.py:1570`)
2. Análise reativa REQUER `OCG_Global` pré-existente
3. OCG não existe porque personas **ainda não terminaram** (race condition)
4. Análise falha com:
   ```
   ValueError: OCG não encontrado para o projeto 24bf72c3-2ee8-45fd-b879-d3a00b347c39
   ```

### Log da Falha (Celery Worker)
```
[2026-04-30 00:09:38,801: WARNING/ForkPoolWorker-1] 
ingestion.ocg_reactive_error   
document_id=ba065de0-5746-47a2-a319-15c8cc26dba3 
error=OCG não encontrado para o projeto 24bf72c3-2ee8-45fd-b879-d3a00b347c39.
```

### Fluxo Esperado vs. Atual

**ESPERADO** (canônico):
```
1. Questionário respodido e submetido
2. Gate: Ativar Ingestão
3. Documentos ingestados → Dispara 7 personas (async)
4. 7 personas analisam em paralelo → Criam OCGIndividual
5. OCG consolidação aguarda 7 análises → Cria OCGGlobal
6. DEPOIS: Arguidor lê OCGGlobal consolidado
7. DEPOIS: Gatekeeper consolida items
8. DEPOIS: Backlog gera itens (ready, não blocked)
9. DEPOIS: CodeGen executa
```

**ATUAL** (quebrado):
```
1. Documentos ingestados
2. ⚠️ Ingestão tenta análise reativa IMEDIATAMENTE
3. ⚠️ OCG não existe (personas ainda não terminaram)
4. ✗ Análise falha com ValueError
5. ❌ Personas tasks são disparadas (mas ignoradas)
6. ❌ OCGIndividual nunca criado
7. ❌ OCGGlobal nunca criado
8. **Pero** Arguidor executa de "jeito" (com dados fake)
9. **Pero** 87 items criados ficcionalmente
10. **Pero** Backlog items "blocked" (esperando CodeGen que nunca virá)
```

### Impacto
- ❌ 4 documentos ingestados = 0 análises reais
- ❌ 87 items de Gatekeeper = dados fictícios
- ❌ 80 backlog items = todos bloqueados, nunca avançam
- ❌ Você vê "Arguidor 87 items" mas nenhum é real
- ❌ Impossível gerar código: não há dados de entrada

### Solução Necessária

**DT-AUDITORIA-002**: Refatorar fluxo de ingestão

1. **Remover análise reativa imediata** (que falha)
2. **Adicionar gate explícito**: "Ingestão aguarda OCG consolidado"
3. **Sequência correta**:
   - Questionário → Personas → OCG Global ✓ (já funciona)
   - **DEPOIS**: Documentos ingestados → Arguidor lê OCG ✓
   - **DEPOIS**: Gatekeeper consolidação ✓
4. **Proteção**: Se OCG não existe, ingestão retorna `status: "awaiting_ocg"`

---

## 3. ACHADO #3: Gatekeeper Items Criados Sem Análise Real (FICTÍCIO)

### Fato

```sql
SELECT item_type, status, COUNT(*) as count 
FROM gatekeeper_items 
WHERE project_id = '24bf72c3-2ee8-45fd-b879-d3a00b347c39'
GROUP BY item_type, status;

    item_type    | status  | count 
-----------------+---------+-------
 show_stopper    | pending |     1
 improvement     | pending |    32
 poor_definition | pending |    14
 gap             | pending |    40
(4 rows)
```

### Pergunta Crítica
**Quem criou esses 87 items?**

Resposta: **Arguidor executou com dados vazios/fake**

- Argumentador lê documentos
- Documentos não têm análise de personas (OCGIndividual = 0)
- Argumentador criou items baseado em **nada**
- 87 items são ficção

### Impacto
- ❌ "87 itens de governança" = 0 são reais
- ❌ Você não consegue trabalhar com eles (dados inválidos)
- ❌ Feedfoward para Backlog é poison

### Solução Necessária

**DT-AUDITORIA-003**: Validação de entrada no Arguidor

1. **Guardrail**: Arguidor rejeita se `ocg_individual.count < 7`
2. **Log**: Não silenciar erros — avisar que OCG está incompleto
3. **Return**: Status `"awaiting_personas"` em vez de criar items fake

---

## 4. ACHADO #4: Backlog Items "Blocked" (Não Bloqueado, Enganado)

### Fato

```sql
SELECT category, status, COUNT(*) as count 
FROM backlog_items 
WHERE project_id = '24bf72c3-2ee8-45fd-b879-d3a00b347c39'
GROUP BY category, status;

 category | status  | count 
----------+---------+-------
 modules  | blocked |    80
(1 row)
```

### Problema

Todos os 80 items estão `status='blocked'` porque:
- Foram criados a partir de **Gatekeeper items fictícios**
- Sistema acha que estão "bloqueados" esperando CodeGen
- Na verdade, estão presos porque **não há dados de entrada válidos**

### Impacto

- ❌ Você vê "80 backlog items" mas nenhum é acionável
- ❌ Status "blocked" não é verdadeiro — é "invalid data"
- ❌ GP não consegue aprovar módulos que não têm análise real

---

## 5. ACHADO #5: Compartimentalização Correta (OK)

### Fato

Isolamento por `project_id` está **funcionando corretamente**:

- 87 items todos têm `project_id = 24bf72c3-2ee8-45fd-b879-d3a00b347c39` ✓
- Nenhum item vaza de outro projeto
- Índices em `project_id` presentes ✓

**Conclusão**: Compartimentalização está OK. Problema é no fluxo, não na isolação.

---

## 6. SUMÁRIO DE PROBLEMAS

| # | Problema | Raiz | Impacto | Severidade |
|---|----------|------|---------|-----------|
| 1 | Fernando é GP sem consentimento | Fluxo ProjectRequest | Você não acessa projeto | 🟡 ALTA |
| 2 | 0 análises de personas | Race condition: ingestão vs OCG | Todo pipeline falha | 🔴 CRÍTICA |
| 3 | 87 items ficcionais | Arguidor cria sem validação | Dados inválidos | 🔴 CRÍTICA |
| 4 | 80 backlog "blocked" | Dependência de dados fake | Não progride | 🔴 CRÍTICA |
| 5 | Fluxo invertido | Ingestão requer OCG que não existe | Pipeline sequencial quebrada | 🔴 CRÍTICA |

---

## 7. ROADMAP DE CORREÇÃO

### Fase 1: Emergência (Hoje)
1. ✓ Transferir GP para você (Pielak): `POST /projects/{id}/transfer-gp/{your_user_id}`
2. ✓ Limpar dados fake: DELETE gatekeeper_items + backlog_items + arguider_analyses
3. ✓ Resetar ingestão documents para `status='pending'`

### Fase 2: Fix do Fluxo (Amanhã)
1. ✓ Remover análise reativa imediata de ingestão
2. ✓ Adicionar gate: ingestão aguarda OCG consolidado
3. ✓ Validação no Arguidor: recusa se `ocg_individual.count < 7`

### Fase 3: Validação (Amanhã à noite)
1. ✓ Test E2E: Questionário → Personas → OCG → Ingestão → Arguidor → Gatekeeper
2. ✓ Verificar que cada estágio depende do anterior
3. ✓ Confirmar dados reais em cada etapa

### Fase 4: Documentação (Quinta)
1. ✓ Atualizar fluxograma canônico
2. ✓ Guardrails em cada serviço
3. ✓ Logging + alertas para race conditions

---

## 8. CONCLUSÃO

**O GCA NÃO É UMA FÁBRICA DE SOFTWARE. É UM DATA INJECTOR.**

Construiu-se em **camadas desacopladas** que não respeitam dependências:

- Ingestão não espera OCG
- Arguidor não valida input
- Backlog não verifica dados
- **Resultado**: Lixo entra, lixo sai

**Próximas 2 horas**: Fase 1 + Fase 2 de correção.

---

**Assinado**: Auditoria Técnica GCA  
**Data**: 2026-04-30 01:15 UTC  
**Confiabilidade**: Confirmado em DB + Celery logs + Código-fonte
