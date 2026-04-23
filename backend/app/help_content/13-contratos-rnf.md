# Contratos RNF — requisitos não-funcionais como contrato

Os **Contratos RNF** formalizam requisitos não-funcionais (performance, segurança, compliance, disponibilidade) como **cláusulas duras do OCG**. Saem do modo "texto solto lido pelo LLM" e viram:

1. **Bloco de instruções obrigatórias** injetado no prompt do CodeGen.
2. **Cenários de teste canônicos** inseridos nos planos do Tester.
3. **Checks estáticos grep** executados pós-geração — violação blocker rebaixa o arquivo pra `status="todo"` e emite audit.

Sem esse contrato, o LLM descobre latência, CWEs e rate limits pelo tom do documento. Com contrato, ele recebe números e regras e tem que atender — e o CodeGen registra quais cláusulas está cumprindo no docstring.

## As 4 categorias canônicas

A seção `RNF_CONTRACTS` do OCG tem exatamente 4 chaves raiz:

| Categoria | Campos canônicos | Exemplo |
|---|---|---|
| `performance` | `latency_p95_ms`, `throughput_rps`, `per_operation[]` | P95 ≤ 300 ms, throughput ≥ 200 req/s |
| `security` | `required_cwe_protections[]`, `rate_limit_rpm_public`, `rate_limit_rpm_authenticated`, `sensitive_data_categories[]` | CWE-79, CWE-89, CWE-798; 60 req/min público |
| `compliance` | lista de `{ regulation, requirement_id, enforcement }` | LGPD/Art.46/runtime, PCI-DSS/3.2/static |
| `availability` | `uptime_pct`, `rpo_minutes`, `rto_minutes` | uptime 99.9%, RPO 15 min, RTO 60 min |

Qualquer chave fora desse conjunto retorna **HTTP 422** no PUT. Todos os campos são opcionais — categoria vazia é válida e significa "sem contrato nessa dimensão".

## Como editar

Na página `/projects/:id/ocg`, abrir a aba **"Contratos RNF (editável)"**:

1. Cada categoria tem sua própria seção, com formulário estruturado.
2. Segurança oferece sugestões clicáveis de CWE (79, 89, 200, 287, 352, 798) e de categorias de dado sensível (password, token, cpf, cnpj, credit_card, ssn).
3. Compliance oferece sugestões de regulação (LGPD, GDPR, SOX, PCI-DSS, HIPAA, BACEN, CVM, ANS, SOC2, ISO-27001).
4. Clicar **"Salvar contrato"** dispara validação canônica:
   - Válido → bump de versão do OCG, audit `OCG_UPDATED` emitido.
   - Inválido → 422 com lista de erros mostrada inline.
   - Idêntico ao atual → noop (não bumpa).

Só perfis com `project:manage_team` (GP e Admin) editam; demais só leem.

## O que acontece depois que você salva

**CodeGen** (novo scaffold ou regenerar arquivo):
- Builder lê `RNF_CONTRACTS` e monta bloco canônico no prompt:
  ```
  ## Requisitos Não-Funcionais (contrato obrigatório)
  ### Segurança
  - Rate limit público: 60 req/min por cliente.
  - Proteções obrigatórias contra: CWE-89.
  ```
- Além disso, adiciona hints por stack (ex: Python → `slowapi`, Node → `express-rate-limit`, Java → `resilience4j`).
- Exige que o docstring gerado declare quais cláusulas o arquivo atende.

**Tester Review** (geração de specs):
- Cenários RNF obrigatórios aparecem no plano de teste:
  - Unit → só regressão por CWE.
  - Integration → tudo (latency, rate_limit, CWE, compliance).
  - E2E → latency P95 + rate limit (429 esperado).
- Provenance do spec registra `rnf_scenarios_required` pra auditoria.

**Validação estática pós-geração** (grep determinístico):
- Roda no fim de `/scaffold` antes do commit.
- Checks canônicos:
  - `rate_limit_middleware` → algum arquivo do módulo menciona `slowapi`/`Limiter`/`express-rate-limit`/`@RateLimit`.
  - `cwe_89_sql_injection` → SQL parametrizado (`text(:param)`, `select(...)`, `?`) no arquivo.
  - `cwe_798_hardcoded_credentials` → segredos vêm de vault (`VaultService`, `os.environ`).
  - `sensitive_data_not_logged` → anti-pattern: `logger.info(...password...)` ou `print(...token...)` falha o check.
- Violação blocker → status do arquivo vira `todo`, conteúdo recebe marker `[RNF_CONTRACT_VIOLATION]`, audit `CODEGEN_RNF_VIOLATION` é emitido com payload canônico.

## Propagação

Toda mudança em `RNF_CONTRACTS` bumpa a versão do OCG, o que:

- Marca scaffolds antigos como potencialmente desatualizados (regerar pra aplicar contrato novo).
- Marca test specs como stale na provenance.
- Alimenta o delta log `ocg_delta_log` com snapshot completo — rollback é possível.

## Auditoria

Eventos emitidos:

| Evento | Quando | Payload |
|---|---|---|
| `OCG_UPDATED` | PUT bem-sucedido com mudança | `version_from`, `version_to`, `source: "rnf_contracts.put"` |
| `CODEGEN_RNF_VIOLATION` | Validação estática achou blocker | lista `{check_id, file_path, severity, reason}`, `files_count` |

Qualquer alteração fica registrada em `audit_log_global` com hash chain, compatível com revisão do CISO.

## Regras duras

- Validação é **determinística**, sem LLM no caminho crítico — garante reprodutibilidade.
- Categorias totalmente vazias são removidas do payload antes de salvar (categoria vazia ≡ não declarada).
- Endpoints são binários: ou o contrato é aceito, ou retorna 422 com `errors[]`; nunca "parcialmente aceito".

## Ver também

- [OCG — Objeto de Contexto Global](?section=05-ocg) — onde os contratos vivem.
- [Codegen e linguagens suportadas](?section=08-codegen) — como o contrato vira código.
- [Pipeline canônico](?section=04-pipeline) — onde os cenários RNF aparecem no teste.
