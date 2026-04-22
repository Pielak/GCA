# Solução de problemas

FAQs com diagnósticos práticos.

## Backend e infraestrutura

### Backend não sobe

Sintoma: `docker compose up -d` termina mas `gca-backend` fica reiniciando.

Diagnóstico:

```bash
docker logs gca-backend --tail 50
```

Causas comuns e soluções:

| Causa | Solução |
|---|---|
| `DATABASE_URL` ausente | Verificar `.env` e reiniciar com `docker compose up -d` |
| `JWT_SECRET` ou `VAULT_MASTER_KEY` ausentes | Gerar e adicionar ao `.env` |
| Migração pendente | `docker exec gca-backend alembic upgrade head` |
| Porta 8000 em uso | `lsof -i :8000` e liberar ou mudar o port mapping |
| Imagem Docker desatualizada | `docker compose pull && docker compose up -d` |

### Celery worker marca `unhealthy` mas responde a ping

Verifique se o worker processa tarefas de verdade:

```bash
docker exec gca-backend python -c "
from app.celery_app import celery_app
print(celery_app.send_task('app.celery_app.ping').get(timeout=10))
"
```

Se retornar `pong`, o worker está funcional. Se o healthcheck do Docker marca `unhealthy` mesmo assim, o container foi criado antes da versão atual do `docker-compose.yml` — rode:

```bash
docker compose up -d
```

Sem argumentos. Isso sincroniza a stack com as configurações atuais.

### Flower não responde em `localhost:5555`

O serviço Flower pode estar declarado no `docker-compose.yml` mas não subido. Força o up:

```bash
docker compose up -d celery-flower
```

Valide:

```bash
curl -fsS http://localhost:5555/ | head -5
```

### Backup não executa no horário configurado

Verifique o timezone:

```bash
docker exec gca-backend env | grep BACKUP_TIMEZONE
```

Se vazio ou inválido, o agendador cai em UTC. Ajuste `BACKUP_TIMEZONE` no `.env` (ex.: `America/Sao_Paulo`) e reinicie.

## Ingestão

### Documento preso em `processing`

Causa provável: o pipeline de análise foi interrompido (reload, crash) e a task sumiu.

Mitigações automáticas já presentes:

- **Watchdog no startup** — recupera documentos em `processing` há mais de 30 minutos, marca como `error` com mensagem clara.
- **ACK late na fila** — se o worker cai no meio da tarefa, a fila reenfileira.
- **Timeout com `asyncio.wait_for`** — análises passam 10 minutos no máximo; em timeout, o documento vai para `error` com mensagem explícita em vez de ficar pendurado.

Se algum documento persistir preso:

```bash
# Worker está ativo?
docker exec gca-backend python -c "
from app.celery_app import celery_app
print(celery_app.control.inspect(timeout=1).ping())
"

# Alguma tarefa pendente no broker?
docker exec gca-redis redis-cli -n 1 KEYS "celery*"

# Alguma tarefa na DLQ?
curl -H "Authorization: Bearer <admin-token>" http://localhost:8000/api/v1/admin/celery/dlq
```

Na UI, em `/projects/:id/ingestion`, clique em **"Reanalisar"** no documento — o sistema reseta o status e re-enfileira a tarefa.

### Documento quarentenado por PII que você sabe que não tem

O GCA detecta PII (CPF, CNPJ, cartão, telefone BR) com validações apropriadas:

- CPF, CNPJ, cartão — validados por mod-11 ou Luhn (não disparam em números aleatórios).
- Telefone BR — regex + contexto (não dispara em sequências numéricas como IDs ou timestamps).

Se ainda assim um falso-positivo quarentenar, em `/projects/:id/ingestion` → detalhe do documento → **"Liberar quarentena"**. O documento volta ao pipeline.

### PDF com formulário AcroForm não extrai campos

PDFs que passaram por "flatten" (Imprimir → PDF, algumas ferramentas de exportação) perdem a estrutura de formulário. O GCA rejeita esses PDFs com erro 422 e mensagem orientando a abrir no **Adobe Reader**, **Foxit** ou **Okular** e salvar com **Ctrl+S** (não "Salvar como..." nem "Imprimir → PDF") — isso preserva o AcroForm.

## OCG

### OCG preso em `pending_analysis` após questionário aprovado

O pipeline dos 8 agentes disparou mas algo no meio falhou. Vá em `/projects/:id/ingestion` → botão **"Reanalisar"**. Se persistir, como GP você pode regenerar o OCG do zero:

`/projects/:id/ocg` → **"Regenerar OCG"** (confirmação dupla — é destrutivo, perde o delta history).

### OCG em `BLOCKED` sem motivo óbvio

O Gatekeeper bloqueia quando:

- `P2 < 70` — compliance insuficiente.
- `P7 < 70` — segurança insuficiente.

Veja `/projects/:id/ocg` → `PILLAR_SCORES` para identificar qual pilar puxou para baixo.

Como desbloquear: ingerir documento que responda os gaps de compliance ou segurança, OU responder as perguntas do Arguidor com evidência.

### Rollback falhou com "Snapshot não disponível"

Só é possível fazer rollback para versões que tenham snapshot persistido no delta log. Versões muito antigas (pré-feature) podem não ter.

Alternativa: regenerar o OCG do questionário atual em `/projects/:id/ocg` → **"Regenerar OCG"**.

## Provedores de IA

### Erro 401 ou 403 do provedor

A chave está inválida ou expirou. Vá em:

- **Admin**: `/admin` → "Provedores de IA" → botão **"Testar"** no provedor → atualize a chave.
- **GP**: `/projects/:id/settings` → aba IA → **"Validar"** → atualize a chave do projeto.

### Erro 429 (rate limit) ou falha de conexão

O GCA tem fallback automático entre provedores configurados no projeto. Quando o provedor padrão falha (429, 5xx, timeout, 401, 403, DNS, SSL), o sistema tenta o próximo da cadeia — e você recebe uma notificação avisando qual fallback está ativo.

Se só há um provedor configurado no projeto, adicione um segundo em `/projects/:id/settings` → aba IA. O Ollama (local) é uma boa opção como rede de segurança para tarefas de baixa criticidade.

### "Provider do projeto não é criticidade alta suficiente"

Algumas operações (consolidação do OCG, decisões arquiteturais, compliance) exigem provedor classificado como **alta criticidade** (Anthropic, OpenAI, etc — não Ollama sozinho).

Configure um provider premium no projeto OU, se o Admin tiver um global de alta criticidade, operações globais (Admin) podem rodar pelo canal administrativo.

## CodeGen

### Scaffolder retornou `None` (linguagem não suportada)

O CodeGen caiu no fluxo LLM-only porque a linguagem do projeto (ex.: Python, Rust, Swift) não tem template determinístico no GCA.

- **Python** — ainda em LLM-only (FastAPI, Django, Flask vêm do LLM).
- **Outras** (Rust, Ruby, Swift, etc) — não suportadas; o código vem do LLM sem garantia de estrutura.

Se sua linguagem é uma das suportadas mas foi escrita de forma diferente (ex.: "Python3", "node"), confira `STACK.backend.language` em `/projects/:id/ocg`. Os aliases canônicos são:

- C++, cpp, cplusplus.
- C#, cs, .net, dotnet.
- Node.js, nodejs, node, typescript, javascript.
- Java, kotlin, go, php.

### Erro no `cmake` ao testar o scaffold C++

CMake 3.14 ou superior é obrigatório (FetchContent estável a partir dessa versão). Se você está rodando fora do Docker do scaffold:

```bash
cmake --version
# Se < 3.14, atualize
```

Se `-G Ninja` falhar porque ninja não está instalado:

```bash
apt install ninja-build
# ou remova -G Ninja do comando — cai em Makefile
```

### Falha de build C++ dentro do Docker

O Dockerfile gerado usa `gcc:13-bookworm` como stage de build. Em caso de erro, veja os logs:

```bash
docker build -t <target> . 2>&1 | tee build.log
```

Erros comuns:

- **Out of memory** — o build do GoogleTest via FetchContent consome memória. Docker Desktop com 2GB pode falhar; use 4GB+.
- **Download do GoogleTest falhou** — rede bloqueada. Configure proxy no Docker ou use vcpkg offline (V2, ainda não suportado).

## ERS Vivo (MVP 19)

### Botão "Regenerar ERS" aparece desabilitado

O projeto precisa ter **repositório Git conectado** em `/projects/:id/settings` → aba Repositório. O ERS é commitado como `docs/ERS.md` no repo do projeto via `git_service`; sem repo, não há destino possível.

Diagnóstico: abrir a aba Repositório e conferir se o toggle "Repositório configurado" está verde. Se não, seguir o fluxo de conexão (GitHub/GitLab/Bitbucket com PAT).

### ERS regenerado mas `docs/ERS.md` não apareceu no repo

1. Confirme que o commit foi feito: `GET /api/v1/projects/:id/audit` filtrando por `event_type=LIVEDOCS_UPDATED` e `details.doc_type=ers`. O `details.commit_sha` deve estar preenchido.
2. Se o commit_sha aparece mas o arquivo não: o PAT pode ter expirado entre testar a config e disparar o regen. Rote o token em `/settings` → Repositório e dispare novamente.

### Seção 1.3 (Glossário) vazia no ERS regenerado

O glossário tem aprovação obrigatória pelo GP (decisão canônica MVP 19). Termos extraídos automaticamente ficam em status `candidate` até o GP aprovar via `/projects/:id/docs` → aba Glossário. Se nada foi aprovado, a seção mostra placeholder "Nenhum termo aprovado ainda" — **não é bug**.

## Gestão de equipe

### Convidado não recebeu a senha provisória no email

Fluxo canônico (RF-001) do convite de equipe:

1. GP preenche email + papel em `/projects/:id/team` → **Enviar Convite**.
2. Se o email **nunca** existiu no GCA, o sistema gera senha provisória canônica (10 caracteres: 1 maiúscula + 1 dígito + 1 especial) e grava o hash no User.
3. Email é enviado com: link para aceitar + **senha provisória em texto claro** no corpo.
4. Usuário clica no link → vai para `/p/:slug` → faz login com email + senha provisória.
5. Sistema detecta `first_access_completed=false` → dispara tela de troca obrigatória de senha.
6. Usuário define senha pessoal → `accepted_at` e `joined_at` são marcados automaticamente → entra no projeto.

Se o email do convite **não** incluiu a senha provisória: regressão histórica foi corrigida — todos os convites emitidos após o fix incluem a senha corretamente. Para convite anterior órfão, a opção canônica é **revogar e reenviar** o convite pelo GP.

### Usuário convidado aparece como membro ativo mesmo sem aceitar convite

Estado esperado no banco (ProjectMember):

- **Convite pendente:** `is_active = true`, `invite_token IS NOT NULL`, `joined_at IS NULL`.
- **Membro integrado:** `is_active = true`, `joined_at IS NOT NULL` (preenchido ao aceitar o convite ou, no caso de GP criado por aprovação direta de projeto, ao ser criado pelo `gp_management_service`).

Regra canônica em `project_team_service.is_active_integrated_member()`: membro integrado exige `is_active AND joined_at IS NOT NULL`. O campo `accepted_at` sozinho não basta — o caminho de aprovação de projeto cria GP com `joined_at` preenchido mas `accepted_at NULL`.

Se a tela de Equipe mostrar o mesmo usuário em **Convites Pendentes** e **Membros da Equipe** simultaneamente: era bug conhecido do endpoint `GET /projects/:id/members` que filtrava apenas `is_active=true` sem checar `joined_at`. Corrigido — endpoint agora alinha com a regra canônica.

Como confirmar o estado real:

```sql
SELECT pm.is_active, pm.joined_at, pm.invited_at, pm.accepted_at, pm.invite_token IS NOT NULL AS tem_token
FROM project_members pm
JOIN users u ON u.id = pm.user_id
WHERE u.email = 'pessoa@empresa.com'
  AND pm.project_id = '...';
```

## Integrações externas (MVP 20)

### Webhook do Jira/Trello retorna `{"accepted": false, "reason": "invalid_signature_or_irrelevant"}`

Duas causas possíveis:

1. **Signing secret divergente** — o secret configurado no Jira/Trello tem que bater com o gravado no vault do projeto (`secret_key='jira:webhook_secret'` ou `trello:webhook_secret`). Rote o secret em ambos lados e reconfigure o webhook.
2. **Evento irrelevante** — Jira dispara eventos como `jira:user_created` que o parser filtra silenciosamente. `jira:issue_created`, `issue_updated`, `issue_deleted` são os três relevantes. Trello: `createCard`, `updateCard`, `deleteCard`, `commentCard`.

### Módulo aprovado mas nenhuma issue foi criada no Jira

Fluxo é best-effort — a falha na criação **não** bloqueia a aprovação (decisão canônica). Verifique:

1. `GET /projects/:id/integrations/issue-tracker` retorna `enabled=true`, `active_provider='jira'` e `has_credentials.jira.api_token=true`? Se não, falta config.
2. Logs do backend: `docker logs gca-backend | grep integrations.issue_creation_failed`. O erro real aparece no `details.error`.
3. Causa comum: `default_project_key` errado (ex: "PROJ-5" em vez de "PROJ"), ou o usuário do `api_token` não tem permissão de criar issue naquele projeto Jira.

### P7 do OCG não recalcula mesmo com findings no Sonar

Cenário esperado: P7 só consome findings reais **quando o scanner está configurado no projeto**. Sem config, o P7 mantém a heurística anterior (decisão #7 do contrato MVP 20).

Se o scanner está configurado e ainda assim P7 parece estático:

1. Confirme findings em `GET /projects/:id/security/findings` — se vazio, o sync ainda não rodou.
2. Dispare sync manual via endpoint admin ou re-execute o scanner do cliente e reenvie os findings.
3. Se findings aparecem mas P7 continua vindo do LLM, pode ser cache do OCG — recarregue a aba Gatekeeper.

### Credencial de integração desaparece após reinício

Credenciais vão pro vault encrypted via `pgcrypto`. O problema canônico é:

- **GCA_MASTER_KEY mudou** entre runs — o `pgp_sym_decrypt` retorna vazio quando a master key é diferente da usada para encriptar. Solução: manter a master key em `.env` imutável; se precisar rotacionar, re-configurar todas as credenciais do vault em um único ciclo coordenado.

### Notificação Slack não chega

1. **`enabled=false`** — confira em `/settings` → Integrações → Slack.
2. **Event não está em `opted_in_events`** — se a lista foi configurada explicitamente, só os eventos listados chegam. Lista vazia ou não configurada = opt-in em todos (default).
3. **Modo `link_only_mode=true` ativo** — mensagem aparece mas sem payload de contexto. Se o time esperava ver os `fields` do Block Kit, desabilite o modo link-only (cliente não-regulado).
4. **Webhook URL inválido / revogado** — Slack retorna 404 ou 400 não-retryable. Gere novo Incoming Webhook e atualize via `PUT /integrations/issue-tracker/credentials/slack/webhook_url`.

## Busca no help

### Busca retorna lista vazia

Verifique se o termo está escrito como aparece no conteúdo. O sistema é case-insensitive e ignora acentos (ex.: `documentacao` encontra `documentação`), mas não corrige erros de digitação.

Termos que têm muitos hits (teste primeiro com eles): OCG, RBAC, CodeGen, Gatekeeper, pipeline, DDL, ingestão.

### Renderer mostra markdown como texto puro

O frontend precisa ter sido buildado e reiniciado depois de upgrade:

```bash
docker exec gca-frontend npm run build
docker compose restart gca-frontend
```

Depois, **hard refresh** no navegador (Ctrl+Shift+R ou Cmd+Shift+R) para bypassar cache.

## Contato / suporte

Para problemas não cobertos:

1. **Incidente técnico no projeto** — `/projects/:id/incidents` → **"Novo ticket"** com severidade + descrição + anexos.
2. **Equipe de Sustentação da instância** — `/admin/support` (se você for Admin).
3. **Auditoria** — `/admin/audit` filtrando pelo tipo de evento relacionado (ex.: `DOCUMENT_QUARANTINED` para encontrar quarentenas recentes).

## Ver também

- [Observabilidade](?section=09-observabilidade) — endpoints de diagnóstico.
- [Instalação & primeiro setup](?section=02-instalacao) — validação pós-install.
- [Área Administrativa](?section=06-admin) — ferramentas de diagnóstico.
