# Convites e primeiro acesso

Este capítulo cobre os dois fluxos canônicos de convite do GCA: **Admin convidando outro Admin** (área administrativa) e **GP convidando membro de equipe** (projeto). Ambos seguem o RF-001 do GCA — primeiro acesso com senha provisória + troca obrigatória antes de qualquer ação — mas com arquiteturas diferentes por motivos de segurança.

---

## 1. Comparativo rápido

| | Admin convida Admin | GP convida equipe |
|---|---|---|
| Quem convida | Admin da instância | GP do projeto |
| Onde inicia | `/admin/invite` | `/projects/:id/team` |
| Tabela usada | `InvitationToken` (isolada) | `ProjectMember.invite_token` |
| User é criado? | **Só após validação completa** | **Imediatamente** (com `first_access_completed=false`) |
| Link do email | `/accept-invitation?token=...` | `/p/:slug?invite=...` |
| Etapas na UI | **2 telas** (validar → definir) | **1 tela que muda** (login → troca) |
| Expiração do convite | 7 dias | 7 dias |
| Tentativas de senha | **máx 3** antes de invalidar token | rate limit geral de login |
| Rigor | Mais alto (conta só existe ao fim) | Mais ágil (conta desde o convite) |

Os dois emails incluem a **senha provisória em texto claro** + link para aceitar. Ambos exigem troca obrigatória antes do primeiro acesso.

---

## 2. Fluxo canônico — Admin convidando Admin

### 2.1 Quem faz

Admin da instância (usuário com `is_admin=true`). Ninguém mais. Este convite **cria mais um Admin** — role com acesso total à instância, não a projeto específico.

### 2.2 Passo a passo do convidante

1. No menu lateral da área administrativa, clique em **"Convidar Usuário"** (`/admin/invite`).
2. Preencha email e nome completo do futuro Admin.
3. Selecione o papel **Admin**.
4. Clique **Enviar Convite**.

O sistema:

- Gera senha provisória canônica RF-001 (10 caracteres, 1 maiúscula, 1 dígito, 1 especial).
- Cria `InvitationToken` com hash da senha, expira em 7 dias.
- **Não cria o User ainda** — só existirá após o convidado concluir os 2 passos.
- Dispara email com: nome de quem convidou + senha provisória em texto + link "Ativar Minha Conta" apontando para `/accept-invitation?token=...`.

### 2.3 Passo a passo do convidado

1. Recebe email "Bem-vindo ao GCA".
2. Copia a senha provisória do bloco amarelo destacado no email.
3. Clica em **Ativar Minha Conta** (ou cola o link `/accept-invitation?token=...` no navegador).
4. **Tela 1 — Validar senha provisória:** cola a senha + clica **Validar**.
   - Se a senha bate: avança automaticamente para Tela 2.
   - Se erra: mensagem de erro. **Máximo 3 tentativas** — passou disso o token é invalidado e Admin precisa reenviar.
5. **Tela 2 — Definir senha permanente:** digita nova senha (10+ caracteres, 1 maiúscula, 1 dígito, 1 especial) + confirma.
6. **Tela 3 — Sucesso:** conta criada; em 3 segundos redireciona para `/login`.
7. No login, entra com email + senha permanente recém-criada.

### 2.4 O que acontece se expirar / esgotar tentativas

- Token expirado (após 7 dias): convidado vê "Convite expirado". Admin reenvia do zero.
- 3 tentativas erradas: token invalidado; Admin reenvia.
- Em ambos os casos, nada fica "preso" — o novo convite gera `InvitationToken` novo.

---

## 3. Fluxo canônico — GP convidando equipe do projeto

### 3.1 Quem faz

GP do projeto. Outros GPs do mesmo projeto podem ser adicionados como co-gestores.

### 3.2 Papéis disponíveis

| Papel canônico | O que pode fazer |
|---|---|
| `gp` | Co-gestor do projeto (aprovação de módulos, regeneração do ERS, convidar) |
| `dev` | Implementa, roda CodeGen, commita. Não aprova módulos. |
| `tester` | Edita, executa e registra testes. |
| `qa` | Revisa/aprova execução de testes. |

### 3.3 Passo a passo do convidante

1. No projeto, abra `/projects/:id/team`.
2. Clique **Convidar**.
3. Preencha email + selecione papel.
4. Clique **Enviar**.

O sistema:

- Se o email **nunca existiu** no GCA: cria User com senha provisória canônica RF-001 + `first_access_completed=false`.
- Se o email **já existe** no GCA (ex: pessoa que já é membro de outro projeto): reaproveita o User; não envia senha provisória no email (ela usa a senha que já tem).
- Cria `ProjectMember` com `invite_token` novo; expira em 7 dias.
- Dispara email com: nome de quem convidou + detalhes do projeto + **senha provisória em texto claro (só quando user é novo)** + link "Aceitar Convite" apontando para `/p/:slug?invite=...`.

### 3.4 Passo a passo do convidado (usuário novo no GCA)

1. Recebe email "Você foi convidado para um projeto".
2. Copia a senha provisória do bloco amarelo destacado no email.
3. Clica em **Aceitar Convite** (ou cola o link `/p/:slug?invite=...`).
4. **Tela de login do projeto:** digita email + senha provisória.
5. Sistema detecta `first_access_completed=false` → troca automaticamente para tela de definição de senha permanente dentro da mesma página.
6. **Tela de troca:** digita nova senha (10+ caracteres, 1 maiúscula, 1 dígito, 1 especial) + confirma.
7. Após confirmar: `ProjectMember.accepted_at` e `joined_at` são marcados automaticamente; redireciona para `/projects/:id`.
8. A partir daí, loga normalmente com email + senha permanente.

### 3.5 Passo a passo do convidado (usuário já existente)

Igual ao anterior, **sem** os passos 2 (não há senha provisória no email) e 6 (não há tela de troca). Login direto com a senha que já tem. `accepted_at` + `joined_at` marcados no primeiro login.

### 3.6 Rigor vs ergonomia

Diferente do fluxo Admin, o Projeto **não** limita tentativas de senha por invite. Se o convidado erra várias vezes, só recebe "senha inválida" — o convite continua ativo até os 7 dias. Trade-off intencional: fluxo mais ágil, recuperação mais simples. A senha canônica RF-001 tem entropia alta o suficiente (~2⁶⁰) para brute force ser inviável no prazo do convite.

---

## 4. Operações comuns

### 4.1 Revogar convite pendente

- **Admin:** marcar `InvitationToken.revoked_at` (via endpoint admin ou limpeza direta).
- **Projeto:** na aba Equipe, botão **Revogar** no card do convite pendente. Seta `ProjectMember.revoked_at` + `is_active=false`.

### 4.2 Reenviar convite

Hoje ambos os fluxos fazem isso revogando o anterior e criando novo. GP / Admin clica **Convidar** de novo; o sistema detecta o convite anterior e rejeita com "já existe convite ativo" — se for isso, revogue primeiro, depois reenvie.

### 4.3 Convite órfão após regressão

Caso um convite tenha sido emitido antes de algum fix ao fluxo (senha não enviada por email, por exemplo), a senha provisória fica perdida (hasheada no banco sem cópia legível). O caminho canônico é:

1. Revogar o convite atual.
2. Reenviar — novo convite gera nova senha e inclui no email.

Se precisar recuperar rapidamente (email não chegou por bloqueio de spam), o Admin pode resetar a senha do usuário via fluxo de reset de senha padrão.

---

## 5. O que o convidado vê

### 5.1 Senha provisória no email (tanto admin quanto projeto)

Bloco amarelo destacado com:

- Email do convidado (pra não confundir se tiver vários convites simultâneos).
- Senha provisória em **monospace bold** (pra fácil seleção e cópia).
- Instrução: *"use esta senha para primeiro acesso; você será solicitado a definir uma senha pessoal"*.

### 5.2 Tela de troca obrigatória

Lista de 4 critérios canônicos (mínimo 10 caracteres, maiúscula, dígito, especial) marca cada um em verde em tempo real conforme o convidado digita. Dois campos — nova senha e confirmação — com olho para mostrar/ocultar. Botão de **Confirmar** só habilita quando os 4 critérios passam **e** os campos são idênticos.

Após troca bem-sucedida:

- **Admin:** redirect automático para `/login` em 3 segundos.
- **Projeto:** redirect automático para `/projects/:id` imediato (já está autenticado com a senha nova).

---

## 6. Troubleshooting

Problemas comuns estão no [Capítulo 10 — Troubleshooting](?section=10-troubleshooting):

- *"Convidado não recebeu a senha provisória no email"*
- *"Usuário convidado aparece como membro ativo mesmo sem aceitar convite"*

Para abrir ticket sobre problema de convite, use `/projects/:id/incidents` com categoria **Acesso**.
