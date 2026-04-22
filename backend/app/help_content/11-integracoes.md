# Integrações Externas

O GCA conversa com as ferramentas que seu time já usa. Em vez de reinventar
tracker de issues, scanner de segurança ou canal de notificação, o GCA
**consome** essas ferramentas e agrega governança sobre os dados delas.

Três integrações canônicas estão disponíveis:

| Tipo | Providers V1 | O que faz |
|---|---|---|
| **Issue Tracker** | Jira, Trello | Módulos aprovados viram issues automaticamente; status sincroniza via webhook |
| **Security Scanner** | Sonar, Snyk, gitleaks | Findings reais alimentam o pilar P7 do OCG |
| **Notifier** | Slack | Eventos do pipeline viram mensagem no canal do time |

Todas as três são **opcionais** — o GCA funciona 100% sem elas. Quando
configuradas, amplificam o valor sem mudar o fluxo canônico.

---

## 1. Issue Tracker Bridge (Jira / Trello)

### 1.1 Para que serve

Hoje o backlog do GCA vive separado do Jira/Trello do time. O comprador
pergunta *"onde aparece isso no meu Jira?"* e a resposta era *"não
aparece"*. Com a integração ligada:

1. Quando o GP aprova um módulo no GCA, uma issue é criada automaticamente
   no tracker configurado.
2. Mudanças de status na issue (via tracker) sincronizam de volta para o
   GCA via webhook.
3. A matriz de rastreabilidade do ERS referencia a issue externa.

### 1.2 Configurar

Abra **`/projects/:id/settings` → aba Integrações**. Escolha o provider
ativo (Jira ou Trello) e preencha:

**Jira:**
- **Base URL**: ex. `https://suaempresa.atlassian.net`
- **Project Key**: identificador do projeto no Jira (ex. `PROJ`)
- **Email Atlassian**: usuário técnico da integração
- **API Token**: gerado em https://id.atlassian.com/manage-profile/security/api-tokens
- **Webhook Secret** (opcional): gera um secret forte e configura no painel
  de webhooks do Jira apontando para
  `POST /api/v1/integrations/webhooks/issue-tracker/jira/{project_id}`

**Trello:**
- **Base URL**: `https://api.trello.com`
- **Board ID**: ID do board onde os cards serão criados
- **API Key**: https://trello.com/app-key
- **User Token**: gerado via link na mesma página
- **Webhook Secret** (opcional): idem Jira

Todas as credenciais são gravadas **encrypted** no vault do projeto (nunca
em plaintext). Você pode substituir ou remover a qualquer momento.

### 1.3 Status mapping customizado

Se seu fluxo de trabalho no Jira tem estados específicos (ex. *"Em análise
pelo jurídico"*), configure o mapping JSON na aba de settings apontando
para um dos cinco status canônicos do GCA:

```json
{
  "Em análise pelo jurídico": "review",
  "Aguardando compliance": "review"
}
```

Status canônicos do GCA: `todo`, `in_progress`, `review`, `done`,
`cancelled`.

---

## 2. Security Scanners (Sonar / Snyk / gitleaks)

### 2.1 Para que serve

Empresas de grande porte já investiram em Sonar/Snyk/Fortify/Checkmarx. O
GCA **não reimplementa SAST** — consome findings dessas ferramentas e
mapeia para o **pilar P7** do OCG.

Resultado prático: quando o CISO pergunta *"qual o risco de segurança
deste projeto?"*, a resposta vem com dados reais do scanner que sua
empresa já paga, traduzidos em score P7 do OCG + trilha de auditoria
SHA-256 + rastreabilidade ao requisito via matriz do ERS.

### 2.2 Scanners suportados

| Scanner | Modalidade | Credencial |
|---|---|---|
| **SonarQube / SonarCloud** | REST `/api/issues/search` | API Token |
| **Snyk** | REST `/rest/orgs/{org}/issues` | API Token |
| **gitleaks** | JSON report (cliente manda via API) ou local | Nenhuma (report) ou binário instalado |

### 2.3 Fórmula determinística de P7

Quando há findings configurados:

```
penalty = 25 × N_critical + 10 × N_high + 3 × N_medium + 1 × N_low
P7_score = clamp(0, 100, 100 - penalty)
```

Findings com status `accepted_risk` (aceitos pelo GP com justificativa
auditada) **não** contam no penalty.

Quando o projeto **não** tem scanner configurado, o P7 mantém a heurística
anterior — comportamento preservado.

### 2.4 Aceitar risco formalmente

GP pode marcar um finding como `accepted_risk` via endpoint/UI com
justificativa mínima obrigatória (10 caracteres). Ação fica na trilha de
auditoria SHA-256. Admin co-assina em V2.

---

## 3. Slack Notifier (uni-direcional)

### 3.1 Eventos canônicos

O GCA envia mensagem ao canal configurado quando os seguintes eventos
canônicos acontecem:

| Evento | Quando dispara |
|---|---|
| `MODULE_APPROVED` | GP aprova módulo no Gatekeeper |
| `OCG_CONSOLIDATED` | OCG passa por consolidação formal |
| `CODEGEN_COMPLETED` | Módulo gerado com sucesso |
| `ERS_REGENERATED` | `docs/ERS.md` regenerado e commitado |
| `SECURITY_FINDING_HIGH` | Novo finding critical/high detectado |
| `BACKUP_FAILED` | Backup automático falhou |

### 3.2 Configurar

Na aba Integrações do projeto:

- **Webhook URL**: gere em https://api.slack.com/apps → novo app → Incoming
  Webhooks → escolher canal destino
- **Canal** (opcional, só pra exibição): `#gca-events` ou similar
- **Eventos opt-in** (opcional): lista de eventos que o time quer receber.
  Sem configurar = recebe todos.
- **Modo link-only** (regulado): quando ativo, mensagem só tem link pro
  GCA; zero payload sensível trafega por Slack. Use em cliente BACEN, ANS,
  órgão público que não permite dado sensível em terceiros.

### 3.3 Uni-direcional em V1

Nesta versão mensagens **vão** do GCA pro Slack; reações/botões no Slack
**não voltam** pro GCA. ChatOps bi-direcional (aprovar módulo com emoji)
fica como roadmap futuro — exige SSO corporativo e revisão de superfície
de ataque.

---

## 4. O que o GCA não vai reimplementar

- ❌ SAST interno — use Sonar/Snyk/Fortify; GCA consome.
- ❌ Issue tracker interno — use Jira/Trello/Linear; GCA integra.
- ❌ Chat interno — use Slack/Teams; GCA envia.

**Filosofia canônica:** governança + orquestração + rastreabilidade são o
produto do GCA. Ferramentas commodity maduras ficam onde estão e entram no
GCA via adapter.

---

## 5. Novas integrações sob demanda

Linear, Asana, GitHub Issues, Monday, ClickUp, Microsoft Teams,
Mattermost, Discord — **todos cabem** no padrão adapter canônico do GCA.
Custo estimado por novo adapter: ~1.5-2 dias de desenvolvimento.

Entre em contato para discutir integração específica do seu stack.
