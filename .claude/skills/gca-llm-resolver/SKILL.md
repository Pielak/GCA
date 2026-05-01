---
name: gca-llm-resolver
description: Use this skill when working with LLM provider invocation in the GCA project — including AIKeyResolver, project_settings table, multi-provider configuration (Anthropic, OpenAI, DeepSeek, Gemini, Ollama), prompt routing by criticality, or any code that needs to instantiate or call an AI client. Triggered by mentions of LLM, IA, provider, prompt, completion, embedding, AnthropicClient, AIKeyResolver, project_settings, or multi-LLM. Defines the canonical entry point and prohibitions on direct client instantiation.
---

# Skill: GCA LLM Resolver

> Detalhe operacional para invocação de LLMs no GCA. Regra resumida vive em `CLAUDE.md §3.1`. Esta skill é fonte detalhada — leia antes de tocar em qualquer código que invoque IA.

---

## 1. Por que esta skill existe

O GCA é **on-premises por cliente**. Cada cliente configura seu próprio provider, com sua própria chave. Hardcodar um provider quebra o produto. Foi exatamente o tipo de violação que motivou a criação dessa skill: implementação que ignorou `project_settings`, fixou `AnthropicLLMClient` direto na rota, e fez fallback silencioso quando a chave configurada falhou.

Esta skill estabelece a **porta única** e as **proibições absolutas** para qualquer invocação de IA.

---

## 2. Porta única

```python
from app.services.ai_key_resolver import AIKeyResolver

provider_chain = await AIKeyResolver.resolve_project_provider_chain(
    db=db,
    project_id=project_id,
)

if not provider_chain:
    raise HTTPException(
        status_code=400,
        detail="Projeto sem LLM configurado. Abra Settings > IA."
    )

# provider_chain define a ordem por criticidade da tarefa
# Use o client correspondente, instanciado pelo factory
client = LLMClientFactory.from_chain_entry(provider_chain.preferred)
```

### 2.1. O que `AIKeyResolver` faz por dentro

- Lê `project_settings` filtrando `setting_type='llm'` e `project_id=<id>`.
- Decifra a chave via `VaultService.get_secret`.
- Resolve a cadeia de providers configurados (preferred + fallbacks autorizados pelo GP).
- Aplica a política de criticidade de §6.2 do contrato canônico.
- Retorna estrutura tipada (`ProviderChain`) com chave já decifrada e modelo escolhido.

---

## 3. Configuração canônica

A configuração de IA do projeto vive em **uma única tabela**:

```sql
SELECT * FROM project_settings
WHERE project_id = :project_id
  AND setting_type = 'llm';
```

A UI dessa configuração está em **Settings > IA** dentro do projeto. O GP é quem configura. Admin não vê chaves de projeto (compartimentalização §2.5 do CLAUDE.md).

### 3.1. Estrutura do JSON em `project_settings.value`

```json
{
  "preferred_provider": "anthropic",
  "preferred_model": "claude-opus-4-7",
  "fallbacks": [
    {"provider": "openai", "model": "gpt-4o", "criticality_max": "media"},
    {"provider": "ollama", "model": "llama3.1:70b", "criticality_max": "baixa"}
  ],
  "budget_limit_usd_per_day": 50.0,
  "rate_limit_rpm": 60
}
```

---

## 4. Política de criticidade (§6.2 contrato)

Toda invocação declara a criticidade da tarefa, e o resolver escolhe o provider conforme:

- **Baixa**: Ollama local ou modelo econômico (gpt-4o-mini, claude-haiku, deepseek-chat).
- **Média**: qualquer provider configurado pelo GP.
- **Alta**: premium obrigatório (Claude Opus, GPT-4 Turbo, Gemini Ultra). **Sem rota alternativa** para barato.

Tarefas de criticidade alta:
- Consolidação do OCG (Agent 8: Consolidator).
- Arbitragem de conflitos (OCGConsolidator).
- Compliance crítico (P2, P7 quando bloqueante).
- CodeGen para módulos críticos (validados pelo Gatekeeper como "alta criticidade").

---

## 5. Proibições absolutas

### 5.1. Instanciação direta

```python
# ❌ PROIBIDO
client = AnthropicLLMClient(api_key=settings.ANTHROPIC_API_KEY)
client = OpenAIClient(api_key="sk-...")
client = DeepSeekClient(...)
client = GeminiClient(...)
client = OllamaClient(...)

# ✅ CORRETO
chain = await AIKeyResolver.resolve_project_provider_chain(db, project_id)
client = LLMClientFactory.from_chain_entry(chain.preferred)
```

### 5.2. Provider chumbado

```python
# ❌ PROIBIDO
provider = "anthropic"  # decisão arbitrária
model = "claude-opus-4-7"  # não veio de configuração

# ✅ CORRETO
chain = await AIKeyResolver.resolve_project_provider_chain(db, project_id)
provider = chain.preferred.provider
model = chain.preferred.model
```

### 5.3. Fallback automático sem configuração

```python
# ❌ PROIBIDO
try:
    return await deepseek_client.complete(prompt)
except AuthenticationError:
    return await anthropic_client.complete(prompt)  # contorno silencioso

# ✅ CORRETO
try:
    return await primary_client.complete(prompt)
except AuthenticationError as exc:
    raise HTTPException(
        status_code=502,
        detail=f"Falha de autenticação no provider {primary_provider}. "
               f"Verifique Settings > IA."
    ) from exc
```

### 5.4. Heurística disfarçada de IA

```python
# ❌ PROIBIDO
def evaluate_persona_pillar(content):
    try:
        return await llm_client.complete(prompt)
    except Exception:
        return {"score": 50, "rationale": "fallback heurístico"}  # mentira

# ✅ CORRETO — registra falha, propaga GCAError
def evaluate_persona_pillar(content):
    try:
        return await llm_client.complete(prompt)
    except Exception as exc:
        raise GCAError(
            code="LLM-001-COMPLETION-FAILED",
            user_message="Falha ao avaliar pilar com LLM configurado.",
            suggested_action="Verifique conexão com provider em Settings > IA.",
        ) from exc
```

---

## 6. Protocolo de falha (regra dura)

Se a chamada ao LLM falhar, **PARAR e reportar**. Nunca improvisar.

| Erro recebido | Ação correta |
|---|---|
| `401 Unauthorized` | `HTTPException(502, "Auth do provider X inválida. Verifique Settings > IA.")`. Não tentar próximo provider sem autorização explícita. |
| `403 Forbidden` | Mesmo tratamento. Provavelmente conta sem créditos ou modelo não permitido. |
| `429 Too Many Requests` | Respeitar `Retry-After`. Se persistir, sinalizar via `GCAError(LLM-002-RATE-LIMIT)`. |
| `500/502/503` (provider) | Backoff exponencial (até 3 tentativas). Se falhar todas, `GCAError(LLM-003-PROVIDER-DOWN)`. |
| Tempo limite | `GCAError(LLM-004-TIMEOUT)`. Não retornar resposta vazia. |
| Resposta vazia ou inválida | `GCAError(LLM-005-INVALID-RESPONSE)`. Não tentar parsear como sucesso. |
| Cadeia de providers vazia | `HTTPException(400, "Projeto sem LLM configurado. Abra Settings > IA.")`. |

---

## 7. Onde essa porta única é OBRIGATÓRIA

Qualquer ponto do código que faça invocação de IA precisa passar pelo resolver. Lista (não exaustiva):

- Pipeline OCG (Analyzer, 7 Pillar Specialists, Consolidator).
- Arguidor (classificação de documento, geração de perguntas).
- Sistema de Personas v2 (Auditor, 7 especialistas, ConflictDetector semântico).
- CodeGen (geração de código).
- LiveDocs (atualização de documentação viva).
- Qualquer endpoint que tome decisão com IA, mesmo "auxiliar".

Se algum dos pontos acima estiver instanciando client direto, é **dívida técnica blocker** que deve ser corrigida antes de feature nova.

---

## 8. Separação Admin × Projeto

- **Camada Admin**: chaves globais usadas **apenas** para avaliação de questionário externo (Technology Verification, antes do projeto existir). Configurada em `/api/v1/admin/gca/ai-providers`.
- **Camada Projeto (GP)**: chaves do cliente, configuradas em Settings > IA do projeto. Usadas em **tudo** que ocorre depois da aprovação do projeto (OCG, Personas, CodeGen, etc.).

❌ Proibido o pipeline do projeto usar chaves Admin como fallback. Levaria a vazamento de custos do dogfood para clientes.

---

## 9. Onde inspirar-se / não inspirar-se

Para padrões corretos, leia:
- `app/services/ai_key_resolver.py` — implementação canônica do resolver.
- `app/services/llm_client_factory.py` — factory que recebe `ChainEntry` e retorna client tipado.
- `app/services/vault_service.py` — descriptografia de chaves.

Para anti-padrões, **NÃO** se inspire em:
- Qualquer código que importe `from app.services.anthropic_client import AnthropicLLMClient` em rota.
- Qualquer código com `os.getenv("ANTHROPIC_API_KEY")` fora de configuração de bootstrap.

Se encontrar anti-padrão no repo, registre como dívida técnica em `GCA_MVP_PROGRESS.md`. Não corrigir silenciosamente — é mudança arquitetural que precisa de Plan Mode.

---

*Skill criada: 2026-04-30.*
