# Arquivo — Validação assistida em campo (tickets de incidente)

MVP 6. Extraído de `GCA_CANONICAL_CONTRACT.md` em 2026-04-22 como parte da reforma documental.

---

### MVP 6 — Validação assistida em campo (tickets de incidente)

**Motivação:** o GCA é produto novo. Usuários reais (GPs e membros de projeto) vão encontrar bugs e necessidades não previstas. Este MVP cria o canal oficial dentro da instância para registrar, rotear e rastrear esses achados, de modo que cada incidente vire insumo rastreável para correções futuras (entregues via MVP 7).

#### Em escopo
- abertura de ticket de incidente pelo usuário, a partir do projeto em que ele atua;
- roteamento automático por papel de origem:
  - Dev / Tester / QA abre → **GPs do projeto** recebem;
  - GP abre → **Admins da instância** recebem;
  - Admin abre em um projeto → **demais Admins** recebem (tickets intra-admin);
- seção agregada na área administrativa com visão cross-projeto dos tickets escalados para Admin;
- campos mínimos: título, descrição, prioridade (baixa/média/alta/crítica), categoria (bug/dúvida/pedido de feature/incidente de pipeline), status (aberto/em andamento/resolvido/fechado);
- conversa no ticket (comentários entre autor, GP e/ou Admin), com autoria e timestamp;
- notificação in-app para os destinatários no ato da abertura e em cada evento relevante (comentário novo, mudança de status, resolução);
- auditoria compartimentalizada do ciclo de vida do ticket em `audit_log_global`;
- isolamento por projeto: ticket de um projeto nunca vaza para membros de outro projeto.

#### Fora de escopo
- SLA formal com escalonamento automático por tempo decorrido;
- integração com ferramentas externas (Jira, Linear, Zendesk, email bidirecional);
- pesquisa de satisfação pós-resolução;
- tickets transversais entre projetos (cada ticket pertence a exatamente um projeto; alternativa é abrir tickets irmãos).

#### Emenda 2026-04-19 (mesmo dia do fechamento original)

Expansão do MVP 6 solicitada pelo stakeholder-soberano logo após o fechamento. Mantém o MVP 6 como o MVP dos tickets — não gera MVP novo (protocolo §7.0.6 exige numeração monotônica).

**Adicionados ao em escopo:**
- **Área de Sustentação (papel cross-instância)**: nova flag de usuário `is_support`. Destinatários de tickets com `target_scope='admin'` passam a ser todos os usuários ativos com `is_admin=True OR is_support=True`. Admin e Sustentação veem `/admin/incidents`.
  - **Assimetria obrigatória**: `is_admin=True` **herda** os privilégios de Support automaticamente, mesmo sem `is_support=True`. Admin sobrepõe qualquer posição no GCA. Support **nunca** ganha privilégios de Admin por essa via — promoção a Admin continua fluxo separado de gestão de usuários. Conclusão prática: não existe UI que promova Support a Admin; existe UI que promove user comum a Support e que permite Admin acumular Support se quiser.
  - **Gestão**: seção nova "Equipe Sustentação" na área admin, acessível apenas a Admin, onde Admin ativa/desativa `is_support` de usuários ativos.
- **Anexos ao ticket (imagens, logs, textos)**: o autor pode anexar até 5 arquivos por ticket, 10 MB cada. Tipos aceitos: imagens (png/jpg/jpeg/webp/gif) e textos/logs/relatórios (txt/log/json/pdf). Storage no volume `gca-uploads` em `incidents/{ticket_id}/{hash}_{filename}`; tabela `incident_ticket_attachments` (id, ticket_id, uploader_id, filename, mime, size_bytes, sha256, storage_path, created_at). Sem scan de PII no V1 desta emenda — a responsabilidade pelo conteúdo anexado é do próprio autor, que é membro do projeto ou admin da instância.
- **Contexto obrigatório do incidente**: dois campos novos em `incident_tickets`:
  - `section_reference` (string, autopreenchida pela rota atual do frontend no momento da abertura — ex.: `/projects/{id}/ocg` — editável pelo autor se necessário);
  - `flow_description` (texto longo, **obrigatório**): o autor descreve passo a passo o que estava fazendo quando o erro apareceu. Modal recusa abertura se o campo vier vazio.

**Assimetria Admin↔Support — regra dura (em escopo):**
- Admin pode ver e agir em tickets escalados a admin (já existia);
- Support ativo pode ver e agir em tickets escalados a admin (nova regra);
- Admin pode promover usuário a Support (UI de "Equipe Sustentação");
- Admin pode rebaixar Support;
- Admin pode ativar `is_support` em si mesmo (Admin acumula Sustentação se quiser);
- UI de "Equipe Sustentação" **não** oferece operação de promover Support a Admin (isso fica na gestão de usuários canônica).

**Mantido fora de escopo mesmo na emenda:**
- Scan automático de PII em anexos (fora do V1; responsabilidade é do autor);
- Versionamento do anexo (substituir = upload novo, delete do anterior);
- Preview inline de PDF ou pré-visualização de vídeo (download simples);
- SLA/escalonamento automático;
- Integração externa (Jira/Linear/email bidirecional);
- Tickets cross-projeto.
