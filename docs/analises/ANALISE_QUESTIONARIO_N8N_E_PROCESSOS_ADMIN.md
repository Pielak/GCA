# Análise: Questionário Técnico + Pipeline n8n + Processos Administrativos

**Data**: 05/04/2026  
**Objetivo**: Mapear inteligência do questionário, validação n8n e processos admin faltantes

---

## 📋 PARTE 1: QUESTIONÁRIO TÉCNICO (gca_questionario_tecnico_tenant_corrigido.html)

### Status Visível para o GP (3 Estados)

#### ❌ ERRADO (Atual)
```
"Incompleto" (vermelho)
"Pendente" (sem cor)
"OK" (verde)
```

#### ✅ CORRETO (O Que Deve Ser)
```
Status 1: "Pendente" (🔴 Vermelho Bold)
  └─ Nenhuma resposta iniciada

Status 2: "Incompleto" (🔴 Vermelho Bold)
  └─ Respondido parcialmente, faltas campos obrigatórios
  └─ OU: Detectados gaps/conflitos que bloqueiam aprovação

Status 3: "OK" (🟢 Verde Bold)
  └─ Todas as respostas obrigatórias respondidas
  └─ Análise n8n passou (≥85% aderência)
  └─ Nenhum conflito detectado
```

**Implementação CSS necessária**:
```css
.status-badge {
  font-weight: bold;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 14px;
}

.status-badge.pending {
  background-color: #dc2626;  /* Vermelho bold */
  color: white;
}

.status-badge.incomplete {
  background-color: #dc2626;  /* Vermelho bold */
  color: white;
}

.status-badge.ok {
  background-color: #16a34a;  /* Verde bold */
  color: white;
}
```

### Campos com Indicadores de Conflito

**O Questionário deve ter**:
- ✅ Campo "Observações" (textarea) — para n8n descrever conflitos
- ✅ Campo "Restrições" (textarea) — para n8n descrever incompatibilidades
- ✅ Sistema de highlighting — campos com conflito em cor diferente (ambar/laranja)
- ❌ **NÃO mostrar**: Percentual de 85% (oculto, apenas admin vê)

**Novo layout necessário**:
```html
<!-- Novo: Seção de Avisos n8n -->
<section class="card" id="n8nAlerts" style="display:none;">
  <h2 style="color: #f59e0b;">⚠️ Observações da Análise Técnica</h2>
  
  <!-- Conflitos encontrados -->
  <div id="conflictsList" style="margin-bottom: 20px;">
    <!-- Preenchido por n8n -->
  </div>
  
  <!-- Campo: Observações -->
  <div class="col-12">
    <label class="lbl">Observações da Análise</label>
    <textarea 
      id="n8nObservations" 
      disabled
      readonly
      style="background: #182235; border: 1px solid #f59e0b;"
    ></textarea>
    <small style="color: #a9b7d4;">
      ℹ️ Campos em destaque abaixo têm conflitos detectados
    </small>
  </div>
  
  <!-- Campo: Restrições -->
  <div class="col-12" style="margin-top: 12px;">
    <label class="lbl">Restrições Técnicas</label>
    <textarea 
      id="n8nRestrictions" 
      disabled
      readonly
      style="background: #182235; border: 1px solid #f59e0b;"
    ></textarea>
  </div>
</section>

<!-- Quando há conflito, campo fica assim: -->
<div class="col-6" id="field-frontend" style="border-left: 4px solid #f59e0b;">
  <label class="lbl" style="color: #f59e0b;">Ferramentas de frontend ⚠️</label>
  <div class="checks">
    <!-- opções -->
  </div>
  <small style="color: #f59e0b;">
    ⚠️ Conflito: React + Flutter não são compatíveis
  </small>
</div>
```

---

## 🤖 PARTE 2: PIPELINE N8N — INTELIGÊNCIA NECESSÁRIA

### Validações que n8n Deve Fazer

#### 1. **Validação de Lógica** (Conflitos Técnicos)

```
REGRA: React + Flutter juntos = CONFLITO
  └─ Motivo: React é web, Flutter é mobile (linguagens diferentes)
  └─ Solução: Escolher UM framework

REGRA: Monólito + Microserviços juntos = CONFLITO
  └─ Motivo: Arquiteturas mutuamente excludentes
  └─ Solução: Escolher UMA arquitetura

REGRA: Offline mode + Monólito cloud = CONFLITO
  └─ Motivo: Offline requer local-first, cloud é server-centric
  └─ Solução: Usar híbrido ou cloud local

REGRA: Aplicativo mobile + Executável desktop = VERIFICAR
  └─ Motivo: Possível (ex: React Native + Electron)
  └─ Score: OK se ambos com framework compatível
```

#### 2. **Validação de Gaps** (Campos Faltantes)

```
REGRA: Se "Aplicação web" selecionado
  └─ Então: Frontend obrigatório
  └─ Se vazio: GAP ❌

REGRA: Se "Microserviço" selecionado
  └─ Então: Messaging obrigatório (Kafka, RabbitMQ)
  └─ Se vazio: GAP ❌

REGRA: Se "Projeto com sistema legado" (Sim)
  └─ Então: Acesso repositório obrigatório
  └─ Se vazio: GAP ❌

REGRA: Se "Criticidade" = Crítica
  └─ Então: Deve ter plano de testes + CI/CD
  └─ Se ausente: GAP ❌
```

#### 3. **Validação de Compatibilidade Stack**

```
REGRA: FastAPI + React = ✅ COMPATÍVEL
REGRA: Django + Vue = ✅ COMPATÍVEL
REGRA: FastAPI + Flutter = ❌ INCOMPATÍVEL
  └─ Motivo: FastAPI é REST/backend, Flutter é mobile
  └─ Sugestão: Usar FastAPI como backend, Flutter como frontend

REGRA: Python + Electron = ❌ INCOMPATÍVEL
  └─ Motivo: Electron é Node.js
  └─ Sugestão: Python para backend, Electron para frontend

REGRA: PostgreSQL + Redis + Kafka = ✅ COMPATÍVEL
REGRA: PostgreSQL sozinho (app grande) = ⚠️ VERIFICAR
  └─ Aviso: Sem cache (Redis) pode ter performance issues
```

#### 4. **Calcular Score de Aderência** (85% threshold)

```
Fórmula: (Respostas Válidas + Compatibilidades OK) / Total de Campos × 100

Exemplo:
  • Total campos: 25
  • Respondidos: 25 ✅
  • Sem conflitos: 24 ✅
  • Com conflitos: 1 ❌
  
  Score = (25 + 24) / (25 + 25) = 49/50 = 98% ✅ APROVADO

Se Score < 85%: BLOQUEADO
Se Score ≥ 85%: LIBERADO
```

#### 5. **Output Estruturado**

```json
{
  "projectId": "proj-001",
  "questionnaireStatus": "OK",  // ou "Incompleto" ou "Pendente"
  "adherenceScore": 98,  // OCULTO DO GP
  "approved": true,  // Score ≥ 85%
  "validations": {
    "logicConflicts": [
      {
        "field": "frontend_stack",
        "conflict": "React + Flutter não são compatíveis",
        "severity": "blocker",
        "suggestion": "Escolha UM framework"
      }
    ],
    "gaps": [
      {
        "field": "messaging",
        "gap": "Microserviço sem mensageria",
        "severity": "warning",
        "suggestion": "Adicione Kafka ou RabbitMQ"
      }
    ],
    "incompatibilities": [
      {
        "backend": "FastAPI",
        "frontend": "Flutter",
        "compatible": false,
        "suggestion": "Use FastAPI como backend + Flutter como mobile"
      }
    ]
  },
  "observations": "Detectados 1 conflito bloqueador e 1 aviso...",
  "restrictions": "Projeto não pode prosseguir sem resolver conflitos",
  "highlightedFields": ["frontend_stack", "messaging"]  // Campos com problema
}
```

---

## 📧 PARTE 3: PROCESSOS ADMINISTRATIVOS FALTANTES

### Checklist de Processos (O Que Existe vs O Que Falta)

| Processo | Status | Evidência | Ação Necessária |
|----------|--------|-----------|-----------------|
| **Email de aprovação de projeto para GP** | ❌ NÃO EXISTE | Nenhuma menção em code/spec | **IMPLEMENTAR** |
| **GP convida equipe para projeto** | ✅ EXISTE | `AdminUsersPage.tsx` tem modal invite | REVALIDAR scope (só internos?) |
| **Recuperação de senha (self-service)** | ⚠️ PARCIAL | `POST /reset-password` existe | REVISAR: Fluxo seguro com token |
| **Primeiro acesso (initial password)** | ❌ NÃO EXISTE | Nenhuma menção | **IMPLEMENTAR** |
| **Troca obrigatória senha primeira vez** | ❌ NÃO EXISTE | Nenhuma menção | **IMPLEMENTAR** |

---

### PROCESSO 1: Email de Aprovação de Projeto para GP ✅ NOVO

**Quando**: Após questionnaire ser aprovado (Score ≥ 85%) por n8n

**Fluxo**:
```
1. n8n analisa questionário
2. Score ≥ 85%?
   ├─ Sim: Gera email de aprovação
   └─ Não: Gera email com gaps a corrigir

3. Email para GP contém:
   ├─ Status do questionário (OK / Incompleto)
   ├─ Observações (se houver conflitos)
   ├─ Restrições (se houver incompatibilidades)
   ├─ Link para entrar no projeto (se aprovado)
   └─ Link para corrigir (se incompleto)
```

**Email Template (Aprovado)**:
```
Assunto: ✅ Projeto [ProjectName] — Aprovado para Ingestão

Olá [GP_Name],

Seu questionário técnico foi analisado e APROVADO! 🎉

📊 Resultado:
  • Status: OK
  • Aderência: 98%
  • Stack recomendado: [Suggeste

d_Stack]
  • Próximo passo: Ingira os artefatos no GCA

ℹ️ Observações da análise:
[Observations from n8n]

🔗 Próximos passos:
  1. Convide sua equipe (link: /project/[id]/invite)
  2. Configure credenciais (link: /project/[id]/credentials)
  3. Inicie ingestão de artefatos

⚠️ Restrições técnicas:
[Restrictions, if any]

---
[Footer with support contact]
```

**Email Template (Incompleto)**:
```
Assunto: ⚠️ Projeto [ProjectName] — Revisão Necessária

Olá [GP_Name],

Seu questionário técnico tem 1 conflito que precisa ser resolvido.

🚨 Conflitos Detectados:
  1. React + Flutter não são compatíveis
     └─ Escolha UM framework

📊 Status:
  • Aderência: 72%
  • Threshold: 85%
  • Diferença: -13%

🔗 Revisar questionário:
[Link para corrigir]

Após corrigir, o sistema reavaluará automaticamente.
```

---

### PROCESSO 2: GP Convida Equipe para Projeto ✅ REVISAR

**Status Atual**:
- ✅ `AdminUsersPage.tsx` tem modal "Convidar Usuário"
- ⚠️ **PROBLEMA**: Convida para ADMIN global, não para PROJETO específico

**O Que Deve Ser**:
```
Interface: ProjectDetailLayout
  └─ Tab: "Equipe"
     └─ Button: "Convidar membro"
        └─ Modal: Selecionar usuário + rol no projeto
           ├─ Tech Lead
           ├─ Dev Sênior
           ├─ Dev Pleno
           ├─ QA
           └─ Compliance

Quando convida:
  1. GP envia convite (não admin)
  2. Usuário recebe email
  3. Email tem link: "Aceitar convite para projeto [name]"
  4. Após aceitar, usuário tem acesso ao projeto
  5. Admin recebe log (auditoria)
```

**Mudanças Necessárias**:
- ✅ Crear nova page: `ProjectTeamPage.tsx`
- ✅ Implementar POST `/api/v1/projects/{id}/invite`
- ✅ Email com link de aceitação
- ✅ Auditoria de convite

---

### PROCESSO 3: Recuperação de Senha ⚠️ REVISAR

**Status Atual**:
- ✅ `POST /reset-password` existe no backend
- ⚠️ **VERIFICAR**: Fluxo seguro com token?

**Fluxo Correto**:
```
1. Usuário clica "Esqueci minha senha"
2. Insere email
3. Sistema gera token (válido por 1 hora)
4. Email enviado com link:
   https://gca.com/reset-password?token=xyz123
5. Usuário clica link
6. Modal: Nova senha + confirmação
7. Token validado no backend
8. Senha atualizada
9. Redirecionado para login
10. Auditoria registrada

Segurança:
  ✅ Token com TTL (1 hora)
  ✅ Token single-use
  ✅ Rate limit (máx 5 tentativas/hora)
  ✅ Sem revelar se email existe
```

**Checklist**:
- [ ] Token gerado com bcrypt
- [ ] TTL de 1 hora
- [ ] Single-use (flag `used`)
- [ ] Rate limiting implementado
- [ ] Email com link seguro
- [ ] Modal com validação de força de senha
- [ ] Auditoria log

---

### PROCESSO 4: Primeiro Acesso (Initial Password) ✅ NOVO

**Quando**: Usuário criado por Admin ou GP

**Fluxo**:
```
1. Admin cria usuário ou GP convida
2. Sistema gera senha temporária: "TmpPwd123!@#"
3. Email enviado com:
   ├─ Email do usuário
   ├─ Senha temporária
   └─ Link: "Primeiro acesso"

4. Usuário clica "Primeiro acesso"
5. Modal de login:
   ├─ Email (pré-preenchido, readonly)
   ├─ Senha temporária
   ├─ Button: "Entrar e trocar senha"

6. Após login bem-sucedido:
   └─ Modal obrigatório: "Alterar senha"
      ├─ Senha temporária (readonly)
      ├─ Nova senha (required)
      ├─ Confirmação (required)
      ├─ Validação força (green checkmark)
      └─ Button: "Salvar e continuar"

7. Após salvar:
   ├─ Redireciona para dashboard
   ├─ Marca flag `first_access_completed = true`
   └─ Auditoria registra "First password changed"

Segurança:
  ✅ Senha temporária única por usuário
  ✅ Válida por 24 horas
  ✅ Força de senha mínima: 12 chars, uppercase, number, special
  ✅ Obrigatoriedade de trocar (não pode pular)
```

**Email Template**:
```
Assunto: 🔐 Bem-vindo ao GCA - Configure sua senha

Olá [UserName],

Você foi convidado para participar do projeto [ProjectName] no GCA.

📋 Seus dados de acesso:
  • Email: [email]
  • Senha temporária: [TmpPassword]
  • Projeto: [ProjectName]
  • Seu papel: [Role]

🔒 Próximas etapas:
1. Clique no link abaixo para primeiro acesso
   [Link com token]
2. Faça login com a senha temporária
3. Altere sua senha (obrigatório)
4. Acesse seu projeto

⚠️ Importante:
  • A senha temporária expira em 24 horas
  • Você será obrigado a alterar a senha no primeiro login
  • Use uma senha forte (mín 12 caracteres)

[Link: Primeiro Acesso]

---
[Footer]
```

---

### PROCESSO 5: Troca Obrigatória Senha Primeira Vez ✅ NOVO

**Já descrito acima** no Processo 4, step 6-7

**Checklist Backend**:
- [ ] Flag `password_changed_at` no User
- [ ] Flag `first_access_completed` no User
- [ ] Middleware que bloqueia se `first_access_completed = false`
- [ ] Endpoint: POST `/api/v1/auth/change-first-password`
- [ ] Validação força de senha
- [ ] Log de auditoria

---

## 🔗 INTEGRAÇÃO: N8N + QUESTIONÁRIO + PROCESSOS ADMIN

### Fluxo Completo:

```
1️⃣ GP responde questionário (externo)
   └─ HTML com status: Pendente → Incompleto → OK

2️⃣ n8n analisa (webhook do formulário)
   ├─ Valida lógica (React + Flutter?)
   ├─ Detecta gaps (microserviço sem messaging?)
   ├─ Compatibilidade stack
   ├─ Calcula score (85% threshold)
   ├─ Gera observações e restrições
   └─ Salva no banco

3️⃣ Frontend atualiza status para GP
   ├─ Se Score ≥ 85%: "OK" (verde bold) ✅
   ├─ Se Score < 85%: "Incompleto" (vermelho bold)
   └─ Mostra campos com conflito (ambar)

4️⃣ Email enviado para GP
   ├─ Se aprovado: "Parabéns, projeto pronto"
   ├─ Se não: "Corrija os conflitos"
   └─ Observações + Restrições

5️⃣ Se aprovado, GP entra no projeto
   └─ Primeira tela: "Convide sua equipe"
      └─ Usa novo ProjectTeamPage
         └─ Seleciona usuários + papéis
            └─ Email enviado com convite
               └─ Usuário clica aceitar
                  └─ Gets first access flow
                     └─ Obrigado trocar senha
```

---

## ✅ CHECKLIST DE IMPLEMENTAÇÃO

### Frontend (HTML/React)

- [ ] Questionário: Status "Pendente" / "Incompleto" / "OK" (colors + bold)
- [ ] Questionário: Campos com conflito destacados (ambar)
- [ ] Questionário: Seções "Observações" e "Restrições" (readonly)
- [ ] ProjectTeamPage: Nova página para convidar equipe
- [ ] LoginPage: Modal obrigatório para trocar senha primeira vez
- [ ] ResetPassword: Page segura com token validation
- [ ] Email templates: 3 tipos (aprovação, conflito, convite)

### Backend (FastAPI)

- [ ] POST `/api/v1/projects/{id}/invite` (GP convida)
- [ ] POST `/api/v1/auth/reset-password` (verify + enhance)
- [ ] POST `/api/v1/auth/change-first-password` (new)
- [ ] GET `/api/v1/questionnaire/{id}/status` (get status)
- [ ] Middleware: Bloqueia acesso se `first_access_completed = false`
- [ ] Email service: 3 templates
- [ ] Auditoria: Log todas as ações (convite, reset, primeiro acesso)

### n8n Workflow

- [ ] Webhook: Recebe formulário completo
- [ ] Validação lógica: 5+ regras
- [ ] Validação gaps: 8+ regras
- [ ] Compatibilidade: Matrix stack
- [ ] Scoring: 85% threshold
- [ ] Output: JSON estruturado
- [ ] Email: Dispara para GP (aprovado/conflito)
- [ ] Auditoria: Log cada análise

### Database

- [ ] Users: Adicionar `first_access_completed` bool
- [ ] Users: Adicionar `password_changed_at` timestamp
- [ ] Questionnaire: Adicionar `n8n_analysis` JSON
- [ ] Questionnaire: Adicionar `approval_status` enum
- [ ] Questionnaire: Adicionar `adherence_score` int
- [ ] Questionnaire: Adicionar `observations` text
- [ ] Questionnaire: Adicionar `restrictions` text
- [ ] ProjectInvite: Nova table (user_id, project_id, role, status, created_at)
- [ ] ResetToken: Nova table (user_id, token, expires_at, used)

---

## 📌 NOTAS IMPORTANTES

### Score de 85% — NÃO MOSTRAR PARA GP

O percentual nunca deve aparecer na interface para o GP. Apenas:
- "Pendente" (vermelho bold)
- "Incompleto" (vermelho bold)  
- "OK" (verde bold)

### Campos com Conflito — HIGHLIGHT

Quando há conflito detectado:
```
1. Campo fica com borda esquerda ambar (4px)
2. Label fica ambar com ⚠️ icon
3. Descrição do conflito aparece em small text
4. Campo readonly após n8n rodar
```

### n8n Deve Ser Inteligente

Não é apenas validação. Deve:
- ✅ Detectar incompatibilidades técnicas
- ✅ Sugerir correções
- ✅ Explicar por quê
- ✅ Score justo (não muito restritivo)

---

## 🎯 Timeline Recomendado

**Session 09**: 
- [ ] Questionário HTML atualizado
- [ ] n8n workflow básico (validações)
- [ ] Email templates

**Session 10**:
- [ ] Frontend updates (status colors, highlights)
- [ ] Backend processes (reset, first access, invite)
- [ ] Database schema updates

**Session 11+**:
- [ ] n8n inteligência avançada
- [ ] Testes E2E completos
- [ ] Production readiness

