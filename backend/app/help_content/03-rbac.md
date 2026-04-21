# RBAC e papéis

O GCA tem **5 papéis** e cada ação sensível do sistema exige uma permissão específica.

## Os 5 papéis

### Admin — escopo: instância

- Configura a instância: provedores de IA, SMTP, backup, thresholds e pesos dos pilares.
- **Não atua operacionalmente dentro dos projetos** — o GP é soberano lá.
- Convida e bloqueia usuários.
- Aprova ou rejeita requisições externas de projeto.
- Inspeciona auditoria global e métricas agregadas.
- Gerencia equipe de Sustentação (flag `is_support`).

Protege-se automaticamente: você **não consegue** desativar ou excluir o último Admin ativo da instância.

### GP — escopo: um projeto

O GP é o **dono funcional** do projeto. Tem acesso a todas as funcionalidades: OCG, ingestão, Gatekeeper, Arguidor, CodeGen, testes, documentação, releases. A distribuição operacional com Dev/Tester/QA é só uma divisão de trabalho do dia-a-dia — não uma restrição de permissão.

- Conduz o projeto do questionário até o release bundle.
- Aprova OCG, ingestões, análises, scaffolds de código.
- Convida membros (Dev, Tester, QA, outro GP).
- Pode **transferir a soberania** para outro membro ativo do projeto.
- Pode **convidar outro GP** (co-gestão).
- Configura as chaves de IA do projeto (separadas das globais).

### Dev — escopo: um projeto

- Implementa e gera código via CodeGen.
- Executa correções.
- Interage com o repositório Git do projeto (PAT configurado em Configurações).
- **Não aprova** módulos nem OCG — aprovação é GP.

### Tester — escopo: um projeto

- Edita, executa e registra testes.
- Aprova ou rejeita specs de teste (unit, integration, E2E).
- **Não aprova a execução formalmente** — isso é do QA.

### QA — escopo: um projeto

- Revisa e aprova a execução dos testes.
- Atua no gate `qa:approve` que libera o Release Bundle.
- **Não edita o conteúdo dos testes** — edição é do Tester.

## Matriz de permissões

| Ação | Admin | GP | Dev | Tester | QA |
|---|---|---|---|---|---|
| Criar/aprovar/arquivar projeto | ✅ | ⚠️ dentro do próprio | ❌ | ❌ | ❌ |
| Configurar IA da instância | ✅ | ❌ | ❌ | ❌ | ❌ |
| Configurar IA do projeto | ⚠️ override | ✅ | ❌ | ❌ | ❌ |
| Convidar membros para projeto | ✅ | ✅ (do próprio) | ❌ | ❌ | ❌ |
| Aprovar OCG | ✅ | ✅ | ❌ | ❌ | ❌ |
| Ingerir documentos | ✅ | ✅ | ✅ | ❌ | ❌ |
| Rodar CodeGen | ✅ | ✅ | ✅ | ❌ | ❌ |
| Editar spec de teste | ✅ | ✅ | ⚠️ | ✅ | ❌ |
| Executar teste | ✅ | ✅ | ✅ | ✅ | ❌ |
| Aprovar execução (qa:approve) | ✅ | ✅ | ❌ | ❌ | ✅ |
| Ver auditoria global | ✅ | ❌ | ❌ | ❌ | ❌ |
| Ver auditoria do projeto | ✅ | ✅ | ✅ | ✅ | ✅ |

## Fluxos de convite e transferência

### Convidar Admin

1. Admin existente → `/admin/users` → **"Convidar Administrador"**.
2. Preenche nome + email.
3. Sistema envia email com link de aceite (expira em 5 dias).
4. O convidado abre o link, define senha, aceita.
5. Passa a ter `is_admin=true` e fica ativo.

### Convidar membro para o projeto

1. GP → `/projects/:id/settings` → aba **Equipe** → **"Convidar Membro"**.
2. Escolhe o papel (Dev / Tester / QA / GP) e o email.
3. Sistema envia email com link de aceite + slug do projeto.
4. O convidado abre o link, define senha (se for primeiro acesso à instância), aceita.
5. Passa a ser membro ativo do projeto no papel escolhido.

### Transferir a soberania de GP → GP

Quando o GP atual precisa sair do papel e passar para outro membro:

1. GP atual → `/projects/:id/settings` → aba **Equipe** → **"Transferir soberania"**.
2. Seleciona um membro ativo e aceito do projeto.
3. Confirma duas vezes (modal).
4. Operação atômica: o chamador vira `dev`; o alvo vira `gp`.

Pré-condições que o sistema exige:

- O alvo precisa ser membro ativo e já ter aceitado o convite.
- O alvo não pode já ser GP.
- O alvo não pode ser o próprio chamador.

Ambos os lados da transferência geram evento na auditoria, agrupados pelo mesmo `correlation_id`.

### Revogar / bloquear usuário

- Admin → `/admin/users` → **"Bloquear"** ou **"Excluir"** no card do usuário.
- Se o alvo é o último Admin ativo, o sistema bloqueia a ação com 403. Você **não consegue** se trancar para fora da instância.

## Compartimentalização entre projetos

Regra dura: dado de um projeto **não cruza** para outro.

- Documentos ingeridos em projeto A nunca aparecem no OCG de B.
- Chaves de IA do projeto A não são usadas em chamadas do projeto B.
- Tokens Git (PAT) são criptografados por projeto.
- Notificações por email respeitam o escopo — Admin não é notificado sobre eventos de projetos onde ele não tem relação.
- Um mesmo repositório Git **não pode** ser vinculado a dois projetos. Ao tentar, o sistema rejeita com mensagem explícita citando o projeto que já usa aquele repositório.

## Auditoria de mudanças de papel

Todo evento que altera papel gera entrada em `audit_log_global`:

- `role_granted` — convite emitido, convite aceito, Admin promovido, transferência recebida.
- `role_revoked` — convite revogado, Admin rebaixado, usuário desativado, transferência emitida.
- `role_transferred` — evento específico do fluxo de transferência GP → GP.

Cada entrada registra: quem fez (`actor_id`), alvo (`target_user_id`), projeto (`project_id` — nulo para ações na instância), papel anterior e novo, fase (`invited`, `accepted`, `revoked`, `admin_promoted`, `admin_demoted`, `transferred`, `user_deactivated`) e timestamp.

Admin vê tudo isso em `/admin/audit` filtrando por evento.

## Ver também

- [Instalação & primeiro setup](?section=02-instalacao) — como criar o primeiro Admin.
- [Área Administrativa](?section=06-admin) — tour completo do que Admin faz.
- [Área de Gestão de Projeto](?section=07-gp) — tour completo do que GP faz.
