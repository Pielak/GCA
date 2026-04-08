# 🔧 Guia de Setup do Admin - GCA

## Visão Geral

Este guia fornece ao Admin do GCA as instruções passo-a-passo para obter e configurar todas as credenciais necessárias **na sequência correta**. O GCA não pode funcionar sem SMTP, GitHub não pode ser útil sem IA, e N8N só é necessário depois que você tem código sendo gerado.

---

## 📋 Sequência de Configuração (Ordem Importante)

1. **SMTP** - Comunicação (envio de emails com credenciais)
2. **GitHub** - Versionamento (sincronizar código gerado)
3. **IA Providers** - Geração de código (Claude, GPT-4, Grok, DeepSeek)
4. **N8N** - Recomendações (web scraping de tecnologias)
5. **Database** - Infraestrutura (armazenar dados dos tenants)

---

## 1️⃣ SMTP Configuration (PRIMEIRO)

**O que é?** SMTP é o protocolo para envio de emails. Sem SMTP, o Admin não consegue enviar credenciais aos GPs e os GPs não conseguem convidar membros da equipe.

**Por que é PRIMEIRO?** Porque é essencial para qualquer comunicação do sistema.

### Obter Credenciais

#### Opção A: Gmail (Recomendado para início)

1. Acesse: https://myaccount.google.com
2. Vá em **Security** (Segurança)
3. Ative **2-Factor Authentication** (se não estiver ativo)
4. Em **App passwords**, selecione:
   - App: `Mail`
   - Device: `Windows Computer` (ou seu dispositivo)
5. Google gera uma **senha de aplicativo** (16 caracteres)
6. Copie a senha e salve em local seguro

```
SMTP_SERVER: smtp.gmail.com
SMTP_PORT: 587 (TLS) ou 465 (SSL)
SMTP_USER: seu-email@gmail.com
SMTP_PASSWORD: xxxx xxxx xxxx xxxx (16 caracteres gerado pelo Google)
SMTP_USE_TLS: true
```

#### Opção B: Seu próprio servidor SMTP corporativo

Se sua empresa tem um servidor SMTP (Microsoft Exchange, Postfix, etc):

```
SMTP_SERVER: mail.sua-empresa.com
SMTP_PORT: 587 (consultar com TI)
SMTP_USER: seu-usuario@empresa.com
SMTP_PASSWORD: sua-senha
SMTP_USE_TLS: true ou false (consultar com TI)
```

### Validar

No Dashboard, clique em **"Enviar Email de Teste"**. Um email será enviado para sua caixa de entrada confirmando que SMTP está funcionando.

**Resultado esperado:**
```
✓ Email de teste enviado com sucesso para seu-email@gmail.com
```

---

## 2️⃣ GitHub Integration (SEGUNDO)

**O que é?** GitHub Personal Access Token (PAT) permite que o GCA crie branches, commits e pull requests automaticamente no seu repositório.

**Por que é SEGUNDO?** Depois que o GP tiver acesso ao sistema (via SMTP), ele precisa de um lugar para sincronizar o código gerado. GitHub é esse lugar.

### Obter Personal Access Token (PAT)

1. Acesse: https://github.com/settings/tokens
2. Clique em **Generate new token** → **Generate new token (classic)**
3. Preencha:
   - **Note**: `GCA - Automated Code Deployment` (para rastrear qual token é qual)
   - **Expiration**: `90 days` (recomendado para segurança)
4. Marque as **Scopes** (permissões):
   - ✅ `repo` (acesso completo a repositórios)
   - ✅ `user` (ler informações de usuário)
5. Clique em **Generate token**
6. **Copie e salve em local MUITO SEGURO** (aparece apenas uma vez)

```
GITHUB_PAT: ghp_xxxxxxxxxxxxx
GITHUB_USER: seu-usuario
```

### Validar

No Dashboard, clique em **"Validar GitHub"**. O sistema tentará:
1. Autenticar com o token
2. Listar seus repositórios
3. Exibir seu username

**Resultado esperado:**
```
✓ GitHub validado com sucesso
✓ Usuário: seu-usuario
✓ Repositórios encontrados: 5
```

---

## 3️⃣ IA Providers (TERCEIRO)

**O que é?** O GCA suporta múltiplos provedores de IA para geração de código. Você pode usar 1, 2, 3 ou todos os 4.

**Por que é TERCEIRO?** Com SMTP (para comunicação) e GitHub (para sincronizar), agora você precisa de IA para realmente gerar código.

**Recomendação:** Comece com **Anthropic Claude** (melhor custo-benefício). Depois adicione outros conforme necessário.

### Opção 1: Anthropic Claude (Recomendado)

**Preço:** $0.003 entrada / $0.015 saída por 1K tokens (mais barato)

1. Acesse: https://console.anthropic.com
2. Crie conta (ou faça login)
3. Vá em **API Keys**
4. Clique em **Create key**
5. Copie a chave

```
ANTHROPIC_API_KEY: sk-ant-xxxxxxxxxxxxx
MODEL: claude-opus-4-1 (ou versão mais recente)
```

### Opção 2: OpenAI GPT-4 (Opcional)

**Preço:** $0.005 entrada / $0.015 saída por 1K tokens

1. Acesse: https://platform.openai.com
2. Vá em **API Keys**
3. Clique em **Create new secret key**
4. Copie

```
OPENAI_API_KEY: sk-xxxxxxxxxxxxx
MODEL: gpt-4-turbo-preview
```

### Opção 3: Grok (Opcional)

**Preço:** $0.002 entrada / $0.010 saída por 1K tokens

1. Acesse: https://console.x.ai
2. Crie conta
3. Gere API Key
4. Copie

```
GROK_API_KEY: xxxxxxxxxxxxx
```

### Opção 4: DeepSeek (Opcional - Mais barato)

**Preço:** $0.0005 entrada / $0.002 saída por 1K tokens (MAIS BARATO)

1. Acesse: https://platform.deepseek.com
2. Crie conta
3. Vá em **API Keys**
4. Gere chave
5. Copie

```
DEEPSEEK_API_KEY: sk-xxxxxxxxxxxxx
```

### Validar

No Dashboard, clique em **"Test [Provider]"** para cada provedor que configurou. O sistema:
1. Tentará fazer uma chamada simples de geração
2. Confirmará se a chave é válida
3. Exibirá o tempo de resposta

**Resultado esperado:**
```
✓ Anthropic Claude validado com sucesso
✓ Tempo de resposta: 1.2s
✓ Modelo: claude-opus-4-1
```

---

## 4️⃣ N8N Integration (QUARTO)

**O que é?** N8N é um workflow automation tool que faz web scraping de tecnologias para gerar recomendações de stack automáticas.

**Por que é QUARTO?** Seu objetivo é sugerir tecnologias baseadas na linguagem escolhida (ex: Python → FastAPI, SQLAlchemy, PostgreSQL, Celery). Só faz sentido depois que você tem geração de código funcionando.

### Pré-requisito

- Servidor N8N já deve estar rodando (N8N Cloud, self-hosted, Docker, etc)

### Obter Credenciais

#### Opção A: N8N Cloud (Recomendado para início)

1. Acesse: https://app.n8n.cloud
2. Faça login ou crie conta
3. Vá em **Settings** → **API** (ou "Integrations")
4. Gere uma **API Key**
5. Copie o valor

```
N8N_API_KEY: n8n_xxxxxxxxxxxxx
N8N_SERVER_URL: https://app.n8n.cloud
```

#### Opção B: N8N Self-Hosted

1. Acesse seu servidor N8N: `http://seu-servidor-n8n:5678`
2. Vá em **Settings** → **API**
3. Copie a **API Key**

```
N8N_API_KEY: n8n_xxxxxxxxxxxxx
N8N_SERVER_URL: http://seu-servidor-n8n:5678
```

### Validar

No Dashboard, clique em **"Test N8N Connection"**. O sistema tentará:
1. Conectar ao servidor N8N
2. Listar workflows disponíveis
3. Confirmar que APIs de web scraping estão prontas

**Resultado esperado:**
```
✓ N8N conectado com sucesso
✓ Workflows disponíveis: 5
✓ Web scraping pronto para Python, Java, Node.js, Go, Rust
```

---

## 5️⃣ Database Configuration (QUINTO/ÚLTIMO)

**O que é?** PostgreSQL é o banco de dados onde o GCA armazena todos os dados dos tenants em schemas isolados (multi-tenant).

**Por que é ÚLTIMO?** É a infraestrutura que suporta tudo. Você já deve ter PostgreSQL instalado. Esta é uma validação final de que tudo está conectado.

### Pré-requisito

PostgreSQL deve estar instalado e rodando:

```bash
# Verificar se PostgreSQL está rodando
psql -U postgres -c "SELECT version();"
```

### Credenciais

```
DATABASE_URL: postgresql://user:password@localhost:5432/gca
DATABASE_USER: postgres (ou seu usuário)
DATABASE_PASSWORD: sua-senha
DATABASE_HOST: localhost (ou IP do servidor)
DATABASE_PORT: 5432
DATABASE_NAME: gca
```

### Validar

No Dashboard, clique em **"Test Connection"**. O sistema:
1. Tentará conectar ao banco
2. Criará as tabelas iniciais (se não existirem)
3. Confirmará que schema multi-tenant está pronto

**Resultado esperado:**
```
✓ PostgreSQL conectado com sucesso
✓ Database: gca
✓ Tabelas inicializadas
✓ Multi-tenant schema pronto
```

---

## 📅 Cronograma Recomendado

### Dia 1: Planejamento
- [ ] Definir qual SMTP usar (Gmail ou corporativo?)
- [ ] Verificar se já tem conta no GitHub
- [ ] Decidir qual(is) IA provider(s) usar
- [ ] Confirmar N8N disponível
- [ ] Confirmar PostgreSQL instalado

### Dia 2: Geração de Credenciais
- [ ] SMTP: Gerar App Password (Gmail) ou pedir para TI
- [ ] GitHub: Gerar Personal Access Token
- [ ] IA Providers: Gerar todas as API Keys desejadas
- [ ] N8N: Gerar API Key
- [ ] Database: Confirmar credenciais PostgreSQL

### Dia 3: Configuração no GCA
- [ ] Abrir Admin Setup Dashboard
- [ ] Inserir SMTP credentials → Test
- [ ] Inserir GitHub PAT → Test
- [ ] Inserir IA Provider Keys → Test cada um
- [ ] Inserir N8N credentials → Test
- [ ] Inserir Database credentials → Test

### Dia 4: Validação Final
- [ ] ✅ GCA está pronto
- [ ] Prosseguir para criar Tenant fictício

---

## 🔐 Segurança & Boas Práticas

### ⚠️ NUNCA faça isso:

- ❌ Commit API Keys no Git
- ❌ Deixar senhas em arquivos .txt
- ❌ Compartilhar credenciais por email ou Slack
- ❌ Usar mesma senha para múltiplos serviços
- ❌ Deixar credenciais em logs

### ✅ SEMPRE faça isso:

- ✅ Use `.env` local (nunca commitar .env)
- ✅ Use vault/secrets manager em produção
- ✅ Rotação de credenciais a cada 90 dias
- ✅ API Keys diferentes por serviço
- ✅ Audit logs de quem acessou quais credenciais
- ✅ Revoke tokens antigos quando mudar

### Rotação de Credenciais (Recomendado)

| Credencial | Frequência |
|-----------|-----------|
| SMTP Password | 90 dias |
| GitHub PAT | 90 dias |
| IA Provider Keys | 90 dias |
| N8N API Key | 90 dias |
| Database Password | 180 dias |

---

## 🐛 Troubleshooting

### SMTP não está enviando email

**Símbolo:** Email não chega
**Causas comuns:**
- Gmail App Password não foi gerado (falta 2FA)
- Credenciais estão erradas
- Port 587 bloqueada no firewall

**Solução:**
```bash
# Testar conexão SMTP manualmente
telnet smtp.gmail.com 587

# Se conectar, a porta está aberta
# Se não conectar, há problema de firewall
```

---

### GitHub PAT não está funcionando

**Símbolo:** "Invalid token" ou "Unauthorized"
**Causas comuns:**
- Token expirou
- Token não tem scopes `repo` e `user`
- Token foi revogado

**Solução:**
1. Ir para https://github.com/settings/tokens
2. Verificar se token ainda existe e é válido
3. Gerar novo token se necessário

---

### IA Provider retorna erro de autenticação

**Símbolo:** "Authentication failed" ou "Invalid API key"
**Causas comuns:**
- API Key foi copiada com espaços
- API Key expirou
- Conta não tem crédito (OpenAI, etc)

**Solução:**
1. Copiar API Key novamente (sem espaços)
2. Verificar na console se chave é válida
3. Confirmar crédito disponível

---

### N8N não consegue conectar

**Símbolo:** "Connection refused" ou timeout
**Causas comuns:**
- Servidor N8N não está rodando
- URL está errada
- Firewall bloqueando acesso

**Solução:**
```bash
# Verificar se N8N está rodando
curl https://app.n8n.cloud/health

# Se conectar, N8N está ok
```

---

### Database não conecta

**Símbolo:** "Connection refused" ou "FATAL: password authentication failed"
**Causas comuns:**
- PostgreSQL não está rodando
- Credenciais estão erradas
- Banco não existe

**Solução:**
```bash
# Conectar com psql
psql -U postgres -h localhost -d gca

# Se conectar, database está ok
```

---

## ✅ Checklist Final

- [ ] SMTP testado e funcionando
- [ ] GitHub PAT validado
- [ ] Pelo menos 1 IA Provider funcionando
- [ ] N8N conectado (opcional, mas recomendado)
- [ ] Database respondendo

**SE TODOS OS CHECKMARKS ESTÃO MARCADOS** → Admin Setup está completo! Prossiga para criar o Tenant fictício.

---

## 📞 Próximos Passos (Após Setup Completo)

1. ✅ Admin Setup concluído
2. 📊 Criar Tenant fictício ("Mock Ecommerce")
3. 👤 GP fictício acessa o sistema
4. 🎯 Arguidor: Equipe define Stack (Python + FastAPI)
5. 💻 Code Generation: Gerar código
6. ✓ Validation: Validar código
7. 🐙 GitHub: Criar PR
8. 🎉 Projeto completo testado

---

**Última atualização:** 2026-04-05  
**Versão:** GCA 1.0  
**Sequência:** SMTP → GitHub → IA → N8N → Database
