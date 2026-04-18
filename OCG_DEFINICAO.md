# OCG — Objeto de Contexto Global

> ⚠️ **DOCUMENTO DE REFERÊNCIA — precede o contrato canônico.**
> Descreve a definição teórica do OCG. O **contrato canônico vigente**
> ([`GCA_CANONICAL_CONTRACT.md §5`](GCA_CANONICAL_CONTRACT.md)) e a skill
> `gca-ocg-engine` são as fontes soberanas sobre comportamento do OCG na
> implementação atual. Em caso de divergência, o contrato vence.

## Definição Central

O **OCG (Objeto de Contexto Global)** é a fonte única de verdade do projeto no GCA.

Ele inicia obrigatoriamente a partir do questionário externo aprovado, mas **não é estático**.
Ele evolui continuamente baseado em eventos do sistema — é um **objeto de estado evolutivo orientado a eventos**.

- **Expande** com boa ingestão de dados (novos documentos, análises positivas)
- **Contrai** com dados ruins, conflitantes ou incompletos (reduz confiança)
- **Sempre versionado e auditável** — toda mudança gera delta log e trilha de auditoria

Nenhum módulo pode assumir defaults invisíveis quando o OCG não estiver completo;
deve bloquear ou exigir complementação.

---

## Princípio Fundamental

O OCG não é uma IA autônoma. Ele é uma **inteligência derivada**, calculada a partir do estado do projeto. Todo módulo do pipeline deve:

1. **ANTES**: Carregar o OCG como contexto principal
2. **DURANTE**: Usar o OCG para decisões (stack, compliance, segurança, testes)
3. **DEPOIS**: Atualizar o OCG, versionar e emitir evento de auditoria

---

## Ciclo de Vida

```
Questionário Externo (49Q)
    ↓
Technology Verification (8 fases, 50+ validações)
    ↓
Aprovação Admin (score >= 90)
    ↓
Pipeline OCG (8 agentes IA)
    ├── Agent 0: Analyzer — classifica respostas por pilar
    ├── Agents 1-7: Pillar Specialists (paralelo) — analisa cada pilar
    └── Agent 8: Consolidator — consolida OCG final em PT-BR
    ↓
OCG Persistido (versionado, auditado)
    ↓
Expansão/Contração (ingestão de documentos, Arguidor, Gatekeeper)
    ↓
Propagação (backlog vivo, módulos dependentes, documentação)
```

---

## Máquina de Estado

```yaml
OCG_ENGINE:
  type: event_driven_state_machine

  events:
    - QUESTIONNAIRE_APPROVED      # Cria OCG inicial
    - DOCUMENT_INGESTED           # Expande/contrai contexto
    - DOCUMENT_QUARANTINED        # Bloqueia propagação (PII detectado)
    - GATEKEEPER_EVALUATED        # Atualiza scores e findings
    - ARGUIDER_RESPONSE_REGISTERED # Enriquece OCG com análise
    - CODEGEN_COMPLETED           # Registra artefato gerado
    - QA_EXECUTION_COMPLETED      # Atualiza estado de qualidade
    - BACKLOG_REGENERATED         # Recalcula backlog do OCG

  behaviors:
    expand_context:    # Boa ingestão → mais dados, maior confiança
    contract_context:  # Dados ruins → reduz confiança, marca lacunas
    update_context:    # Atualização parcial (ex: score de pilar)
    block_propagation: # Documento em quarentena → não afeta OCG
```

### Expansão vs Contração

| Situação | Ação sobre o OCG | Impacto |
|----------|------------------|---------|
| Boa ingestão (documento válido) | **Expande** contexto | Mais dados, maior confiança |
| Ingestão parcial | **Atualiza** com lacunas marcadas | Confiança mantida |
| Dados conflitantes | **Contrai** confiança | Alerta, requer decisão |
| Documento reprovado/quarentena | **Bloqueia** propagação | Não afeta OCG |
| Gatekeeper aprovação | **Expande** score e status | Habilita CodeGen |
| QA falhou | **Contrai** qualidade | Bloqueia entrega |

---

## Estrutura do OCG (Schema v1.0.0)

### Seções Obrigatórias

| Seção | Descrição | Origem |
|-------|-----------|--------|
| `PROJECT_PROFILE` | Perfil: nome, tipo, criticidade, arquitetura, modelo execução | Questionário + Analyzer |
| `PILLAR_SCORES` | Scores P1-P7 com nível de aderência e contagem de findings | Pillar Specialists |
| `COMPOSITE_SCORE` | Score composto ponderado + status de aprovação | Consolidator |
| `STACK_RECOMMENDATION` | Stack: frontend, backend, banco, cache, infra, observabilidade, segurança | Consolidator + Questionário |
| `CRITICAL_FINDINGS` | Achados críticos que impedem ou arriscam o projeto | Pillar Specialists |
| `TESTING_REQUIREMENTS` | Testes: tipos, cobertura, ferramentas, cenários | Consolidator + Questionário |
| `COMPLIANCE_CHECKLIST` | Conformidade: LGPD, GDPR, auditoria, PCI-DSS | P2 Compliance + Consolidator |
| `DELIVERABLES` | Entregáveis esperados do projeto | Consolidator |
| `ARCHITECTURE_OVERVIEW` | Visão arquitetural: estilo, componentes, fluxo de dados | P5 Architecture + Consolidator |
| `RISK_ANALYSIS` | Riscos alto/médio/baixo com mitigações e responsáveis | Consolidator |
| `APPROVAL_STATUS` | Status: READY, NEEDS_REVIEW, AT_RISK, BLOCKED | Consolidator |

### Campos de Saúde do Contexto (futuro)

```json
{
  "context_health": {
    "depth": "initial | expanded | contracted",
    "confidence": 0.0,
    "ingestion_quality": "good | partial | bad",
    "last_event": "DOCUMENT_INGESTED",
    "version": 3,
    "delta_count": 2
  }
}
```

---

## Pesos dos Pilares

| Pilar | Nome | Peso | Bloqueante se < 70 |
|-------|------|------|-------------------|
| P1 | Caso de Negócio | 10% | Não |
| P2 | Regras e Compliance | 15% | **Sim** (LGPD/GDPR) |
| P3 | Funcionalidades e Escopo | 20% | Não |
| P4 | Requisitos Não-Funcionais | 20% | Não |
| P5 | Arquitetura e Design | 15% | Não |
| P6 | Dados e Persistência | 10% | Não |
| P7 | Segurança e Proteção | 10% | **Sim** |

**Fórmula**: `composite = P1×10% + P2×15% + P3×20% + P4×20% + P5×15% + P6×10% + P7×10%`

---

## Regras de Aprovação

1. Se P7 < 70 → **BLOCKED** (falhas de segurança impedem prosseguimento)
2. Se P2 < 70 e LGPD/GDPR se aplica → **BLOCKED** (bloqueio de compliance)
3. Se composite >= 90 → **READY** (aprovado para geração de código)
4. Se composite >= 75 → **NEEDS_REVIEW** (lacunas menores, pode prosseguir com cautela)
5. Se composite < 75 → **AT_RISK** (lacunas significativas, recomenda correções)

---

## Compartimentalização

- Cada projeto tem seu próprio OCG — documentos de um projeto **não afetam outro**
- O OCG é a fonte de verdade **do projeto**, não do sistema
- Chaves de IA do pipeline OCG (camada Admin) são separadas das chaves do projeto (camada GP)
- O Admin configura chaves globais usadas **apenas** para avaliação do questionário externo
- O GP configura suas próprias chaves de IA nas Settings do projeto (vault criptografado)

---

## Propagação Automática

| Mudança no OCG | Módulos Impactados | Comportamento |
|----------------|-------------------|---------------|
| AI profile | Ingestão, Arguidor, CodeGen, LiveDocs | Revalidar provedor, mascaramento, budget |
| Stack / repositório | CodeGen, QA, LiveDocs, Legado | Trocar templates, imagem base, testes |
| Compliance | Ingestão, quarentena, auditoria, QA | Aplicar bloqueios, mascaramento, retenção |
| QA profile | QA Readiness, dashboards | Regerar plano de testes, executor, indicadores |

---

## Backlog Vivo

O backlog é **derivado do OCG**. Sempre que o OCG muda:
- Backlog é recalculado (itens auto-gerados substituídos, manuais preservados)
- Módulos dependentes são reavaliados
- Documentação viva é regenerada

### Categorias do Backlog

| Categoria | Itens Esperados |
|-----------|----------------|
| `modules` | Módulos a construir, especificações técnicas, design |
| `tests` | Unitários, integração, E2E, segurança, performance |
| `compliance` | Normas regulatórias, auditorias, LGPD/GDPR |
| `security` | Requisitos de segurança, vulnerabilidades, certificações |
| `agile` | Histórias de usuário, épicos, bugs, dívida técnica |
| `other` | Requisitos não-funcionais, documentos de design |

---

## Endpoints da API — Mapa Completo

### OCG — Geração e Consulta

| Método | Endpoint | Descrição | Permissão |
|--------|----------|-----------|-----------|
| `POST` | `/api/v1/agents/ocg/generate` | Pipeline completo 8 agentes → gera OCG | Admin/GP autenticado |
| `GET` | `/api/v1/projects/{id}/ocg` | OCG mais recente do projeto | Membro do projeto |
| `GET` | `/api/v1/ocg/{ocg_id}` | OCG por ID específico | Membro do projeto |
| `POST` | `/api/v1/agents/analyze` | Agent 0: Analyzer (classificação) | Admin |
| `POST` | `/api/v1/agents/pillar/{pillar_id}` | Agent 1-7: Pillar Specialist | Admin |
| `POST` | `/api/v1/agents/consolidate` | Agent 8: Consolidator | Admin |

### Questionário — Entrada do OCG

| Método | Endpoint | Descrição | Permissão |
|--------|----------|-----------|-----------|
| `POST` | `/api/v1/questionnaires/` | Submeter questionário (externo ou projeto) | Público/GP |
| `GET` | `/api/v1/questionnaires/{id}/status` | Status de análise do questionário | GP |
| `GET` | `/api/v1/projects/{id}/questionnaire` | Questionário vinculado ao projeto | Membro |

### Ingestão — Expansão do OCG

| Método | Endpoint | Descrição | Permissão |
|--------|----------|-----------|-----------|
| `POST` | `/api/v1/projects/{id}/ingestion` | Upload de documento (PDF, DOCX, código, etc.) | GP/Dev |
| `GET` | `/api/v1/projects/{id}/ingestion` | Listar documentos ingeridos | Membro |
| `GET` | `/api/v1/projects/{id}/ingestion/{doc_id}` | Detalhe do documento | Membro |
| `GET` | `/api/v1/projects/{id}/ingestion/{doc_id}/status` | Status de análise (Arguidor) | Membro |
| `DELETE` | `/api/v1/projects/{id}/ingestion/{doc_id}` | Remover documento | GP |

### Gatekeeper — Avaliação do OCG

| Método | Endpoint | Descrição | Permissão |
|--------|----------|-----------|-----------|
| `GET` | `/api/v1/projects/{id}/gatekeeper` | Visão geral do Gatekeeper (scores, findings) | Membro |
| `GET` | `/api/v1/projects/{id}/gatekeeper/modules` | Módulos avaliados pelo Gatekeeper | Membro |
| `POST` | `/api/v1/projects/{id}/gatekeeper/items/{item_id}/resolve` | Resolver item (gap/show-stopper) | GP/Tech Lead |
| `POST` | `/api/v1/projects/{id}/gatekeeper/items/{item_id}/ignore` | Ignorar item com justificativa | GP |
| `POST` | `/api/v1/projects/{id}/gatekeeper/modules/{mod_id}/approve` | Aprovar módulo para CodeGen | GP/Tech Lead |
| `POST` | `/api/v1/projects/{id}/gatekeeper/modules/{mod_id}/reject` | Rejeitar módulo | GP |
| `GET` | `/api/v1/projects/{id}/gatekeeper/report` | Relatório completo (PDF/JSON) | Membro |

### Backlog Vivo — Derivado do OCG

| Método | Endpoint | Descrição | Permissão |
|--------|----------|-----------|-----------|
| `GET` | `/api/v1/projects/{id}/backlog` | Listar itens do backlog (filtro por categoria) | Membro |
| `POST` | `/api/v1/projects/{id}/backlog/regenerate` | Regenerar backlog a partir do OCG atual | GP |

### Projeto — Contexto Compartimentalizado

| Método | Endpoint | Descrição | Permissão |
|--------|----------|-----------|-----------|
| `GET` | `/api/v1/projects/` | Listar projetos (Admin vê todos, GP vê seus) | Autenticado |
| `GET` | `/api/v1/projects/{id}` | Detalhe do projeto | Membro |
| `GET` | `/api/v1/projects/{id}/members` | Membros ativos do projeto | Membro |
| `GET` | `/api/v1/projects/{id}/pending-invites` | Convites pendentes | GP |
| `POST` | `/api/v1/projects/{id}/invite` | Convidar membro (nome, email, papel) | GP |
| `POST` | `/api/v1/projects/{id}/invites/{invite_id}/revoke` | Revogar convite pendente | GP |
| `POST` | `/api/v1/projects/{id}/accept-invite` | Aceitar convite (via token) | Público |
| `POST` | `/api/v1/projects/{id}/activate` | Definir como contexto ativo do usuário | Membro |

### Auditoria — Rastreabilidade do OCG

| Método | Endpoint | Descrição | Permissão |
|--------|----------|-----------|-----------|
| `GET` | `/api/v1/admin/audit` | Trilha de auditoria global (hash chain) | Admin |
| `GET` | `/api/v1/admin/audit/verify-chain` | Verificar integridade da cadeia de hashes | Admin |
| `GET` | `/api/v1/admin/projects/{id}/activity-log` | Log de atividade por projeto | Admin |

### Administração GCA — Camada Global

| Método | Endpoint | Descrição | Permissão |
|--------|----------|-----------|-----------|
| `GET` | `/api/v1/admin/gca/settings` | Pesos dos pilares, thresholds, config agentes | Admin |
| `PUT` | `/api/v1/admin/gca/settings/pillar-weights` | Alterar pesos dos 7 pilares | Admin |
| `PUT` | `/api/v1/admin/gca/settings/thresholds` | Alterar thresholds de aprovação | Admin |
| `GET` | `/api/v1/admin/gca/ai-providers` | Listar provedores IA configurados | Admin |
| `PUT` | `/api/v1/admin/gca/ai-providers` | Configurar provedor IA (chave, modelo) | Admin |
| `POST` | `/api/v1/admin/gca/ai-providers/test` | Testar conexão com provedor | Admin |
| `PUT` | `/api/v1/admin/gca/ai-providers/default` | Definir provedor padrão | Admin |
| `GET` | `/api/v1/admin/dashboard/metrics` | Métricas globais do sistema | Admin |
| `GET` | `/api/v1/admin/projects/pending` | Listar project requests (todos os status) | Admin |
| `POST` | `/api/v1/admin/projects/{id}/approve` | Aprovar projeto (cria User, Project, Member, 2 emails) | Admin |

---

## Endpoints Planejados (Ainda Não Implementados)

| Método | Endpoint | Descrição | Prioridade |
|--------|----------|-----------|-----------|
| `PUT` | `/api/v1/projects/{id}/ocg` | Atualizar OCG manualmente (expand/contract) | Alta |
| `GET` | `/api/v1/projects/{id}/ocg/history` | Histórico de versões do OCG | Média |
| `GET` | `/api/v1/projects/{id}/ocg/delta-log` | Log de mudanças (quem, quando, o quê) | Média |
| `POST` | `/api/v1/projects/{id}/ocg/propagate` | Forçar propagação para módulos dependentes | Média |
| `GET` | `/api/v1/projects/{id}/ocg/health` | Saúde do contexto (depth, confidence, quality) | Baixa |
| `POST` | `/api/v1/projects/{id}/ingestion/{doc_id}/release` | Liberar documento da quarentena | Alta |
| `GET` | `/api/v1/projects/{id}/audit` | Auditoria por projeto (não global) | Média |

---

## Catálogo de Eventos (26 tipos)

### Projeto e Questionário (1-9)
- `PROJECT_REQUEST_CREATED` — Solicitação de novo projeto
- `PROJECT_PROVISIONING_STARTED` — Início do provisionamento do tenant
- `PROJECT_PROVISIONED` — Tenant criado com sucesso
- `QUESTIONNAIRE_SUBMITTED` — Questionário submetido para análise
- `QUESTIONNAIRE_APPROVED` — Questionário aprovado (dispara OCG)
- `DOCUMENT_INGESTED` — Documento processado pelo Arguidor
- `DOCUMENT_QUARANTINED` — Documento com PII detectado
- `MASTER_DOCUMENT_MERGED` — Documentos consolidados
- `GATEKEEPER_EVALUATED` — Avaliação do Gatekeeper concluída

### Agentes e Geração (10-18)
- `ARGUIDER_QUESTION_OPENED` — Arguidor identificou lacuna
- `ARGUIDER_RESPONSE_REGISTERED` — Resposta registrada para lacuna
- `CODEGEN_REQUESTED` — Geração de código solicitada
- `CODEGEN_COMPLETED` — Código gerado com sucesso
- `CODE_VALIDATION_COMPLETED` — Validação de código concluída
- `QA_EXECUTION_REQUESTED` — Execução de testes solicitada
- `QA_EXECUTION_COMPLETED` — Testes executados
- `LIVEDOCS_UPDATED` — Documentação viva atualizada
- `WEBHOOK_HEALTH_CHANGED` — Status de webhook alterado

### Usuários e Memberships (19-26)
- `CREDENTIAL_STATUS_CHANGED` — Credencial alterada
- `GP_USER_CREATED` — Usuário GP criado automaticamente
- `PROJECT_MEMBERSHIP_CREATED` — Membro adicionado ao projeto
- `PROJECT_INVITE_CREATED` — Convite criado
- `PROJECT_INVITE_EMAIL_SENT` — Email de convite enviado
- `PROJECT_INVITE_ACCEPTED` — Convite aceito
- `PROJECT_CONTEXT_ACTIVATED` — Contexto ativo do projeto definido
- `BACKLOG_REGENERATED` — Backlog regenerado do OCG
- `AUDIT_CHAIN_VERIFIED` — Integridade da cadeia verificada

---

*Documento de referência técnica do OCG no GCA.*
*Atualizado em: 2026-04-09 — Sessão 17*
