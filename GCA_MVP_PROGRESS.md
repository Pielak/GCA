# GCA_MVP_PROGRESS.md

Versão: 1.1  
Data-base: 2026-04-17  
Status: **controle de avanço por fase**

---

## 1. Fase atual

### MVP ativo
**MVP 1 — Base operacional e saneamento do núcleo**

### Objetivo do momento
Estabilizar a base já existente do GCA, eliminar conflitos de contrato/RBAC/escopo e impedir que novas features agravem a dívida técnica antes da evolução para os próximos MVPs.

### Princípio desta fase
Nesta fase, o trabalho prioritário é:
1. diagnosticar;
2. classificar dívida;
3. corrigir blockers e criticals;
4. revalidar a base;
5. só então considerar avanço.

---

## 2. Escopo da fase atual

### Em escopo agora
- autenticação;
- RBAC canônico de 5 papéis;
- cadastro/aprovação de projetos;
- questionário;
- OCG básico persistido;
- Gatekeeper básico;
- auditoria mínima;
- configuração básica de provedor de IA;
- política de adequação e roteamento híbrido de IA;
- saneamento de documentação operacional do núcleo;
- saneamento de telas/rotas/componentes que conflitem com o RBAC canônico.

### Fora de escopo agora
- expansão de papéis;
- marketplace;
- billing avançado;
- auto-upgrade avançado;
- hardening completo de produção;
- Release Bundle completo;
- evolução ampla de Documentação Viva;
- expansão livre de módulos apenas porque já aparecem em documentos históricos.

---

## 3. Dívida aberta conhecida

### 3.1 Blocker / Critical

| ID | Severidade | Tema | Descrição | Origem | Status |
|---|---|---|---|---|---|
| DT-001 | Critical | RBAC | Conflito entre documentação histórica com 7 papéis e contrato canônico com 5 papéis. | Docs históricos vs contrato | **Quitada 2026-04-17 (backend)** — ver §4 |
| DT-002 | Critical | UI/Admin | Há análise apontando que a aba de usuários/admin está modelada com RBAC global ampliado e lista papéis além do recorte canônico. | Análise completa | Aberto |
| DT-003 | Critical | Contrato de produto | Há tensão entre textos que sugerem plataforma ampla pronta e o recorte real que ainda exige saneamento da base. | Docs / README / manual | Aberto |
| DT-004 | Critical | Segurança operacional | PAT de Git ainda aparece documentado em texto plano / criptografia pendente. | Tutorial / requisitos / roadmap | Aberto |
| DT-005 | Critical | Governança de IA | Falta consolidar regra canônica para seleção de provedor/modelo por objetivo do cliente final, evitando default rígido enganoso. | Requisitos / contrato | Aberto |

### 3.2 Major

| ID | Severidade | Tema | Descrição | Origem | Status |
|---|---|---|---|---|---|
| DT-006 | Major | Fases vs realidade | Há materiais descrevendo pipeline completo com módulos avançados como se estivessem igualmente maduros. | Manual / tutorial / análise | Aberto |
| DT-007 | Major | Placeholders / continuidade | Há placeholders de telas/módulos previstos que não devem ser promovidos automaticamente a entregas da fase atual. | TASK_GCA_MASTER | Aberto |
| DT-008 | Major | Consistência documental | Há discrepâncias entre documentos sobre readiness, testes e maturidade operacional. | Changelog / docs / task | Aberto |
| DT-009 | Major | Roteamento híbrido | Falta explicitar em código e docs ativas que tarefas menores podem usar modelo local/Ollama e decisões críticas exigem modelo premium. | Contrato / operação | Aberto |

### 3.3 Minor

| ID | Severidade | Tema | Descrição | Origem | Status |
|---|---|---|---|---|---|
| DT-010 | Minor | Terminologia | Uso inconsistente de termos como tenant, projeto, instância e cliente. | Docs históricos | Aberto |
| DT-011 | Minor | Narrativa de produto | Parte da documentação promocional está mais madura que o contrato técnico real. | README / manual | Aberto |

---

## 4. Dívida quitada

| ID | Data | Item quitado | Arquivos/módulos | Evidência |
|---|---|---|---|---|
| DT-001 (parcial — backend) | 2026-04-17 | RBAC reduzido aos 5 papéis canônicos no backend: `admin_viewer` (virtual) + `gp` + `dev` + `tester` + `qa`. Papéis históricos (tech_lead, dev_senior, dev_pleno, compliance, stakeholder, viewer) removidos. GP perdeu `code:write/review/execute/commit` (contrato §4.1 — GP não escreve código); QA ganhou `security:review` e `compliance:validate`. Comentários dos campos `role` em `models/base.py` atualizados. | `backend/app/core/permissions.py`, `backend/app/models/base.py`, `backend/tests/test_permissions.py`, `backend/tests/test_rbac_integration.py`, `backend/tests/test_multi_roles.py`, `backend/tests/test_project_setup.py` | 81/81 testes backend + 44/44 unit passando. DB com 3 `gp` preservados sem migration. |

> Parte pendente de DT-001: papéis nos `ROLE_LABELS` do frontend (`Sidebar.tsx`, `AdminUsersPage.tsx`) ainda listam 11 entradas — alinhamento frontend é escopo da DT-002.

> Regra: toda quitação relevante deve ser adicionada aqui com data, módulos afetados e evidência.

---

## 5. Gaps e conflitos que precisam ser reconhecidos pelo Claude

### 5.1 Papéis
- Backend/contrato caminham para 5 papéis canônicos.
- Manual, tutorial e análises ainda carregam 7+ papéis em vários pontos.
- Claude não pode usar esses papéis históricos para expandir o sistema.

### 5.2 Produto
- O produto canônico é instalável por cliente.
- Documentos históricos podem sugerir plataforma mais ampla ou linguagem de multi-tenant central.
- Claude deve manter o modelo: **instância por cliente + isolamento por projeto**.

### 5.3 IA
- O sistema suporta múltiplos provedores/modelos em documentação e serviços.
- Claude deve tratar a IA como componente configurável por objetivo do cliente.
- O sistema pode operar em modo híbrido:
  - tarefas auxiliares e repetitivas com modelo local/Ollama;
  - consolidação e decisão crítica com modelo premium.
- Não pode assumir um único provedor como verdade universal do produto.

---

## 6. Gate de avanço

A fase atual **não pode avançar** se qualquer um destes itens estiver aberto:
- blocker aberto;
- critical aberto;
- contradição estrutural entre contrato e código do núcleo;
- RBAC ambíguo;
- teste quebrado da fase;
- alteração sem migração/compatibilidade onde ela seria obrigatória;
- feature nova adicionada para “contornar” dívida não resolvida.

### Situação atual do gate
**NÃO AVANÇAR**

### Motivo
A base ainda possui conflitos canônicos de RBAC, produto, governança de IA e segurança operacional que tornam perigoso avançar sem saneamento mínimo.

---

## 7. Ordem recomendada de saneamento

1. **RBAC canônico**
   - congelar 5 papéis em backend, frontend e docs ativas;
   - marcar documentos históricos como históricos.

2. **Contrato de produto**
   - consolidar instalação por cliente + isolamento por projeto;
   - eliminar leituras ambíguas de SaaS compartilhado.

3. **Admin / gestão de usuários**
   - alinhar páginas e fluxos ao RBAC canônico;
   - remover dependência implícita de papéis históricos.

4. **Política de IA**
   - introduzir recomendação por objetivo do cliente;
   - explicitar roteamento híbrido por criticidade;
   - manter provedores/modelos configuráveis.

5. **Segurança operacional do núcleo**
   - preparar trilha de correção para PAT/segredos;
   - evitar expansão de módulos antes disso.

---

## 8. Procedimento obrigatório para Claude

Antes de qualquer mudança:
1. ler `GCA_CANONICAL_CONTRACT.md`;
2. ler este arquivo;
3. identificar se a solicitação pertence ao MVP 1;
4. verificar blockers/criticals;
5. se houver impedimento, corrigir só o necessário;
6. atualizar este arquivo ao concluir a correção.

### Resposta mínima esperada do Claude por ciclo
- fase avaliada;
- dívida encontrada;
- item corrigido;
- item pendente;
- status do gate: pode avançar / não pode avançar.

---

## 9. Próximo marco de saída do MVP 1

O MVP 1 poderá ser considerado apto a encerrar quando:
- RBAC de 5 papéis estiver coerente;
- telas e fluxos do núcleo respeitarem esse RBAC;
- política de IA configurável por cliente estiver explicitada;
- roteamento híbrido de IA estiver definido para tarefas menores vs decisões críticas;
- conflitos documentais críticos estiverem neutralizados;
- núcleo auth/projeto/questionário/OCG/Gatekeeper básico estiver estável;
- gate de avanço mudar para **PODE AVANÇAR** com justificativa registrada.
