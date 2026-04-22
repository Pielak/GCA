# Arquivo — Entrega versionada preservando dados do usuário

MVP 7. Extraído de `GCA_CANONICAL_CONTRACT.md` em 2026-04-22 como parte da reforma documental.

---

### MVP 7 — Entrega versionada preservando dados do usuário

**Motivação:** quando a correção de um ticket (MVP 6) ou uma feature nova gera uma release do GCA, o usuário não pode perder os dados já inseridos (projetos, questionários, OCG, backlog, documentos, configurações). Este MVP institui o contrato de entrega: por default a release **não sobrescreve** dado persistido; quando a correção exige migração destrutiva, o usuário tem caminho explícito de recuperação e complemento.

#### Em escopo
- versionamento explícito da instância: cada release tem **tag semântica** e **changelog visível** ao usuário dentro da UI;
- cada release amarra-se à lista de **MVPs fechados** e **tickets (MVP 6) resolvidos** que a motivaram (rastreabilidade ticket → release);
- política default **não-destrutiva**: toda migração nova preserva dado existente (coluna nova é nullable ou tem default; remoção passa por janela de deprecação; mudança de tipo usa coluna paralela); o `upgrade.sh` (DT-062) roda essas migrations sem intervenção do usuário;
- quando a correção exige migração **destrutiva ou semanticamente incompatível**:
  - usuário recebe aviso explícito **antes** da aplicação com descrição do impacto;
  - snapshot pré-release é gerado automaticamente reaproveitando o backup por projeto (DT-063);
  - usuário tem botão para **restaurar o estado anterior** dos dados do projeto;
  - usuário é conduzido por um **assistente pós-release** para completar informações novas referentes ao ticket que motivou a entrega (ex.: release adiciona campo obrigatório no questionário por causa do ticket X — assistente mostra projetos afetados e solicita o novo campo);
- changelog segmentado por papel: Admin vê a release inteira; GP vê o que afeta os projetos onde atua; Dev/Tester/QA vê o que afeta os módulos em uso;
- auditoria: cada aplicação de release + cada restauração de snapshot + cada preenchimento via assistente pós-release gera evento em `audit_log_global`.

#### Fora de escopo
- downgrade da versão do aplicativo (container/imagem) — continua operação manual via DT-062 `upgrade.sh` / `restore.sh`;
- compartilhamento automático de correção entre instâncias de clientes diferentes (cada cliente recebe release pelo fluxo de instalação próprio);
- marketplace de plugins, features opt-in ou A/B testing de release;
- edição retroativa de dado de usuário fora do caminho oferecido pelo assistente pós-release (dado preservado é dado preservado — mudança arbitrária exige nova release).
