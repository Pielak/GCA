# RBAC e papéis

O GCA opera com **5 papéis canônicos** (contrato §4, imutável): Admin, GP, Dev, Tester, QA. Papéis antigos (tech_lead, dev_senior, dev_pleno, compliance, stakeholder, viewer) foram removidos em MVP 1 (DT-001); documentos históricos que citem esses papéis não são contrato de implementação.

## Os 5 papéis canônicos

### Admin (instância)

- Configura a instância: provedores de IA, SMTP, backup, thresholds dos pilares, pesos.
- **Não atua operacionalmente em projetos**. A analogia: Admin está para a instância assim como GP está para o projeto.
- Convida e bloqueia usuários, aprova/rejeita requisições externas de projeto, inspeciona auditoria global, vê métricas agregadas.
- Flag cross-instância `is_support` (Sustentação) é herdada automaticamente por Admin. UI de Sustentação **não** promove Support a Admin.
- Guard dura: não é possível desativar/excluir o **último Admin ativo** (MVP 11 Fase 11.3).

### GP (projeto) — **soberano do projeto**

Emenda §4.1 de 2026-04-19: o GP tem **todos os acessos** dentro do projeto, incluindo CodeGen, pipeline de testes e demais fluxos. A separação operacional com Dev/Tester/QA é de dia-a-dia, não de permissão.

- Conduz o projeto do questionário até o release bundle.
- Aprova/rejeita OCG, ingestões, análises do Arguidor, scaffolds de código.
- Convida membros (Dev, Tester, QA, outro GP) com papel específico.
- Pode **transferir soberania** para outro membro ativo (MVP 11 Fase 11.2 — endpoint `POST /projects/{id}/transfer-gp/{target}`).
- Pode **convidar outro GP** do mesmo projeto (MVP 11 Fase 11.1 — co-gestão).
- Configura provedor IA do projeto separado das chaves globais do Admin.

### Dev

- Implementa, gera código via CodeGen, executa correções.
- **Não aprova módulos nem OCG** — aprovação é GP ou Admin via override.
- Interage com repositório Git do projeto (PAT do projeto configurado em Configurações).

### Tester

- Edita, executa e registra testes.
- Aprova/rejeita specs de teste unitário/integração/E2E.
- **Não revisa por QA** — revisão formal é papel do QA.

### QA

- Revisa e aprova execução de testes.
- **Não edita conteúdo de teste** — edição é do Tester.
- Atua no gate `qa:approve` que libera Release Bundle (MVP 4).

## Matriz resumida de permissões

| Ação | Admin | GP | Dev | Tester | QA |
|---|---|---|---|---|---|
| Criar/aprovar/arquivar projeto | ✅ | ⚠️ dentro do próprio | ❌ | ❌ | ❌ |
| Configurar IA da instância | ✅ | ❌ | ❌ | ❌ | ❌ |
| Configurar IA do projeto | ⚠️ override | ✅ | ❌ | ❌ | ❌ |
| Convidar membros | ✅ (qualquer) | ✅ (no projeto) | ❌ | ❌ | ❌ |
| Aprovar OCG | ✅ | ✅ | ❌ | ❌ | ❌ |
| Ingerir documentos | ✅ | ✅ | ✅ | ❌ | ❌ |
| Rodar CodeGen | ✅ | ✅ | ✅ | ❌ | ❌ |
| Editar spec de teste | ✅ | ✅ | ⚠️ | ✅ | ❌ |
| Executar teste | ✅ | ✅ | ✅ | ✅ | ❌ |
| Aprovar execução (`qa:approve`) | ✅ | ✅ | ❌ | ❌ | ✅ |
| Ver auditoria global | ✅ | ❌ | ❌ | ❌ | ❌ |
| Ver auditoria do projeto | ✅ | ✅ | ✅ | ✅ | ✅ |

Enforcement técnico: `require_action('<permission>')` como FastAPI dependency em cada endpoint sensível. RBAC pulverizado por ação, não por papel.

## Fluxos canônicos do RBAC

### Convite de Admin

1. Admin existente → `/admin/users` → "Convidar Administrador".
2. Backend cria `users` inativo + token de aceite.
3. Email com link `/accept-invitation?token=...`.
4. Convidado define senha + aceita → `is_admin=true` + `is_active=true`.
5. Emite `ROLE_GRANTED` com `phase=admin_promoted` em `audit_log_global`.

### Convite de membro para projeto

1. GP do projeto → `/projects/:id/team` → "Convidar Membro".
2. Escolhe papel (Dev/Tester/QA/GP) + email.
3. Backend cria `project_members` inativo + invitation token.
4. Email com link `/accept-invitation?token=...` + slug do projeto.
5. Convidado aceita → `accepted_at` + `joined_at` preenchidos.
6. Emite `ROLE_GRANTED` com `phase=invited`, depois `phase=accepted`.

### Transferência de soberania GP → GP

1. GP atual → `/projects/:id/team` → aba "Transferir soberania".
2. Seleciona membro ativo + aceito do projeto.
3. Confirmação dupla (modal).
4. Backend em transação: chamador vira `dev`, alvo vira `gp`. Ambos `ROLE_TRANSFERRED` com mesmo `correlation_id` (`extra.direction ∈ {outgoing, incoming}`).
5. Pré-condições binárias (qualquer falha → 403):
   - Chamador é GP ativo do projeto.
   - Alvo é membro ativo e aceito.
   - Alvo não é GP já.
   - Alvo ≠ chamador.

### Revogação/bloqueio de Admin

- `lock_user(user_id)` com `actor_id` — bloqueia o user.
- Guard canônico `guard_last_admin_on_action` (MVP 11.3) bloqueia se target é admin ativo e restariam 0 ativos após a ação. Impossível "se trancar para fora".
- Mesmo guard aplicado em `delete_user` e `set_admin_flag(False)`.

## Compartimentalização §2.2

Toda query envolvendo dado de projeto **deve** incluir `project_id` no predicado. Nenhum canal lateral (vault, storage, cache, logs, notificações, git, n8n, SMTP) cruza entre projetos sem autorização explícita.

Exemplos de regras duras decorrentes:

- Repositório Git compartilhado entre projetos é **bloqueado** no backend (MVP 2 DT-026): a tentativa de conectar URL normalizada já vinculada rejeita com mensagem explícita.
- Chave global de avaliação (Admin) ≠ chave do projeto (GP). Roteador canônico `AIKeyResolver` separa as camadas.
- Notificações por email seguem o escopo: admin só recebe avisos do próprio projeto ou da instância; não recebe eventos de projetos que não governa.

## Auditoria de eventos de papel (MVP 11.4)

Todo evento de papel emite uma das 3 categorias em `audit_log_global`:

- `ROLE_GRANTED` — convite emitido, convite aceito, promoção admin, transferência recebida.
- `ROLE_REVOKED` — convite revogado, rebaixamento admin, desativação de user, transferência emitida.
- `ROLE_TRANSFERRED` — reservado ao fluxo de transferência GP → GP.

Payload canônico: `{ actor_id, target_user_id, project_id (nullable na instância), old_role, new_role, phase, timestamp, extra? }`.

Consulta: `/admin/audit` filtro por tipo de evento.

## Ver também

- [Instalação & setup](?section=02-instalacao) — como criar o primeiro Admin.
- [Área Administrativa](?section=06-admin) — tour completo do que Admin faz.
- [Área de Gestão de Projeto](?section=07-gp) — tour completo do que GP faz.
