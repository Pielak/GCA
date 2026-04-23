# DocumentCanonical — Schema v1

**MVP 29 Fase 1 — Design Técnico**
**Data:** 2026-04-23

## 1. Propósito

Representação canônica de qualquer documento ingerido no GCA. Substitui o texto bruto como input principal pro Arguidor/LLM. Objetivo: reduzir 3-5× os tokens enviados ao LLM e eliminar "reasoning de layout" da responsabilidade do modelo.

O `DocumentCanonical` é **determinístico** (mesmo arquivo + mesma versão de extractor = mesma saída). Nenhuma chamada LLM na geração do canônico — só regex, dicionário e heurística.

## 2. Shape

Dataclass Python em `app/services/document_canonical.py`:

```python
@dataclass
class CanonicalEntity:
    entity_type: str   # actor|system|requirement|date|integration|rule|version|reference
    value: str
    confidence: float  # 0.0-1.0 (regex hit = 0.9; dicionário = 1.0; heurística = 0.6)
    source_section_id: str | None = None  # onde foi encontrado

@dataclass
class CanonicalSection:
    id: str            # estável: "s1", "s2.1", ... (hierárquico)
    section_type: str  # heading|bullet|paragraph|table|list|code_block
    semantic_type: str # functional_requirement|non_functional_requirement|business_rule|
                       # actor|interface|glossary|risk|assumption|unknown
    title: str | None
    content: str       # texto da seção
    depth: int         # 1 = H1, 2 = H2, etc.

@dataclass
class DocumentCanonical:
    id: str                  # hash do arquivo + versão do extractor
    title: str
    document_type: str       # PDF|DOCX|MD|XLSX|IMAGE|QUESTIONNAIRE
    original_filename: str
    sections: list[CanonicalSection]
    entities: list[CanonicalEntity]
    requirements: list[str]  # extração determinística de RFs (frases "O sistema deve...")
    actors: list[str]        # papéis únicos (normalizado)
    rules: list[str]         # regras de negócio
    refs: list[str]          # referências a docs/URLs/artefatos externos
    affected_pillars: list[str]  # fase 2: preenchido; MVP: pode vir vazio
    stats: dict              # sections_count, entities_count, char_count, etc.
    extractor_version: str   # v1.0.0 (muda quando lógica muda → invalida cache)
    raw_text_fallback: str | None = None  # opcional, pra debug
```

## 3. Regras de classificação semântica

### Funcional vs Não-Funcional

Heurística por palavras-chave no conteúdo da seção:

- **`functional_requirement`**: "o sistema deve", "o usuário pode", "funcionalidade", "CRUD", "listar", "cadastrar", "permitir que"
- **`non_functional_requirement`**: "latência", "tempo de resposta", "performance", "SLA", "disponibilidade", "uptime", "escalabilidade", "carga", "throughput", "segurança de transporte", "criptografia"
- **`business_rule`**: "regra:", "condição:", "quando [X] então [Y]", "se [condição]", "validação"
- **`actor`**: título ou bullet começando com papel conhecido ("Administrador", "GP", "Tech Lead", "Compliance", "Auditor", "Usuário Final")
- **`interface`**: "API", "endpoint", "tela de", "componente", "módulo [X] expõe"
- **`glossary`**: seção titulada "Glossário", "Definições", "Siglas"
- **`risk`**: "risco:", "ameaça:", "vulnerabilidade"
- **`assumption`**: "assume-se que", "premissa:", "hipótese:"
- **`unknown`**: fallback quando nenhum match

Primeiro match vence. Conteúdo é lowercased e stripped pra comparação.

### Depth

- Em MD: `#` = 1, `##` = 2, etc.
- Em DOCX: heading_1 = 1, heading_2 = 2 (via `rich_docx_extractor`)
- Em PDF: inferido por tamanho de fonte relativo (heading = fonte > média) via `pdf_layered_extractor`
- Bullet top-level = depth do heading pai + 1
- Parágrafo = depth do heading pai

## 4. Dicionário do projeto

Lista estática em `app/services/document_canonical.py:_PROJECT_DICTIONARY`:

```python
_PROJECT_DICTIONARY = {
    "actors": [
        "Administrador", "Admin", "GP", "Gerente de Projeto", "Tech Lead",
        "Dev", "Desenvolvedor", "Dev Sr", "Dev Pl", "Tester", "QA",
        "Compliance", "Auditor", "Stakeholder", "Usuário Final", "GP",
    ],
    "systems": [
        "DataJud", "PostgreSQL", "Redis", "Celery", "FastAPI", "React",
        "Tauri", "SQLCipher", "Ollama", "Anthropic", "OpenAI", "DeepSeek",
        "Grok", "Docker", "n8n", "Prometheus", "Flower", "Cloudflare",
    ],
    "integrations": [
        "OAuth", "OIDC", "SAML", "LGPD", "GDPR", "SLA", "API REST",
        "Webhook", "SSO", "MFA", "JWT",
    ],
}
```

Palavra do dicionário no texto → `CanonicalEntity(confidence=1.0)`. Capitalization-insensitive via `re.IGNORECASE`.

## 5. Regex canônicos

```python
_REGEX = {
    "date_brazilian": r"\b\d{2}[/-]\d{2}[/-]\d{4}\b",
    "date_iso": r"\b\d{4}-\d{2}-\d{2}\b",
    "version_semver": r"\bv?\d+\.\d+(\.\d+)?(-[a-z0-9]+)?\b",
    "requirement_phrase": r"(?i)(o sistema|a aplicação|o módulo|o serviço)\s+(deve|deverá|precisa|pode)\b[^.]{10,200}",
    "url": r"https?://[^\s)]+",
    "ref_file": r"\b[\w-]+\.(pdf|docx|md|xlsx|json|yaml|yml|sql|py|ts|tsx|js|jsx)\b",
}
```

Regex em fallback quando palavra do dicionário não bate.

## 6. Exemplos por tipo

### 6.1 MD (questionário técnico)

Entrada: `Questionario_Tecnico_Governanca_Preenchido_AJS.md`

```markdown
# Questionário Técnico — Governança AJS

## Stack Backend
- Linguagem: Python 3.11
- Framework: FastAPI
- Banco: PostgreSQL 15

## Requisitos Funcionais
- O sistema deve autenticar via OAuth2
- O GP deve aprovar cada questionário antes da geração do OCG
```

Saída canônica (resumo):
```json
{
  "id": "ab3f...v1",
  "title": "Questionário Técnico — Governança AJS",
  "document_type": "MD",
  "sections": [
    {"id": "s1", "section_type": "heading", "semantic_type": "unknown",
     "title": "Questionário Técnico — Governança AJS", "depth": 1},
    {"id": "s2", "section_type": "heading", "semantic_type": "interface",
     "title": "Stack Backend", "depth": 2},
    {"id": "s2.1", "section_type": "bullet", "semantic_type": "interface",
     "content": "Linguagem: Python 3.11", "depth": 3},
    {"id": "s3", "section_type": "heading", "semantic_type": "functional_requirement",
     "title": "Requisitos Funcionais", "depth": 2},
    {"id": "s3.1", "section_type": "bullet", "semantic_type": "functional_requirement",
     "content": "O sistema deve autenticar via OAuth2", "depth": 3}
  ],
  "entities": [
    {"entity_type": "system", "value": "Python", "confidence": 1.0, "source_section_id": "s2.1"},
    {"entity_type": "system", "value": "FastAPI", "confidence": 1.0, "source_section_id": "s2"},
    {"entity_type": "system", "value": "PostgreSQL", "confidence": 1.0, "source_section_id": "s2"},
    {"entity_type": "actor", "value": "GP", "confidence": 1.0, "source_section_id": "s3.1"},
    {"entity_type": "integration", "value": "OAuth", "confidence": 1.0, "source_section_id": "s3.1"}
  ],
  "requirements": [
    "O sistema deve autenticar via OAuth2",
    "O GP deve aprovar cada questionário antes da geração do OCG"
  ],
  "actors": ["GP"],
  "rules": [],
  "refs": []
}
```

## 7. Integração com o pipeline atual

Em `ingestion_service.py`, pós-extração:

```python
# Hoje:
text = pdf_layered_extractor.extract(file_bytes).text
# manda text pro Arguidor

# Pós MVP 29:
canonical = document_canonicalizer.canonicalize(
    file_bytes, filename, doc_type="PDF"
)
# manda canonical pro Arguidor
```

## 8. Integração com o Arguidor

`arguider_service._build_prompt()` passa a receber `DocumentCanonical` em vez de texto bruto. Novo template serializa o canônico de forma dirigida:

```
## Documento analisado

**Título:** {canonical.title}
**Tipo:** {canonical.document_type}

### Requisitos identificados ({len(canonical.requirements)})
- {req1}
- {req2}

### Atores ({len(canonical.actors)})
{actores}

### Sistemas mencionados
{sistemas}

### Seções semânticas
{sections com semantic_type != "unknown"}
```

LLM recebe sinalizado. Prompt passa de ~15k tokens de texto bruto pra ~3-5k tokens estruturados.

## 9. Cache (Fase 2)

- Tabela nova `document_canonical_cache(key, canonical_json, created_at)`
- key = `sha256(file_bytes) || ':' || extractor_version`
- Re-ingestão do mesmo arquivo → SELECT no cache antes de re-canonizar
- Invalidação automática ao subir `extractor_version` (chave muda)

MVP não implementa — canoniza toda vez. Overhead aceitável (~100-300ms) pra docs até 10MB.

## 10. Versionamento

`extractor_version` sobe quando:
- Regex muda (qualquer entry em `_REGEX`)
- Dicionário do projeto muda (`_PROJECT_DICTIONARY`)
- Lógica de classificação semântica muda
- Shape do `DocumentCanonical` muda (breaking)

Bump é manual, seguindo semver: major = breaking shape; minor = novo campo opcional; patch = regra/dicionário.

Valor atual: **v1.0.0** (primeira release).
