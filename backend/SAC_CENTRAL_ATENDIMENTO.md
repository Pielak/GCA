# 🆘 SAC - Central de Atendimento do Usuário | GCA

## Visão Geral

Cada usuário do GCA tem acesso a um **SAC (Suporte ao Cliente)** integrado na aplicação. Este SAC permite que os usuários abram tickets de suporte com problemas, dúvidas ou erros que encontram durante o uso do sistema.

---

## 1. Como Acessar o SAC

### Interface do Usuário

```
Barra Superior da Aplicação:
┌────────────────────────────────────────────────┐
│ GCA Ecommerce Project                [? SAC]   │
└────────────────────────────────────────────────┘
        (Ícone de interrogação no canto superior)

Ao clicar, abre modal:
┌───────────────────────────────────────────────┐
│  CENTRAL DE ATENDIMENTO (SAC)                 │
├───────────────────────────────────────────────┤
│ Descrever seu problema...                     │
│                                               │
│ [Abrir Novo Ticket]                          │
│ [Meus Tickets]                               │
│ [Documentação]                               │
└───────────────────────────────────────────────┘
```

---

## 2. Formulário de Novo Ticket

### Campos Pré-Formatados

```
┌────────────────────────────────────────────────┐
│ 📋 NOVO TICKET DE SUPORTE                     │
├────────────────────────────────────────────────┤
│                                                │
│ Nível de Severidade: [▼]                     │
│ ├─ □ BAIXO     (não impede trabalho)         │
│ ├─ □ MÉDIO     (reduz produtividade)         │
│ ├─ □ ALTO      (bloqueia funcionalidade)     │
│ └─ □ CRÍTICO   (sistema indisponível)        │
│                                                │
│ Descreva o Problema: [_________________]     │
│                      [_________________]     │
│                      [_________________]     │
│                      [_________________]     │
│ Mínimo: 20 caracteres                        │
│ Máximo: 5000 caracteres                      │
│ Caracteres: 0/5000                           │
│                                                │
│ Projeto Afetado: [Ecommerce Platform ▼]     │
│                                                │
│ Funcionalidade Afetada: [Code Generation ▼] │
│                                                │
│ Mensagens de Erro Recebidas:                 │
│ [_________________]                          │
│ [_________________]                          │
│ (Cole a mensagem de erro exatamente)         │
│                                                │
│ Comportamento Errático:                      │
│ [_________________]                          │
│ [_________________]                          │
│ (Descreva o que está acontecendo de forma    │
│  diferente do esperado)                      │
│                                                │
│ Anexar Screenshot/Arquivo: [Selecionar]      │
│                                                │
│ [Cancelar] [Enviar Ticket]                   │
└────────────────────────────────────────────────┘
```

---

## 3. Campos Obrigatórios

### Nível de Severidade (Obrigatório)

| Nível | Quando Usar | Tempo Esperado | Exemplo |
|-------|------------|----------------|---------|
| **BAIXO** | Não impede trabalho | 48-72 horas | Typo na interface, cor errada |
| **MÉDIO** | Reduz produtividade | 24-48 horas | Filtro não funciona direito, lentidão |
| **ALTO** | Bloqueia funcionalidade | 4-12 horas | Não consegue gerar código, aba fechou |
| **CRÍTICO** | Sistema indisponível | 1 hora | App não abre, todos sem acesso |

### Descrição do Problema (Obrigatório, 20-5000 caracteres)

**O que incluir**:
- ✅ O que você estava tentando fazer
- ✅ O que aconteceu (inesperado)
- ✅ O que deveria ter acontecido
- ✅ Quantas vezes ocorreu
- ✅ Em que browser/dispositivo

**Exemplo BOM**:
```
Estava tentando gerar código para um módulo de login.
Cliquei em "Gerar Código" e a página ficou carregando
por mais de 5 minutos, depois fechou sozinha.
Esperava que o código fosse gerado e exibido.
Tentei 3 vezes, mesma coisa.
Uso Chrome no Windows 11.
```

**Exemplo RUIM**:
```
Não funciona! Muito lento.
```

### Mensagens de Erro (Se aplicável)

Cole a mensagem exatamente como aparece:

**Exemplo**:
```
Error: Failed to generate code
Status: 500 Internal Server Error
At: 2026-04-05 15:22:33
Code: ERR_GEN_TIMEOUT
```

### Comportamento Errático (Se aplicável)

Descreva o que está estranho:

**Exemplo**:
```
Ao abrir a aba de "Code Generation", o combo de
"Projeto" mostra só 2 projetos quando deveria
mostrar 8. Se eu sair e entro novamente, mostra
correto. Isso acontece 80% das vezes.
```

---

## 4. Projeto e Funcionalidade Afetados

### Seleção Automática

```
Projeto: [Ecommerce Platform ▼]
├─ Ecommerce Platform (seu projeto)
└─ [Outros projetos em que você participa]

Funcionalidade: [Code Generation ▼]
├─ Arguidor
├─ Code Generation
├─ Validation
├─ GitHub Integration
├─ Dashboard
└─ Outra...
```

---

## 5. Fluxo Completo do SAC

### Passo 1: Abrir Ticket

```
Usuário → [? SAC] → Preenche Formulário → Clica [Enviar Ticket]
```

### Passo 2: Confirmação

```
Sistema valida campos obrigatórios
├─ Nível de Severidade? ✓
├─ Descrição > 20 caracteres? ✓
├─ Projeto selecionado? ✓
└─ Tudo OK? → Cria Ticket
```

### Passo 3: Notificações

```
Ticket é enviado para:
├─ GP do Projeto (via email + Teams/Slack se integrado)
└─ Admin (se CRÍTICO)

Emails Enviados:
├─ GP: "[BAIXO] Novo ticket: Typo na interface"
├─ Usuário: "Ticket #12345 criado com sucesso"
└─ Admin (se crítico): "🚨 CRÍTICO: Sistema indisponível"
```

### Passo 4: Rastreamento

```
Usuário pode acompanhar em "Meus Tickets":
┌────────────────────────────────────────────┐
│ MEUS TICKETS                               │
├────────────────────────────────────────────┤
│ #12345 | BAIXO | Typo na interface        │
│        | Criado: 15:22 | Status: ABERTO  │
│        | Resposta de: GP | [Ver Detalhes]│
│                                            │
│ #12344 | MÉDIO | Filtro não funciona      │
│        | Criado: 14:55 | Status: EM ANÁLISE
│        | Resposta de: GP | [Ver Detalhes]│
│                                            │
│ #12343 | CRÍTICO | App não abre           │
│        | Criado: 14:20 | Status: RESOLVIDO
│        | Resposta de: Admin | [Ver Detalhes]
│                                            │
└────────────────────────────────────────────┘
```

### Passo 5: Feedback e Resolução

```
GP ou Admin responde com:
├─ Diagnóstico do problema
├─ Solução fornecida
├─ Próximos passos (se houver)
└─ Pedido de confirmação se problema foi resolvido

Usuário pode:
├─ Marcar como "Resolvido"
├─ Adicionar comentário
├─ Reabrir se problema persist
└─ Avaliar a resposta (⭐⭐⭐⭐⭐)
```

---

## 6. Campos de Erro e Comportamento

### Como Registrar Mensagens de Erro

**Onde encontrar**:
```
Opção 1: Alerta na tela (copie texto)
Opção 2: Console do navegador (F12 → Console → copie)
Opção 3: Inspection de elemento (F12 → verificar logs)
```

**O que colar**:
```
Completo:
Error: Failed to generate code: TIMEOUT_EXCEEDED
Stack: at generateProjectCode (code-generation.ts:245)
Timestamp: 2026-04-05T15:22:33.456Z
Request ID: req_abc123def456
Status Code: 500

Ou apenas:
Failed to generate code
Status: 500
Error Code: TIMEOUT_EXCEEDED
```

### Como Descrever Comportamento Errático

**Estrutura recomendada**:
```
1. Ação que realizo:
   "Clico em [Gerar Código]"

2. Resultado observado:
   "A página congela por 30 segundos"

3. Resultado esperado:
   "Deveria gerar código em 5 segundos"

4. Frequência:
   "Acontece 100% das vezes neste projeto"
   "Acontece aleatoriamente (50% das vezes)"
   "Acontece apenas com projetos > 10 arquivos"

5. Contexto adicional:
   "Apenas quando projeto tem integração GitHub"
   "Apenas com 5+ membros na equipe"
   "Apenas ao usar provider OpenAI"
```

---

## 7. Anexos Permitidos

```
Máximo 5 arquivos por ticket
Tamanho máximo: 10MB total

Tipos permitidos:
✅ Screenshots (PNG, JPG)
✅ Arquivos de texto (.txt, .log)
✅ Videos (MP4, WebM - máx 5min)
✅ Arquivos JSON (configurações)
❌ Executáveis (.exe, .sh)
❌ Arquivos com credenciais
```

---

## 8. Classificação Automática

O sistema tenta classificar seu problema em:

```
Categoria Detectada: [Code Generation]
├─ Analisando palavras-chave
├─ "gerar", "código", "timeout" detectados
└─ Classifica como: Code Generation

Tag Automática: [performance]
├─ Palavras "lento", "timeout", "congela"
└─ Tag: performance

Prioridade: [MÉDIO]
├─ Baseado em: severidade (MÉDIO) + frequência
└─ SLA: 24-48 horas
```

---

## 9. SLA (Service Level Agreement)

```
Severidade | Resposta | Resolução | Escalonamento
-----------|----------|-----------|---------------
BAIXO      | 24h      | 72h       | GP → Admin (3 dias)
MÉDIO      | 12h      | 48h       | GP → Admin (1 dia)
ALTO       | 4h       | 12h       | GP → Admin (imediato)
CRÍTICO    | 1h       | 4h        | Admin (imediato)
```

---

## 10. Exemplo de Ticket Completo

### Ticket Enviado pelo Usuário

```
NÍVEL: ALTO
PROJETO: Ecommerce Platform
FUNCIONALIDADE: Code Generation

PROBLEMA:
Estava tentando gerar código para o módulo de checkout.
Selecionei Python + FastAPI, preenchi os requisitos e cliquei em
"Gerar Código". A página ficou carregando por 2 minutos e exibiu
um erro. Tentei 4 vezes, sempre mesma coisa. Ontem funcionava normal.

MENSAGENS DE ERRO:
Error: Failed to generate code
Status: 500
Message: TIMEOUT_EXCEEDED
Request ID: req_5a7d8c2e
Timestamp: 2026-04-05T15:22:33Z

COMPORTAMENTO ERRÁTICO:
O combo de "Projeto" mostra apenas alguns dos meus projetos.
Tenho 8 projetos mas vejo só 3. Se recarregar a página, aparece certo.

NAVEGADOR: Chrome 124.0.0.0 (Windows 11)
ANEXO: screenshot_erro.png (142 KB)

```

### Resposta do GP

```
TICKET #12345
STATUS: EM ANÁLISE → RESOLVIDO

Resposta do GP (João Silva):
Olá User,

Obrigado por reportar! Identifiquei o problema:

1. CAUSA: Seu projeto "Ecommerce" tem > 10GB de dados históricos,
   o que causa timeout da IA ao analisar.

2. SOLUÇÃO: Arquivei dados anteriores a 2025. Tente gerar código
   novamente.

3. RESULTADO: Teste enviado para você realizar. Se funcionar,
   marque como resolvido. Se não, reabra este ticket.

Timeline:
- Identifiquei o problema em 2h
- Implementei solução em 4h
- Você pode testar agora

Próximos passos:
- Teste a geração de código
- Valide se está rápido
- Confirme se problema foi resolvido
```

---

## 11. Boas Práticas para Abrir Ticket

### ✅ FAÇA

- Descreva exatamente o que fez
- Cole mensagens de erro completas
- Inclua browser, SO e versão
- Anexe screenshots relevantes
- Indique quantas vezes aconteceu
- Seja objetivo e claro

### ❌ NÃO FAÇA

- "Não funciona!" (sem detalhes)
- Remova dados sensíveis
- Abra múltiplos tickets iguais
- Coloque credenciais no texto
- Use linguagem agressiva
- Escreva em maiúscula

---

## 12. Ciclo de Vida do Ticket

```
┌─────────────────────────────────────────────────────┐
│                  NOVO TICKET                        │
├─────────────────────────────────────────────────────┤
│ Status: ABERTO                                      │
│ Atribuído a: GP do Projeto                         │
│ SLA: 24h (MÉDIO)                                   │
└──────────────────┬──────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────┐
│              GP ANALISA PROBLEMA                    │
├─────────────────────────────────────────────────────┤
│ Status: EM ANÁLISE                                  │
│ GP: João Silva                                      │
│ Progresso: 50%                                      │
└──────────────────┬──────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────┐
│             GP FORNECE SOLUÇÃO                      │
├─────────────────────────────────────────────────────┤
│ Status: AGUARDANDO FEEDBACK                         │
│ Mensagem: "Tente os passos abaixo..."              │
│ Ação do Usuário: Testar ou Reabrir                 │
└──────────────────┬──────────────────────────────────┘
                   ↓
         ┌─────────┴──────────┐
         │                    │
    Funcionou?          Não Funcionou?
         │                    │
         ↓                    ↓
   ┌──────────────┐  ┌──────────────────┐
   │ RESOLVIDO    │  │ REABERTURA       │
   │              │  │ + Comentário     │
   │ Ticket fecha │  │ volta para ANÁLISE
   └──────────────┘  └──────────────────┘
         │
         ↓
   ┌──────────────────────────┐
   │ Admin pode ver Histórico │
   │ e Feedback da Resolução  │
   └──────────────────────────┘
```

---

## 13. Métricas e Relatórios

### Admin e GP podem ver

```
Dashboard SAC:
├─ Total de Tickets: 152
├─ Abertos: 8
├─ Em Análise: 5
├─ Resolvidos: 139
│
├─ Por Severidade:
│  ├─ BAIXO: 45 (29%)
│  ├─ MÉDIO: 78 (51%)
│  ├─ ALTO: 18 (12%)
│  └─ CRÍTICO: 11 (8%)
│
├─ SLA Compliance:
│  ├─ BAIXO: 100% (45/45)
│  ├─ MÉDIO: 95% (74/78)
│  ├─ ALTO: 89% (16/18)
│  └─ CRÍTICO: 91% (10/11)
│
└─ Tempo Médio de Resolução:
   ├─ BAIXO: 2.3 dias
   ├─ MÉDIO: 1.8 dias
   ├─ ALTO: 8.4 horas
   └─ CRÍTICO: 2.5 horas
```

---

**Documento Version**: 1.0  
**Última Atualização**: 2026-04-05  
**Aplicação**: GCA - Gestão de Codificação Assistida
