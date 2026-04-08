# 🔐 Fluxo de Acesso e Segurança de Usuários - GCA

## Visão Geral

Este documento descreve os fluxos de acesso, autenticação, recuperação de senha e segurança do sistema GCA para todos os tipos de usuários.

---

## 1. Criação de Projeto pelo Admin

### Processo

```
Admin cria Projeto
      ↓
Admin convida GP (Gestor de Projeto)
      ↓
GP recebe E-mail com:
├─ Nome do Projeto
├─ Slug do Projeto
├─ Senha Provisória
├─ Link para Acessar
└─ Aviso: "Trocar senha na primeira acesso"
      ↓
GP Acessa o Sistema
      ↓
Sistema Força:
├─ "Você deve trocar sua senha"
├─ Campo: Nova Senha (obrigatório)
└─ Botão: "Trocar Senha e Continuar"
      ↓
GP consegue acessar o projeto
```

### O que o Admin Não Vê

- ❌ Senhas dos GPs (uma via de mão única)
- ❌ Credenciais configuradas pelo GP
- ❌ Dados confidenciais do projeto
- ❌ Atividades internas do GP (exceto segurança)

**Analogia**: Admin entrega o carro. GP cuida de tudo: abastecimento, manutenção, seguros.

---

## 2. Acesso ao Sistema - Primeiro Login

### Cenário: GP Acessa pela Primeira Vez

```
1. GP abre a aplicação
2. Clica em "Login"
3. Digite: E-mail + Senha Provisória
4. Sistema valida credenciais
5. Sistema detecta: "Primeira vez com essa senha"
6. Sistema redireciona obrigatoriamente para:
   
   ┌─────────────────────────────────────────┐
   │ TROCAR SENHA (OBRIGATÓRIO)              │
   ├─────────────────────────────────────────┤
   │ Seu login foi criado com uma            │
   │ senha provisória.                       │
   │ Você DEVE trocar agora.                 │
   │                                         │
   │ Nova Senha: [_________________]         │
   │ Confirmar: [_________________]          │
   │                                         │
   │ [❌ Sair] [✓ Trocar Senha e Entrar]    │
   └─────────────────────────────────────────┘

7. GP digita nova senha (requisitos: 8 caracteres, maiúscula, número)
8. Sistema salva nova senha (criptografada)
9. Sistema redireciona para: Selecionar Projeto
```

### Se GP Tentar Entrar Sem Trocar a Senha

```
1. GP acessa com senha provisória
2. Sistema bloqueia acesso imediatamente
3. Mensagem: "Você DEVE trocar sua senha antes de continuar"
4. Redireciona para "Trocar Senha"
5. Sem outras opções (não consegue "pular")
```

---

## 3. Seleção de Projeto

### Fluxo

```
GP Faz Login (com senha já trocada)
      ↓
Sistema exibe:
┌──────────────────────────────────┐
│ Selecione o Projeto              │
├──────────────────────────────────┤
│ [Combo com Projetos Ativos]      │
│ └─ Ecommerce Platform            │
│ └─ API Portal                    │
│ └─ Dashboard Admin               │
│                                  │
│ [✓ Acessar]                      │
└──────────────────────────────────┘

      ↓
GP seleciona projeto
      ↓
Sistema valida: "Este usuário está cadastrado neste projeto?"
├─ SIM → Acesso liberado ✓
└─ NÃO → Bloqueado (ver "Tentativas Suspeitas")
```

---

## 4. Tentativas Suspeitas de Acesso

### Proteção Contra Acesso Não Autorizado

**Regra**: Usuário só acessa projetos em que está cadastrado.

### Cenário: Tentativa de Acesso Não Autorizado

```
Tentativa 1: João tenta acessar "Projeto X" (não cadastrado)
├─ Sistema: "Projeto indisponível"
├─ Contador: 1/5 tentativas
└─ Log: registrado

Tentativa 2, 3, 4: Mesma coisa
├─ Contador: 2/5, 3/5, 4/5
└─ Logs acumulam

Tentativa 5: João tenta acessar novamente
├─ Sistema: "Entrada BLOQUEADA por segurança"
├─ Login dele é desativado temporariamente
├─ E-mail enviado IMEDIATAMENTE para:
│  ├─ João: "Sua conta foi bloqueada por atividade suspeita"
│  ├─ GP do Projeto: "Tentativa suspeita de acesso"
│  └─ Admin: "Alerta de segurança - tentativas de acesso"
└─ Mensagem: "Entre em contato com seu GP ou Admin"
```

### Informações no E-mail de Alerta

```
Para: Admin + GP

Assunto: 🚨 ALERTA: Tentativa Suspeita de Acesso

Corpo:
─────────────────────────────────────────
Usuário: João Silva (joao@empresa.com)
Projeto: Projeto X
Tentativas Bloqueadas: 5/5

Histórico:
1. 2026-04-05 14:25:10 - Tentou acessar "Dashboard Admin"
2. 2026-04-05 14:30:22 - Tentou acessar "Projeto Secreto"
3. 2026-04-05 14:35:44 - Tentou acessar "API Portal"
4. 2026-04-05 14:40:55 - Tentou acessar "Financeiro"
5. 2026-04-05 14:45:33 - Tentou acessar "Projeto X" → BLOQUEADO

Ação Requerida:
└─ Desbloqueie em: [Painel Admin > Segurança > Liberar Acesso]
─────────────────────────────────────────
```

---

## 5. Recuperação de Senha - Fluxo do Usuário

### Cenário: Usuário Esqueceu a Senha

```
1. Usuário abre a aplicação
2. Clica em "Esqueci minha senha"
3. Sistema exibe:

   ┌─────────────────────────────────────────┐
   │ RECUPERAR SENHA                         │
   ├─────────────────────────────────────────┤
   │ Digite seu e-mail de acesso:            │
   │ [joao@empresa.com________]              │
   │                                         │
   │ [Enviar Link de Recuperação]            │
   └─────────────────────────────────────────┘

4. Usuário digita seu e-mail
5. Sistema valida se e-mail existe
6. Sistema gera "token de recuperação" (válido por 24 horas)
7. E-mail é enviado:

   ───────────────────────────────────────────
   Assunto: Recuperar sua Senha - GCA
   
   Olá João,
   
   Você solicitou recuperação de senha.
   Link válido por 24 horas:
   
   https://gca.empresa.com/recuperar-senha?token=xyz123abc456
   
   Se não solicitou, ignore este e-mail.
   ───────────────────────────────────────────

8. Usuário clica no link
9. Sistema valida token
10. Exibe formulário:

    ┌─────────────────────────────────────────┐
    │ NOVA SENHA                              │
    ├─────────────────────────────────────────┤
    │ Nova Senha: [__________] (8+ caracteres)│
    │ Confirmar: [__________]                 │
    │                                         │
    │ [Resetar Senha]                         │
    └─────────────────────────────────────────┘

11. Usuário digita nova senha
12. Sistema salva e criptografa
13. Mensagem: "Senha alterada com sucesso!"
14. Redireciona para: Login
```

### Segurança do Link de Recuperação

- ✅ Válido por 24 horas apenas
- ✅ One-time use (não pode usar duas vezes)
- ✅ Enviado via SMTP seguro
- ✅ Link contém hash aleatório (impossível adivinhar)

---

## 6. Reset de Senha Forçado - Admin

### Cenário: Admin Reseta Senha de um Usuário

```
Admin acessa: Painel > Usuários > Buscar > [Usuário] > [Reset Senha]

Sistema gera:
├─ Nova Senha Provisória (ex: "TempP@ss2026")
├─ Envia E-mail IMEDIATAMENTE para o usuário
└─ Log registrado: "Admin resetou senha de João em 2026-04-05 15:30"

E-mail Recebido pelo Usuário:
───────────────────────────────────────────
Assunto: Sua Senha foi Resetada

Olá João,

Seu Admin resetou sua senha de acesso.
Nova senha provisória: TempP@ss2026

IMPORTANTE:
- Você DEVE trocar essa senha na primeira acesso
- Acesso bloqueado até trocar
- Link: https://gca.empresa.com/login

Se não foi você quem pediu, entre em contato com seu Admin.
───────────────────────────────────────────

Próximas Ações do Usuário:
1. Login com: joao@empresa.com + TempP@ss2026
2. Sistema força: "Trocar Senha (Obrigatório)"
3. Usuário digita nova senha
4. Sistema libera acesso
```

---

## 7. Fluxo de Acesso Resumido

```
┌─────────────────────────────────────────────────────────┐
│ PRIMEIRO ACESSO (GP)                                    │
├─────────────────────────────────────────────────────────┤
│ 1. Recebe E-mail com Senha Provisória                   │
│ 2. Login com E-mail + Senha Provisória                  │
│ 3. Sistema força: "Trocar Senha (Obrigatório)"          │
│ 4. Digita nova senha                                    │
│ 5. Seleciona projeto (Combo de projetos)               │
│ 6. Acessa o projeto                                     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ PRÓXIMOS ACESSOS                                        │
├─────────────────────────────────────────────────────────┤
│ 1. Email + Senha                                        │
│ 2. Seleciona projeto (só projetos em que está)         │
│ 3. Acessa                                               │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ ESQUECEU A SENHA                                        │
├─────────────────────────────────────────────────────────┤
│ 1. Clica "Esqueci minha senha"                          │
│ 2. Digita E-mail                                        │
│ 3. Recebe link via e-mail (válido 24h)                │
│ 4. Clica no link                                        │
│ 5. Digita nova senha                                    │
│ 6. Volta a fazer Login                                  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ ADMIN RESETA SENHA                                      │
├─────────────────────────────────────────────────────────┤
│ 1. Admin clica "Reset Senha"                            │
│ 2. Sistema gera Senha Provisória                        │
│ 3. E-mail é enviado IMEDIATAMENTE                       │
│ 4. Usuário recebe e-mail                                │
│ 5. Login com Senha Provisória                           │
│ 6. Sistema força: "Trocar Senha"                        │
│ 7. Usuário troca senha                                  │
│ 8. Acesso liberado                                      │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ TENTATIVA SUSPEITA DE ACESSO (5 tentativas)            │
├─────────────────────────────────────────────────────────┤
│ 1. Usuário tenta acessar projeto não autorizado        │
│ 2. 1ª-4ª tentativa: "Projeto indisponível"            │
│ 3. 5ª tentativa: "Entrada BLOQUEADA"                   │
│ 4. E-mail enviado para Admin + GP                      │
│ 5. Conta desativada até Admin liberar                  │
│ 6. Admin desbloqueador em: Painel > Segurança         │
└─────────────────────────────────────────────────────────┘
```

---

## 8. Boas Práticas de Segurança

### Para Usuários
- ✅ Trocar senha provisória imediatamente
- ✅ Usar senhas fortes (8+ caracteres, maiúsculas, números)
- ✅ Não compartilhar credenciais
- ✅ Logout ao sair da sessão

### Para Admin
- ✅ Reset de senha via Painel Admin
- ✅ Monitorar tentativas suspeitas (alertas)
- ✅ Liberar acessos bloqueados
- ✅ Manter log de auditoria
- ✅ Não compartilhar senhas provisórias por mensagem

---

## 9. Requisitos Técnicos

### Senha Provisória

**Formato**: `[Prefixo][Timestamp][Aleatório]`

Exemplo: `TEMP_20260405_K7xJ9Qm2`

**Características**:
- Gerada aleatoriamente a cada reset
- Válida apenas para primeiro acesso
- Não pode ser reutilizada
- Força o reset imediato

### Token de Recuperação

**Formato**: SHA-256 Hash

**Características**:
- Válido por 24 horas
- One-time use
- Gerado aleatoriamente
- Armazenado com hash (não reversível)

### Tentativas de Acesso

**Contador**: 5 tentativas máximo por projeto

**Reset do Contador**:
- Quando usuário acessa projeto com sucesso
- Quando Admin libera o acesso bloqueado

---

**Documento Version**: 1.0  
**Última Atualização**: 2026-04-05  
**Aplicação**: GCA - Gestão de Codificação Assistida
