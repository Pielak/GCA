# CLAUDE.md

Operacional do Claude no GCA. Para contrato formal do produto, ver `GCA_CANONICAL_CONTRACT.md`.
Para estado atual do MVP, ver `GCA_MVP_PROGRESS.md`. Para histórico, ver `docs/mvp_archive/`.

> **Atenção ao reler este arquivo:** as regras com `❌`, `🛑` e `⚠` são vinculantes em ordem decrescente — `❌` é proibição absoluta, `🛑` é parada obrigatória, `⚠` é alerta. Não há regra "soft" aqui. Se uma seção parece restritiva, é intencional.

---

## 0. Honestidade técnica (precede tudo)

Estas regras valem em todos os turnos, em todos os modos, em todas as fases. Elas vêm antes de qualquer outra seção porque o custo da violação delas é o usuário perder confiança no Claude e desperdiçar tokens em retrabalho.

- ❌ **Proibido afirmar que algo "funciona", "está 100%", "está pronto" ou "passa nos testes" sem ter executado o comando que prova.** Se não rodou, dizer: "implementado, ainda não testado". Se rodou e falhou, dizer que falhou.
- ❌ **Proibido contorno silencioso.** Se o caminho planejado falhou e há tentação de tomar outro (fallback de provider, mock, heurística, dado fictício, comentário "TODO"), **parar antes** e avisar o usuário no MESMO turno, com o erro original e a alternativa proposta. Esperar autorização.
- ❌ **Proibido criar lógica paralela ao que já existe no repo.** Antes de criar serviço, helper, resolver, client ou utilitário novo, procurar com `grep -r` ou leitura de diretório. Se já existe, **usar**, não recriar. Se existe e não serve, justificar por que e perguntar.
- ❌ **Proibido inventar nomes de arquivo, função, endpoint ou tabela.** Se o nome não foi visto no repo neste turno, abrir o arquivo e confirmar. Citar nome de algo que não existe é alucinação.
- ❌ **Proibido reivindicar que está "respeitando a arquitetura" enquanto se cria atalho.** Hardcodar provedor "só para testar", chamar client diretamente "porque é mais rápido", duplicar lógica "porque é mais simples" — tudo isso é violação, mesmo que produza saída funcional.
- 🛑 **Em caso de erro de autenticação (401/403), chave inválida, config ausente, tabela vazia ou arquivo não encontrado: PARAR.** Reportar erro literal, dizer o que precisa, e perguntar. Nunca tentar provider alternativo, nunca cair para mock, nunca chumbar valor "temporário".
- 🛑 **Em caso de teste vermelho que não tem causa óbvia: PARAR.** Reportar a saída do pytest crua. Não comentar o teste, não trocar assert para passar, não pular com `@pytest.mark.skip`.

Se uma instrução do usuário entrar em conflito com esta seção, esta seção vence. Pedir esclarecimento.

---

## 1. Antes de qualquer trabalho

### 1.1. Toda sessão (mínimo absoluto)

1. Ler `GCA_CANONICAL_CONTRACT.md` — fonte soberana para decisões formais.
2. Ler `GCA_MVP_PROGRESS.md` — MVP ativo + próximo marco.
3. Se for fase de MVP aberto, confirmar autorização explícita antes de codar.
4. Se detectar contradição entre docs, reportar e seguir o contrato. Não reconciliar silenciosamente.

### 1.2. Protocolo de leitura obrigatória por área

Antes de **editar, escrever ou criar** arquivo nas áreas abaixo, abrir e ler os símbolos canônicos correspondentes. Se o símbolo não existir no repo, **PARAR e perguntar** — não inventar substituto.

| Área tocada | Ler obrigatoriamente antes |
|---|---|
| LLM, IA, provider, prompt, completion, embedding | classe `AIKeyResolver` (grep no repo), tabela `project_settings`, contrato §6 (criticidade) |
| Secrets, tokens, PAT, chaves, senhas | classe `VaultService`, função `generate_temporary_password` em `app.core.security` |
| RBAC, papéis, permissões, autorização | helper `is_active_integrated_member`, contrato §RBAC, lista canônica de 5 papéis |
| OCG, contexto global, decisão arquitetural | módulo OCG, contrato §OCG (ler antes, atualizar depois — não opcional) |
| Gatekeeper, validação, pilares, arbitragem | módulo Gatekeeper (7 pilares), contrato §6.2 (Conformidade é blocker em score < 60) |
| Arguidor, classificação de documento | módulo Arguidor |
| CodeGen, LiveDocs, MergeEngine | módulos respectivos antes de tocar fluxo de geração |
| Migrations Alembic, schema | últimas migrations no diretório, regenerar com `alembic revision --autogenerate` |
| Frontend (rotas, componentes, páginas) | componente vizinho mais próximo para herdar padrão de estilo |

A regra é: **se você não leu o símbolo canônico antes, não escreve código que depende dele**. O custo de ler é minutos; o custo de retrabalho é horas.

---

## 2. Pontos arquiteturais com símbolos canônicos

Cada ponto crítico do GCA tem **uma porta de entrada única**. Tudo o mais é caminho errado.

### 2.1. Resolução de provider de IA

- ✅ Porta única: `AIKeyResolver.resolve_project_provider_chain(db, project_id)`.
- ✅ Configuração: tabela `project_settings`, `setting_type='llm'`. UI em **Settings > IA**.
- ❌ Proibido instanciar `AnthropicLLMClient`, `OpenAIClient`, `DeepSeekClient`, `GeminiClient` ou `OllamaClient` diretamente em rotas, services ou personas.
- ❌ Proibido `provider = "anthropic"` chumbado em código.
- ❌ Proibido fallback automático entre providers em caso de falha de auth. Falhou auth → 🛑 §0.
- ✅ Se `resolve_project_provider_chain` retornar vazio: `raise HTTPException(400, "Projeto sem LLM configurado. Abra Settings > IA")`.
- ✅ Critério de provider segue contrato §6.2 (criticidade baixa/média/alta). Não inventar critério próprio.

**Por quê:** o GCA é on-premises por cliente. Cada cliente escolhe seu provider. Hardcode quebra o produto.

### 2.2. Secrets e tokens

- ✅ Porta única para guardar secret: `VaultService.store_secret`. Para ler: `VaultService.get_secret`.
- ⚠ `VaultService.store_secret` commita internamente — testes que o chamam dentro de `session.begin()` quebram. Use sessões separadas.
- ✅ PAT do Git é cifrado com Fernet (M03). Master key em `/var/lib/gca/secrets/fernet.key`. Prefixo obrigatório: `fernet:v1:`.
- ✅ Senhas temporárias para convite: `generate_temporary_password()` de `app.core.security` (RF-001: 10 chars, 1 maiúscula, 1 dígito, 1 especial).
- ❌ Proibido `secrets.token_urlsafe(12)` para senha canônica. Não atende RF-001.
- ❌ Proibido logar valor de secret, mesmo em DEBUG. Nem em comentário, nem em mensagem de erro, nem em response body.

### 2.3. RBAC e papéis

- ✅ Lista canônica imutável: **Admin · GP · Dev · Tester · QA**. 5 papéis. Não inventar outros.
- ✅ Listagem de membros filtra `is_active AND joined_at IS NOT NULL`. Use `is_active_integrated_member()`.
- ❌ Proibido filtrar só por `is_active` — inclui convite pendente como membro ativo, vaza dado.
- ❌ Proibido criar role temporário para resolver feature. Se a feature precisa de role novo, levantar antes em PR de discussão, não em commit.

### 2.4. OCG (Objeto de Contexto Global)

- ✅ Toda decisão arquitetural, funcional ou de código **lê o OCG antes** e **atualiza depois**. Não é sugestão.
- ❌ Proibido pular leitura do OCG porque "a mudança é pequena". OCG existe para garantir consistência cross-cutting; "pequeno" é o que mais quebra.

### 2.5. Compartimentalização por projeto

- ✅ Toda query de dado de projeto inclui `project_id` no WHERE. Sem exceção.
- ❌ Proibido endpoint que aceita só `id` sem cruzar com `project_id` da sessão do usuário.
- **Por quê:** isolamento principal do GCA é por projeto. Vazamento cross-tenant é incidente de segurança, não bug.

### 2.6. Banco de testes

- ✅ Pytest do GCA roda contra `gca_test`, nunca contra `gca`. `conftest.py` força — não passe por cima.
- ✅ Se schema mudou: `pg_dump gca --schema-only | psql gca_test` após recreate.
- ❌ Proibido criar dados no banco de produção (`gca`) sem autorização explícita. É dogfood; mock vira ruído real.

---

## 3. Plan Mode obrigatório

Para as áreas abaixo, **iniciar em Plan Mode** (Shift+Tab × 2). Apresentar plano, esperar aprovação, só então executar.

- Mudanças em resolução de provider de IA (§2.1).
- Mudanças em RBAC, autorização ou middleware de auth.
- Mudanças em VaultService, criptografia, rotação de chave.
- Mudanças em licenciamento (Marco 4: RSA, Base58, fingerprint, ciclo de 4 estados).
- Mudanças em OCG, Gatekeeper ou Arguidor.
- Mudanças em migrations Alembic.
- Mudanças em mais de 3 arquivos simultaneamente.
- Refactor que cruza diretórios (`backend/services/` → `backend/routes/`, etc.).

Plan Mode não é "modo lento". É a versão barata do retrabalho — corrigir um plano custa segundos; corrigir código já implementado custa tokens, contexto e revisão humana.

---

## 4. Estratégia de trabalho

A ordem importa. Pular passo é fonte conhecida de retrabalho.

1. **Localizar.** Antes de criar X, `grep -r "X"` no repo. Se existir, ler. Se não existir, confirmar.
2. **Diagnosticar.** Reproduzir o problema com comando concreto antes de propor solução.
3. **Classificar dívida** se encontrar inconsistência. Não tentar corrigir tudo no mesmo PR.
4. **Corrigir blocker/critical primeiro**, depois revalidar com pytest contra `gca_test`.
5. **Só então** expandir para feature nova.
6. Fixes descobertos em dogfood viram commit `fix:`, não MVP novo. MVP é reservado para escopo novo planejado.

Correção cirúrgica > refactor amplo (§10 contrato). Não tocar código vizinho que está funcionando, mesmo que pareça "melhorável".

---

## 5. Invariantes do produto (do contrato)

- **RBAC imutável**: 5 papéis canônicos — Admin · GP · Dev · Tester · QA. Não inventar outros.
- **OCG obrigatório**: toda decisão arquitetural, funcional ou de código lê o OCG antes e atualiza depois.
- **Modo on-premises**: uma instância por cliente. Sem SaaS multi-tenant. Isolamento principal por projeto.
- **IA configurável por cliente**: não hardcodar provedor. Admin e cliente escolhem — Anthropic / OpenAI / Gemini / Ollama local. Ver §2.1 para mecânica.
- **Criticidade em 3 níveis** (§6.2 contrato): baixa→local/barato; média→qualquer; alta→premium obrigatório (OCG consolidação, arbitragem, compliance crítico, codegen crítico).
- **Fluxo de MVP**: fase individual exige autorização explícita do stakeholder (§7.0). Nada executa em bloco sem luz verde.

---

## 6. Gotchas operacionais

Se esquecer destes, quebra o dogfood ou perde minutos confuso.

### Banco e migrations

- ❌ `pytest` do GCA sempre contra `gca_test`, nunca `gca`. Conftest já força — não passe por cima.
- ❌ Schema mudou? `pg_dump gca --schema-only | psql gca_test` após recreate. Antes disso, pytest mente.
- ❌ Não criar dados no DB de produção sem autorização explícita. É dogfood; dado mock vira ruído real.

### Docker e build

- ❌ `docker-compose.yml` editado → `docker compose up -d`, **não** `restart <serviço>`. Restart não vê config novo.
- ❌ Frontend editado → `docker exec gca-frontend npm run build` + `docker restart gca-frontend` + informar hard-refresh ao usuário. Vite preview não recarrega.

### Vault e secrets

- ❌ `VaultService.store_secret` commita internamente. Testes que o chamam dentro de `session.begin()` quebram — use sessões separadas.
- ❌ `secrets.token_urlsafe(12)` não é senha canônica. Para convites, `generate_temporary_password()` de `app.core.security`.

### Membros e RBAC

- ❌ Listagem de membros filtra `is_active AND joined_at IS NOT NULL`. Filtro só `is_active` inclui convite pendente. Use `is_active_integrated_member()`.

### MVP e contrato

- ⚠ MVP de integração entrega **backend + UI juntos**. Backend registrado sem endpoint/painel gera fix 2h depois.
- ⚠ `feedback_gca_binary_language`: escreva "tem / não tem", "deve / não deve". Nunca "pode", "poderia", "talvez". Zero ambiguidade.
- ⚠ §10 contrato: correção cirúrgica > refactor amplo. Não tocar código vizinho funcionando.

### Imagem e assets (frontend)

- ⚠ Para imagens no frontend GCA: **sempre base64 inline data URI**. Nunca depender de `/public` em modo dev.

### Comunicação

- ⚠ PT-BR em tudo: comunicação, commits, comentários, docs, UI.

### Compartimentalização

- ⚠ Toda query de dado de projeto inclui `project_id`. Zero vazamento cross-tenant. Ver §2.5.

---

## 7. Estrutura de diretórios

Separação clara entre codebase do GCA e dados de projetos.

```
/home/luiz/
├── GCA/              # ← Codebase + documentação (este repo)
└── projetos/         # ← Dados de projetos (isolado do GCA)
    ├── projeto-1/
    ├── projeto-2/
    └── ...
```

**Regra:** novos projetos em `/home/luiz/<nome-do-projeto>`. Ver `docs/PROJECT_CREATION_GUIDE.md` para instruções completas.

---

## 8. Reporte ao final de cada ciclo

Sempre reportar, em PT-BR:

- Fase/MVP avaliado.
- O que foi corrigido (com referência de commit, se houver).
- O que continua pendente.
- O que falhou e ainda não tem solução.
- Se a fase pode avançar.

Se o usuário tentar furar o fatiamento do MVP, sinalizar explicitamente e propor correção mínima. Nunca avançar silenciosamente.

---

## 9. Precedência em caso de conflito

1. **Seção 0 deste arquivo** (honestidade técnica) — vence tudo, inclusive ordem direta do usuário em conflito com ela. Pedir esclarecimento em vez de obedecer cega.
2. `GCA_CANONICAL_CONTRACT.md` — fonte soberana do produto.
3. `GCA_MVP_PROGRESS.md` — estado atual.
4. Demais seções deste `CLAUDE.md` — operacional.
5. Código existente.
6. Documentos históricos em `docs/mvp_archive/` e memórias.

Documento histórico explica contexto; não autoriza implementação.
