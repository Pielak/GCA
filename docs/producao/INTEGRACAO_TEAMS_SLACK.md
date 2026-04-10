# 📢 Integrações de Mensagem - GCA

## Visão Geral

O GCA pode se integrar com Teams, Slack e outras plataformas de mensagem para enviar notificações críticas ao Admin em tempo real.

---

## 1. Microsoft Teams Integration

### Configuração

1. **Criar Webhook no Teams**:
   - Acesse seu workspace do Teams
   - Vá em um canal qualquer
   - Clique em "..." (Mais opções) → "Connectors"
   - Procure por "Incoming Webhook"
   - Configure e copie a URL

2. **Adicionar no GCA**:
   - Admin Dashboard → Integrações → Microsoft Teams
   - Cole a Webhook URL
   - Clique em "Testar" para validar
   - Confirme

### Notificações Enviadas

```
Cada notificação é formatada como:
┌─────────────────────────────────────┐
│ 🚨 [CRÍTICO] Sistema Degradado      │
├─────────────────────────────────────┤
│ Serviço: N8N                        │
│ Status: INDISPONÍVEL                │
│ Desde: 2026-04-05 15:22:00         │
│ Último Status: OK                   │
│                                     │
│ Ação Requerida: Reiniciar serviço   │
│ Dashboard: [Link]                   │
└─────────────────────────────────────┘
```

---

## 2. Slack Integration

### Configuração

1. **Criar App Slack**:
   - Acesse https://api.slack.com/apps
   - Clique em "Create New App" → "From scratch"
   - Nome: "GCA Notifications"
   - Workspace: Selecione seu workspace

2. **Habilitar Webhooks**:
   - Vá em "Incoming Webhooks"
   - Ative a opção
   - Clique em "Add New Webhook to Workspace"
   - Selecione o canal para notificações
   - Copie a Webhook URL

3. **Adicionar no GCA**:
   - Admin Dashboard → Integrações → Slack
   - Cole a Webhook URL
   - Clique em "Testar"
   - Confirme

### Notificações Enviadas

```
Exemplo de notificação no Slack:

[GCA] ⚠️ Alerta - Tokens Próximos do Vencimento
┌──────────────────────────────────────────┐
│ Token: SMTP Password                     │
│ Vence em: 5 dias (10/04/2026)           │
│ Ação: Alterar ASAP                      │
│                                          │
│ Dashboard: [Ir para Integrações]         │
└──────────────────────────────────────────┘
```

---

## 3. Tipos de Notificações

### 1️⃣ Tokens Próximos do Vencimento

**Quando**: 7 dias antes da expiração

```
⏰ AVISO - Token Vencendo

Token: GitHub PAT
Vence em: 7 dias (12/04/2026)
Criado: 2025-04-05
Ação: Regenerar em: https://github.com/settings/tokens
```

---

### 2️⃣ Falta de Créditos em IA

**Quando**: Créditos < 10% do limite

```
💰 AVISO - Créditos em Baixa

Provedor: Anthropic Claude
Créditos Restantes: 8%
Limite: $100/mês
Gasto Atual: $92
Ação: Recarregar créditos
```

---

### 3️⃣ Falhas de Conexão com Serviços

**Quando**: Serviço fica indisponível por > 5 minutos

```
🔌 CRÍTICO - Serviço Indisponível

Serviço: N8N Automation
Status: OFFLINE
Último Check: 2026-04-05 15:22:00
Duração: 8 minutos
Ação: Reiniciar serviço em: [Admin Panel]
```

---

### 4️⃣ Degradação do Sistema

**Quando**: Múltiplos serviços falham ou acesso é bloqueado

```
🚨 CRÍTICO - SISTEMA EM DEGRADAÇÃO

Serviços Indisponíveis: 3
├─ N8N Automation
├─ SMTP Server
└─ Repositório (GitHub)

Usuários Afetados: 24
Último Backup: 2026-04-05 14:00:00
Ação: INTERVENÇÃO IMEDIATA REQUERIDA
```

**Nota Especial**: Quando o sistema entra em degradação total (acesso bloqueado para todos), apenas SMS e chamada telefônica de emergência serão acionados.

---

### 5️⃣ Atividades Suspeitas

**Quando**: 5 tentativas de acesso não autorizado

```
⚠️ SEGURANÇA - Tentativa Suspeita Bloqueada

Usuário: Carlos Santos (carlos@empresa.com)
Projeto Alvo: Projeto Secreto
Tentativas: 5/5 (BLOQUEADO)
Histórico:
1. 14:25:10 - Dashboard Admin
2. 14:30:22 - Projeto Secreto
3. 14:35:44 - API Portal
4. 14:40:55 - Financeiro
5. 14:45:33 - Projeto X

Ação: Liberar em: [Admin > Segurança]
```

---

## 4. Configuração de Alertas

No Admin Dashboard, você pode ativar/desativar:

- ✅ Tokens próximos do vencimento
- ✅ Falta de créditos em IA
- ✅ Falhas de conexão
- ✅ Degradação do sistema
- ✅ Atividades suspeitas

Cada alerta pode ser enviado para **múltiplos canais** simultaneamente.

---

## 5. Histórico de Notificações

Todo Admin pode ver:

```
Data/Hora | Tipo | Mensagem | Canais Enviados | Status
----------|------|----------|-----------------|--------
15:22:00  | ⚠️   | Tokens expirando | Teams, Slack | ✓ Entregue
10:15:30  | 💰  | Créditos baixos  | Teams | ✓ Entregue
23:45:12  | 🚨  | Sistema degradado | Teams, Slack, SMS | ✓ Entregue
```

---

## 6. Formato de Mensagem Padrão

Toda notificação inclui:

```
Cabeçalho:
├─ Ícone + Severidade (⚠️, 💰, 🔌, 🚨, ⚡)
├─ Tipo do alerta
└─ Timestamp

Corpo:
├─ O que aconteceu
├─ Contexto (serviço, usuário, projeto)
├─ Quando começou
└─ Duração

Ação:
├─ O que fazer
├─ Link direto para resolver
└─ Tempo estimado para resolver
```

---

## 7. Webhook Retry Policy

Se o envio falhar:

- **1ª tentativa**: Imediato
- **2ª tentativa**: 30 segundos depois
- **3ª tentativa**: 5 minutos depois
- **4ª tentativa**: 15 minutos depois
- **Após 4 falhas**: Admin é notificado que integração está com problema

---

## 8. Segurança

### Webhook URLs
- Armazenadas criptografadas no banco
- Nunca expostas na UI (apenas •••••••)
- Logs de toda tentativa de envio
- Acesso apenas para Admins

### Conteúdo das Mensagens
- Não contêm senhas ou tokens
- Dados sensíveis são mascarados
- Links são para dashboard autenticado
- IP do servidor pode ser incluído para debug

---

## 9. Limite de Taxa (Rate Limiting)

Para evitar spam:

```
Sistema: Máximo 100 notificações/hora
Por Canal: Máximo 10 notificações/minuto
Por Tipo: Consolidar alertas similares (ex: 5 tentativas suspeitas = 1 alerta)
```

---

## 10. Testando a Integração

**No Admin Dashboard**:

1. Vá para: Painel Admin → Integrações
2. Selecione a plataforma (Teams ou Slack)
3. Clique em "Testar"
4. Você receberá uma mensagem de teste
5. Confirme se recebeu

**Mensagem de Teste**:
```
✅ GCA - Teste de Integração

Esta é uma mensagem de teste para confirmar que a integração
está funcionando corretamente.

Se você viu esta mensagem, tudo está OK!

Timestamp: 2026-04-05 15:30:00
```

---

## 11. Troubleshooting

### Webhook inválida
- Copie novamente de Teams/Slack
- Certifique que começam com `https://`
- Verifique permissões no canal

### Mensagens não chegam
- Clique em "Testar" para validar
- Verifique se canal existe e é acessível
- Procure por mensagens deletadas automaticamente
- Verifique em "Histórico de Notificações"

### Falhas repetidas
- Admin Dashboard mostrará "Problema na Integração"
- Remova e reconfigure a webhook
- Contate suporte se persistir

---

**Documento Version**: 1.0  
**Última Atualização**: 2026-04-05  
**Aplicação**: GCA - Gestão de Codificação Assistida
