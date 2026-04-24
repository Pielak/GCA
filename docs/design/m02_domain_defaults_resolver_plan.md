# M02 — Domain Defaults Resolver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sistema aplica defaults de domínio público (LGPD, CC, CPC, CLT, segurança básica) automaticamente ao OCG via resolver dedicado, com UI de revisão/contestação. User para de responder M01 pro óbvio (prazo prescricional, campos RIPD, rate-limit DataJud, defaults técnicos usuais) — só responde o que é específico do cliente.

**Architecture:** 1 tabela nova (`applied_defaults`) guarda decisões automáticas. Base de conhecimento canônico em Python estruturada por categoria (legal/security/technical/compliance). Hook no Arguidor consulta resolver ANTES de emitir gap — se resolver encontra default canônico, grava em `applied_defaults` e remove do output de gaps. Updater absorve defaults como deltas positivos nos pilares correspondentes. Frontend tem aba "Decisões Automáticas" listando tudo com botão "Contestar" por decisão. M01 prompt reforçado a ignorar gaps já resolvidos.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy async + Pydantic v1 (backend) · React + TypeScript + Tailwind (frontend) · migrations SQL plain em `backend/migrations/NNN_*.sql` (padrão canônico GCA).

---

## File Structure

### Backend

| Ação | Arquivo | Responsabilidade |
|---|---|---|
| Create | `backend/migrations/039_applied_defaults.sql` | Tabela `applied_defaults` — decisões automáticas do resolver. |
| Modify | `backend/app/models/base.py` | Model SQLAlchemy `AppliedDefault` no final do arquivo. |
| Create | `backend/app/services/domain_defaults_kb.py` | Base de conhecimento canônico — dicionário estruturado. Função pura. |
| Create | `backend/app/services/domain_defaults_resolver.py` | `resolve_gap(gap, project_context) -> Optional[AppliedDefault]`. Consulta KB + LLM pra validar aplicação. |
| Modify | `backend/app/services/arguider_service.py` | Hook pós-identificação: filtra gaps com default aplicável, grava em `applied_defaults`. |
| Modify | `backend/app/services/ocg_updater_service.py` | Quando há `applied_defaults` novos, refletir nos pilares correspondentes. |
| Create | `backend/app/routers/applied_defaults_router.py` | 3 endpoints: list, contest, summary. |
| Modify | `backend/app/main.py` | Registrar novo router. |
| Modify | `backend/app/services/iterative_questionnaire_service.py` | `generate_iteration` não gera pergunta pra gaps com default aplicado. |
| Create | `backend/app/tests/test_m02_domain_defaults.py` | Testes standalone (padrão MVP 29 — respeita DT-034). |

### Frontend

| Ação | Arquivo | Responsabilidade |
|---|---|---|
| Create | `frontend/src/hooks/useAppliedDefaults.ts` | Hook de fetch/polling da lista de decisões. |
| Create | `frontend/src/pages/projects/AppliedDefaultsPage.tsx` | Aba "Decisões Automáticas" — lista agrupada por categoria + contestar. |
| Modify | `frontend/src/pages/projects/ProjectDetailLayout.tsx` | Entry no MODULES array. |
| Modify | `frontend/src/routes.tsx` | Rota `/applied-defaults`. |

### Docs

| Ação | Arquivo | Responsabilidade |
|---|---|---|
| Create | `docs/design/m02_domain_defaults_resolver_plan.md` | Este plano (já criado). |
| Modify | `docs/design/m02_impact_report.md` | (Após execução) métricas: N defaults aplicados, % gaps evitados no questionário, delta OCG médio. |

---

## Task 1: Migration SQL `applied_defaults`

**Files:**
- Create: `backend/migrations/039_applied_defaults.sql`

- [ ] **Step 1: Criar o arquivo de migration**

Conteúdo completo de `backend/migrations/039_applied_defaults.sql`:

```sql
-- MVP M02 — decisões automáticas do domain_defaults_resolver.
-- Cada gap que o Arguidor identifica passa pelo resolver. Se o gap tem
-- default canônico em domínio público (LGPD, CC, CPC, CLT, defaults
-- técnicos usuais), grava aqui em vez de virar pergunta no M01.

CREATE TABLE applied_defaults (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    gap_id VARCHAR(20) NOT NULL,
    -- ex: G003, G026 — id do gap do Arguidor que foi resolvido.
    category VARCHAR(40) NOT NULL,
    -- 'legal' | 'security' | 'technical' | 'compliance' | 'architecture'
    decision_key VARCHAR(160) NOT NULL,
    -- ex: 'retention.civil_cases', 'datajud.rate_limit'. Único por projeto.
    decision_value TEXT NOT NULL,
    -- valor aplicado; pode ser string simples ou JSON serializado.
    source_citation VARCHAR(400) NOT NULL,
    -- ex: 'CC art. 206 §5º', 'LGPD Art. 38', 'CNJ Termo de Uso DataJud 3.13'.
    rationale TEXT,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    contested_at TIMESTAMPTZ,
    contested_by UUID REFERENCES users(id) ON DELETE SET NULL,
    contested_value TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, decision_key)
);

CREATE INDEX ix_applied_defaults_project_category
    ON applied_defaults (project_id, category);
CREATE INDEX ix_applied_defaults_project_contested
    ON applied_defaults (project_id, contested_at)
    WHERE contested_at IS NOT NULL;

COMMENT ON TABLE applied_defaults IS
    'M02 — decisões automáticas aplicadas ao OCG pelo domain_defaults_resolver.';
COMMENT ON COLUMN applied_defaults.category IS
    'legal|security|technical|compliance|architecture';
COMMENT ON COLUMN applied_defaults.decision_key IS
    'Chave canônica da decisão. Única por projeto — re-aplicação atualiza em vez de duplicar.';
```

- [ ] **Step 2: Aplicar migration**

Run:
```
docker cp /home/luiz/GCA/backend/migrations/039_applied_defaults.sql gca-postgres:/tmp/039.sql
docker exec gca-postgres psql -U gca -d gca -f /tmp/039.sql
```

Expected: `CREATE TABLE` + 2 `CREATE INDEX` + 3 `COMMENT`.

- [ ] **Step 3: Validar schema**

Run: `docker exec gca-postgres psql -U gca -d gca -c "\d applied_defaults"`
Expected: 13 colunas, UNIQUE(project_id, decision_key), 2 indexes + PK.

- [ ] **Step 4: Commit**

```bash
git -C /home/luiz/GCA add backend/migrations/039_applied_defaults.sql
git -C /home/luiz/GCA commit -m "M02 Task 1 — migration 039 applied_defaults"
```

---

## Task 2: Model SQLAlchemy `AppliedDefault`

**Files:**
- Modify: `backend/app/models/base.py` (append após a última classe — `CustomQuestionnaireIteration`)

- [ ] **Step 1: Adicionar a classe**

Inserir no fim de `backend/app/models/base.py`, após a classe anterior:

```python
class AppliedDefault(Base):
    """M02 — decisão automática aplicada ao OCG pelo domain_defaults_resolver.

    Cada linha representa um default canônico (domínio público: LGPD, CC,
    CPC, CLT, segurança básica, padrões técnicos) que o resolver aplicou
    ao projeto em vez de perguntar ao user no M01. User contesta via UI
    — `contested_value` substitui `decision_value` pro CodeGen.
    """

    __tablename__ = "applied_defaults"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    gap_id = Column(String(20), nullable=False)
    category = Column(String(40), nullable=False)
    decision_key = Column(String(160), nullable=False)
    decision_value = Column(Text, nullable=False)
    source_citation = Column(String(400), nullable=False)
    rationale = Column(Text, nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    contested_at = Column(DateTime(timezone=True), nullable=True)
    contested_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    contested_value = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
```

Adicionar `Text` ao import se não estiver presente (já tem). `datetime` e `timezone` já importados do topo.

- [ ] **Step 2: Validar sintaxe**

Run: `python3 -c "import ast; ast.parse(open('/home/luiz/GCA/backend/app/models/base.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Validar import no container**

Run:
```
docker restart gca-backend && sleep 5
docker exec gca-backend python -c "from app.models.base import AppliedDefault; print('OK', AppliedDefault.__tablename__)"
```
Expected: `OK applied_defaults`

- [ ] **Step 4: Commit**

```bash
git -C /home/luiz/GCA add backend/app/models/base.py
git -C /home/luiz/GCA commit -m "M02 Task 2 — model SQLAlchemy AppliedDefault"
```

---

## Task 3: Base de conhecimento canônico `domain_defaults_kb.py`

**Files:**
- Create: `backend/app/services/domain_defaults_kb.py`

- [ ] **Step 1: Criar o módulo com a KB estruturada**

Conteúdo completo de `backend/app/services/domain_defaults_kb.py`:

```python
"""M02 — base de conhecimento canônico de defaults de domínio público.

Estrutura cada entrada como:
  {
    "key": str,                  # decision_key canônico
    "category": str,             # legal|security|technical|compliance|architecture
    "matches_any_of": list[str], # substrings/padrões que identificam o gap aplicável
    "value": str,                # valor default canônico (pode ter múltiplas linhas)
    "source": str,               # citação verificável da fonte
    "rationale": str,            # explicação curta
    "applies_when": list[str],   # contexto necessário do projeto (domain, stack, etc)
  }

Os defaults são consultados por `domain_defaults_resolver.resolve_gap`
que recebe o texto do gap + contexto do projeto e procura matches.
"""
from __future__ import annotations

from typing import Any

# Conjunto inicial canônico pra direito-BR + LGPD + segurança básica.
# Cada entry deve ter citação verificável (não inventar fonte).
LEGAL_DEFAULTS_BR: list[dict[str, Any]] = [
    {
        "key": "retention.civil_cases",
        "category": "legal",
        "matches_any_of": [
            "retenção de processos cíveis",
            "retenção cível",
            "prazo de guarda processo cível",
            "civil case retention",
        ],
        "value": "5 anos após o trânsito em julgado (prescrição executória — Código Civil art. 206 §5º I).",
        "source": "Código Civil Brasileiro, art. 206 §5º I (prescrição executória de títulos líquidos).",
        "rationale": "Após 5 anos do trânsito em julgado, prescreve a pretensão executória. Manter dados além disso é desnecessário e contraria princípio da minimização LGPD Art. 6º III.",
        "applies_when": ["domain:juridico", "project_type:processo_civil"],
    },
    {
        "key": "retention.labor_cases",
        "category": "legal",
        "matches_any_of": [
            "retenção de processos trabalhistas",
            "retenção trabalhista",
            "labor case retention",
        ],
        "value": "2 anos após encerramento do processo (CLT art. 11 — prescrição bienal pós-contrato).",
        "source": "CLT art. 11 — prescrição bienal após extinção do contrato de trabalho.",
        "rationale": "Passados 2 anos, não há pretensão trabalhista executável sobre o contrato extinto.",
        "applies_when": ["domain:juridico", "project_type:processo_trabalhista"],
    },
    {
        "key": "retention.access_logs",
        "category": "security",
        "matches_any_of": [
            "retenção de logs de acesso",
            "log retention",
            "access log retention",
        ],
        "value": "6 meses rolling (janela deslizante). Logs mais antigos são apagados automaticamente.",
        "source": "ISO/IEC 27001:2022 A.8.15 (Logging); Marco Civil Internet Lei 12.965/2014 art. 15 (6 meses mínimo).",
        "rationale": "6 meses atende Marco Civil como mínimo legal e é suficiente pra forense. Mais tempo agrava risco LGPD.",
        "applies_when": [],
    },
    {
        "key": "retention.deactivated_user_data",
        "category": "legal",
        "matches_any_of": [
            "retenção de dados de usuário inativo",
            "retenção advogado desativado",
            "user data retention",
        ],
        "value": "2 anos após desativação da conta. Após esse prazo, dados pessoais são anonimizados ou apagados.",
        "source": "LGPD Art. 16 (eliminação após tratamento); boa prática OAB (guarda de registro profissional).",
        "rationale": "LGPD exige eliminação quando a finalidade do tratamento cessa. 2 anos cobre eventuais auditorias de conformidade pós-desativação.",
        "applies_when": [],
    },
]

COMPLIANCE_DEFAULTS: list[dict[str, Any]] = [
    {
        "key": "compliance.ripd_structure",
        "category": "compliance",
        "matches_any_of": [
            "RIPD",
            "relatório de impacto",
            "privacy impact assessment",
            "LGPD art 38",
        ],
        "value": (
            "Estrutura canônica LGPD Art. 38:\n"
            "  1. Finalidade específica do tratamento\n"
            "  2. Base legal aplicada (Art. 7º / 11º)\n"
            "  3. Categorias de dados tratados\n"
            "  4. Categorias de titulares\n"
            "  5. Período de retenção (por categoria)\n"
            "  6. Medidas de segurança técnicas e administrativas\n"
            "  7. Transferência internacional (se houver) e salvaguardas\n"
            "  8. Avaliação de riscos e medidas mitigatórias\n"
            "  9. Contato do DPO/encarregado"
        ),
        "source": "LGPD (Lei 13.709/2018) Art. 38 e Resoluções ANPD.",
        "rationale": "Estrutura mínima do RIPD segundo a lei. Campos específicos do projeto (finalidade real, DPO) são parâmetros do cliente, mas a estrutura é pública.",
        "applies_when": ["compliance:lgpd"],
    },
    {
        "key": "compliance.pii_masking",
        "category": "compliance",
        "matches_any_of": [
            "mascaramento de dados pessoais",
            "PII masking",
            "CPF masking",
            "mascarar CPF",
        ],
        "value": (
            "CPF mascarado como ***.XXX.XXX-** (CGU padrão). "
            "Email mascarado como u***@dominio.com. "
            "Telefone mascarado como (**) XXXXX-XX**. "
            "Aplicado em: telas públicas, relatórios compartilhados, logs de aplicação, exports."
        ),
        "source": "Resolução CGU 01/2021; Resolução CNJ 121/2010; LGPD Art. 12.",
        "rationale": "Padrão público de mascaramento no setor jurídico e administrativo brasileiro.",
        "applies_when": ["compliance:lgpd"],
    },
]

SECURITY_DEFAULTS: list[dict[str, Any]] = [
    {
        "key": "security.password_hashing",
        "category": "security",
        "matches_any_of": [
            "password hashing",
            "hash de senha",
            "armazenamento de senha",
        ],
        "value": "argon2id com parâmetros OWASP (memory=64MB, iterations=3, parallelism=4). Fallback: bcrypt cost≥12.",
        "source": "OWASP Password Storage Cheat Sheet (2024); NIST SP 800-63B.",
        "rationale": "argon2id é o algoritmo recomendado desde 2015 (Password Hashing Competition). bcrypt cost 12+ aceito como fallback.",
        "applies_when": [],
    },
    {
        "key": "security.jwt_secret",
        "category": "security",
        "matches_any_of": [
            "JWT secret",
            "segredo JWT",
            "JWT_SECRET",
        ],
        "value": "256-bit random (32 bytes via urandom), armazenado APENAS em env var/secret manager. Nunca no código, nunca no Git.",
        "source": "RFC 7519 §11 (JWT security); OWASP JWT Cheat Sheet.",
        "rationale": "Secret forte + armazenamento seguro é baseline. Qualquer comprometimento invalida todos os tokens ativos.",
        "applies_when": ["tech:jwt_auth"],
    },
    {
        "key": "security.icp_brasil_signing",
        "category": "security",
        "matches_any_of": [
            "ICP-Brasil",
            "assinatura digital",
            "certificado digital jurídico",
        ],
        "value": (
            "Assinatura via biblioteca pyhanko (Python) ou equivalente. "
            "Certificado A3 armazenado externamente ao app (token USB ou smartcard). "
            "Leitura via PKCS#11 (padrão ICP-Brasil). "
            "A1 (arquivo .pfx) aceito como alternativa para ambientes controlados, sempre com senha forte."
        ),
        "source": "ITI — Instituto Nacional de Tecnologia da Informação; MP 2.200-2/2001 (ICP-Brasil).",
        "rationale": "PKCS#11 é o padrão ICP-Brasil. Armazenamento externo (A3) é requisito pra cargos que exigem alta confiabilidade.",
        "applies_when": ["domain:juridico"],
    },
]

TECHNICAL_DEFAULTS: list[dict[str, Any]] = [
    {
        "key": "technical.datajud_rate_limit",
        "category": "technical",
        "matches_any_of": [
            "rate limit DataJud",
            "DataJud rate",
            "throttling DataJud",
        ],
        "value": "120 requisições/minuto (2 req/s). Por chave de API. Implementar com token bucket + retry exponencial em 429.",
        "source": "CNJ Termo de Uso da API DataJud, item 3.13.",
        "rationale": "Limite documentado pelo próprio CNJ. Excedê-lo bloqueia a chave temporariamente.",
        "applies_when": ["integration:datajud"],
    },
    {
        "key": "technical.datajud_endpoint_base",
        "category": "technical",
        "matches_any_of": [
            "endpoint DataJud",
            "URL DataJud",
        ],
        "value": (
            "DataJud (CNJ): https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal}/_search — "
            "onde {tribunal} segue o padrão tjXX (ex: tjsp, tjba, tjrj). "
            "Autenticação: API Key via header `X-DataJud-Key`."
        ),
        "source": "Portal DataJud CNJ — documentação pública da API.",
        "rationale": "Endpoint público padronizado. Cada tribunal tem seu próprio subdomínio/path.",
        "applies_when": ["integration:datajud"],
    },
]

ARCHITECTURE_DEFAULTS: list[dict[str, Any]] = [
    {
        "key": "architecture.sqlite_encryption",
        "category": "architecture",
        "matches_any_of": [
            "SQLite criptografado",
            "SQLCipher",
            "banco local criptografado",
        ],
        "value": "SQLCipher com AES-256-CBC + PBKDF2 100k iterações. Senha derivada da senha mestra do usuário (não armazenada em plaintext).",
        "source": "SQLCipher docs (Zetetic LLC); NIST SP 800-132 (PBKDF2).",
        "rationale": "Padrão da indústria para SQLite criptografado. 100k iterações é o mínimo NIST pra proteção offline.",
        "applies_when": ["stack:sqlite", "deployment:desktop"],
    },
]


def all_defaults() -> list[dict[str, Any]]:
    """Retorna a união de todas as categorias de defaults conhecidos."""
    return [
        *LEGAL_DEFAULTS_BR,
        *COMPLIANCE_DEFAULTS,
        *SECURITY_DEFAULTS,
        *TECHNICAL_DEFAULTS,
        *ARCHITECTURE_DEFAULTS,
    ]


def find_matches(gap_text: str, project_context_tags: list[str]) -> list[dict[str, Any]]:
    """Busca defaults cujas `matches_any_of` batem com o texto do gap E cujo
    `applies_when` é subset do contexto do projeto.

    Case-insensitive substring match em `matches_any_of`. Retorna lista —
    caller decide qual aplicar (geralmente o primeiro match com menor
    specificity; mas callers podem aplicar múltiplos se as decision_keys
    forem distintas).
    """
    gap_lower = gap_text.lower()
    ctx = set(project_context_tags or [])
    matches = []
    for entry in all_defaults():
        if not any(m.lower() in gap_lower for m in entry["matches_any_of"]):
            continue
        required = set(entry.get("applies_when") or [])
        if required and not required.issubset(ctx):
            continue
        matches.append(entry)
    return matches
```

- [ ] **Step 2: Validar sintaxe**

Run: `python3 -c "import ast; ast.parse(open('/home/luiz/GCA/backend/app/services/domain_defaults_kb.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Validar import no container**

Run: `docker exec gca-backend python -c "from app.services.domain_defaults_kb import all_defaults, find_matches; print('total_kb:', len(all_defaults()))"`
Expected: `total_kb: 10` (ou mais se você adicionou entradas).

- [ ] **Step 4: Commit**

```bash
git -C /home/luiz/GCA add backend/app/services/domain_defaults_kb.py
git -C /home/luiz/GCA commit -m "M02 Task 3 — base canônica de defaults (legal/compliance/security/tech/arch)"
```

---

## Task 4: Service `domain_defaults_resolver.py`

**Files:**
- Create: `backend/app/services/domain_defaults_resolver.py`

- [ ] **Step 1: Criar o resolver**

Conteúdo completo de `backend/app/services/domain_defaults_resolver.py`:

```python
"""M02 — resolver de defaults de domínio.

Recebe gap (dict com id/text/severity) + contexto do projeto e decide se
há default canônico aplicável via `domain_defaults_kb.find_matches`.
Quando há match, grava (ou atualiza) a decisão em `applied_defaults` e
retorna a linha. Se não há match, retorna None — gap continua sendo
tratado como pergunta pro M01.

Não chama LLM — é determinístico via substring match na KB. LLM entra
numa evolução futura (fuzzy matching). Hoje, se um gap precisa de decision
que a KB não tem, sobe pro M01 normalmente.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import AppliedDefault
from app.services.domain_defaults_kb import find_matches


async def resolve_gap(
    db: AsyncSession,
    project_id: UUID,
    gap: dict[str, Any],
    project_context_tags: list[str],
) -> Optional[AppliedDefault]:
    """Resolve um gap via default de domínio público, se aplicável.

    Args:
        gap: dict com ao menos `id` (str) e `text`/`description` (str).
        project_context_tags: tags do projeto (ex: ["domain:juridico",
            "project_type:processo_civil", "integration:datajud",
            "compliance:lgpd", "stack:sqlite", "deployment:desktop"]).

    Returns:
        `AppliedDefault` gravada/atualizada, OU None se nenhum default
        canônico se aplica.
    """
    gap_text = str(gap.get("text") or gap.get("description") or "")
    gap_id = str(gap.get("id") or "")
    if not gap_text:
        return None

    matches = find_matches(gap_text, project_context_tags)
    if not matches:
        return None

    # Pega o primeiro match. Multiple matches com mesma decision_key é ambiguidade
    # da KB e deve ser resolvida lá — aqui escolhemos determinístico.
    entry = matches[0]
    decision_key = entry["key"]

    # Upsert canônico: se já existe decisão com esta key pro projeto,
    # atualiza gap_id + rationale; NÃO sobrescreve se já foi contestada.
    existing_result = await db.execute(
        select(AppliedDefault).where(
            (AppliedDefault.project_id == project_id)
            & (AppliedDefault.decision_key == decision_key)
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        if existing.contested_at is not None:
            # User já contestou — NÃO re-aplica. Devolve a linha existente.
            return existing
        existing.gap_id = gap_id
        existing.rationale = entry["rationale"]
        existing.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(existing)
        return existing

    row = AppliedDefault(
        project_id=project_id,
        gap_id=gap_id,
        category=entry["category"],
        decision_key=decision_key,
        decision_value=entry["value"],
        source_citation=entry["source"],
        rationale=entry["rationale"],
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_applied(
    db: AsyncSession,
    project_id: UUID,
    include_contested: bool = True,
) -> list[AppliedDefault]:
    """Lista decisões aplicadas ao projeto, agrupáveis pelo caller por categoria."""
    query = select(AppliedDefault).where(AppliedDefault.project_id == project_id)
    if not include_contested:
        query = query.where(AppliedDefault.contested_at.is_(None))
    query = query.order_by(AppliedDefault.category, AppliedDefault.applied_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def contest_decision(
    db: AsyncSession,
    project_id: UUID,
    decision_id: UUID,
    contested_by: UUID,
    new_value: str,
) -> Optional[AppliedDefault]:
    """Usuário contesta um default aplicado. Marca `contested_at` + salva
    `contested_value`. CodeGen deve usar `contested_value` sobre
    `decision_value` quando presente.
    """
    result = await db.execute(
        select(AppliedDefault).where(
            (AppliedDefault.id == decision_id)
            & (AppliedDefault.project_id == project_id)
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    row.contested_at = datetime.now(timezone.utc)
    row.contested_by = contested_by
    row.contested_value = new_value
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


def infer_project_context_tags(ocg_data: dict[str, Any] | None) -> list[str]:
    """Gera tags de contexto do projeto a partir do OCG pra filtrar defaults.

    Hoje, inferência simples baseada em strings no STACK_RECOMMENDATION e
    PROJECT_PROFILE. Se OCG é escasso, retorna lista vazia — aí só
    defaults sem `applies_when` se aplicam (os universais).
    """
    if not isinstance(ocg_data, dict):
        return []
    tags: list[str] = []

    # Infer domain
    profile = ocg_data.get("PROJECT_PROFILE") or {}
    profile_str = str(profile).lower()
    if any(w in profile_str for w in ("jurídic", "juridic", "advogad", "processo", "tribunal")):
        tags.append("domain:juridico")
        if any(w in profile_str for w in ("cível", "civel", "cpc", "processo civil")):
            tags.append("project_type:processo_civil")
        if any(w in profile_str for w in ("trabalhist", "clt")):
            tags.append("project_type:processo_trabalhista")

    # Infer stack
    stack = ocg_data.get("STACK_RECOMMENDATION") or {}
    stack_str = str(stack).lower()
    if "sqlite" in stack_str:
        tags.append("stack:sqlite")
    if any(w in stack_str for w in ("tauri", "electron", "desktop")):
        tags.append("deployment:desktop")
    if "datajud" in stack_str or "datajud" in profile_str:
        tags.append("integration:datajud")
    if "jwt" in stack_str:
        tags.append("tech:jwt_auth")

    # Compliance
    if "lgpd" in profile_str or "lgpd" in stack_str:
        tags.append("compliance:lgpd")

    return tags
```

- [ ] **Step 2: Validar sintaxe**

Run: `python3 -c "import ast; ast.parse(open('/home/luiz/GCA/backend/app/services/domain_defaults_resolver.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Validar import no container**

Run:
```
docker restart gca-backend && sleep 5
docker exec gca-backend python -c "from app.services.domain_defaults_resolver import resolve_gap, list_applied, contest_decision, infer_project_context_tags; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git -C /home/luiz/GCA add backend/app/services/domain_defaults_resolver.py
git -C /home/luiz/GCA commit -m "M02 Task 4 — resolver determinístico + list/contest/infer_tags"
```

---

## Task 5: Hook no Arguidor

**Files:**
- Modify: `backend/app/services/arguider_service.py`

O Arguidor hoje identifica gaps e emite no `result_json`. Vamos inserir um passo pós-análise: cada gap passa pelo resolver. Os resolvidos são removidos do output de gaps e sinalizados em `applied_defaults_resolved` (campo informacional no log, não precisa existir no JSON de saída).

- [ ] **Step 1: Localizar onde gaps são persistidos**

Run: `grep -n "def analyze_document\|result_json\[.gaps.\]\|result_json.get..gaps" /home/luiz/GCA/backend/app/services/arguider_service.py | head`

Encontre o ponto onde `result_json["gaps"]` ou análogo é iterado pra salvar. Provável linha 500-540.

- [ ] **Step 2: Adicionar filtro pós-análise**

Importar o resolver no topo do arquivo, junto aos outros `from app.services...`:

```python
from app.services.domain_defaults_resolver import (
    resolve_gap,
    infer_project_context_tags,
)
```

Na função `analyze_document`, IMEDIATAMENTE após o parse do `result_json` do LLM e ANTES do loop que persiste gaps (aproximadamente após a linha 500, depois de `result_json = ...` e antes de `for gap_entry in result_json.get("gaps", []) or []`), inserir:

```python
            # M02 — filtra gaps resolvíveis por default de domínio.
            # Cada gap resolvido pelo resolver é movido de `gaps`
            # pra `applied_defaults_resolved` e NÃO é persistido como
            # gap técnico — não aparece no M01 nem punishes pilar.
            try:
                from app.services.domain_defaults_resolver import resolve_gap, infer_project_context_tags
                ocg_for_ctx = await self.db.execute(
                    select(OCG).where(OCG.project_id == project_id).order_by(OCG.version.desc()).limit(1)
                )
                ocg_row = ocg_for_ctx.scalar_one_or_none()
                ocg_data_raw = json.loads(ocg_row.ocg_data) if (ocg_row and ocg_row.ocg_data) else {}
                tags = infer_project_context_tags(ocg_data_raw)

                original_gaps = list(result_json.get("gaps") or [])
                kept_gaps = []
                resolved_defaults = []
                for g in original_gaps:
                    if not isinstance(g, dict):
                        kept_gaps.append(g)
                        continue
                    applied = await resolve_gap(self.db, project_id, g, tags)
                    if applied is None:
                        kept_gaps.append(g)
                    else:
                        resolved_defaults.append({
                            "gap_id": g.get("id"),
                            "decision_key": applied.decision_key,
                            "applied_default_id": str(applied.id),
                        })
                result_json["gaps"] = kept_gaps
                result_json["applied_defaults_resolved"] = resolved_defaults

                if resolved_defaults:
                    logger.info(
                        "arguider.m02_defaults_applied",
                        project_id=str(project_id),
                        resolved_count=len(resolved_defaults),
                        kept_gaps_count=len(kept_gaps),
                    )
            except Exception as m02_exc:  # noqa: BLE001
                logger.warning(
                    "arguider.m02_resolver_failed",
                    project_id=str(project_id),
                    error=str(m02_exc),
                )
```

O import `select` e `OCG` já estão nos imports do arquivo; verificar com `grep -n "^from sqlalchemy\|^from app.models.base" /home/luiz/GCA/backend/app/services/arguider_service.py | head`.

- [ ] **Step 3: Validar sintaxe + restart**

Run:
```
python3 -c "import ast; ast.parse(open('/home/luiz/GCA/backend/app/services/arguider_service.py').read()); print('OK')"
docker restart gca-backend && sleep 5
docker logs gca-backend --tail=3 2>&1 | tail -3
```
Expected: `OK` + `Application startup complete.`

- [ ] **Step 4: Commit**

```bash
git -C /home/luiz/GCA add backend/app/services/arguider_service.py
git -C /home/luiz/GCA commit -m "M02 Task 5 — hook no Arguidor consulta resolver antes de emitir gap"
```

---

## Task 6: Router `applied_defaults_router.py`

**Files:**
- Create: `backend/app/routers/applied_defaults_router.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Criar router com 2 endpoints**

Conteúdo completo:

```python
"""M02 — router de decisões automáticas (applied_defaults)."""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.require_action import require_action
from app.services.domain_defaults_resolver import contest_decision, list_applied

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/applied-defaults", tags=["applied-defaults"])


class AppliedDefaultItem(BaseModel):
    id: str
    gap_id: str
    category: str
    decision_key: str
    decision_value: str
    source_citation: str
    rationale: str | None = None
    applied_at: str
    contested_at: str | None = None
    contested_value: str | None = None
    effective_value: str  # contested_value se presente, senão decision_value


class AppliedDefaultsListResponse(BaseModel):
    items: list[AppliedDefaultItem]
    count_by_category: dict[str, int]
    contested_count: int


class ContestRequest(BaseModel):
    new_value: str = Field(..., min_length=1, max_length=4000)


@router.get("", response_model=AppliedDefaultsListResponse)
async def list_defaults(
    project_id: UUID,
    ctx: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Lista todos os defaults aplicados ao projeto, agrupados por categoria."""
    rows = await list_applied(db, project_id)
    items: list[AppliedDefaultItem] = []
    count_by_cat: dict[str, int] = {}
    contested = 0
    for r in rows:
        count_by_cat[r.category] = count_by_cat.get(r.category, 0) + 1
        if r.contested_at is not None:
            contested += 1
        effective = r.contested_value or r.decision_value
        items.append(AppliedDefaultItem(
            id=str(r.id),
            gap_id=r.gap_id,
            category=r.category,
            decision_key=r.decision_key,
            decision_value=r.decision_value,
            source_citation=r.source_citation,
            rationale=r.rationale,
            applied_at=r.applied_at.isoformat() if r.applied_at else "",
            contested_at=r.contested_at.isoformat() if r.contested_at else None,
            contested_value=r.contested_value,
            effective_value=effective,
        ))
    return AppliedDefaultsListResponse(
        items=items,
        count_by_category=count_by_cat,
        contested_count=contested,
    )


@router.post("/{decision_id}/contest", response_model=AppliedDefaultItem)
async def contest(
    project_id: UUID,
    decision_id: UUID,
    req: ContestRequest,
    ctx: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Usuário contesta uma decisão aplicada, informando o valor específico do caso dele."""
    row = await contest_decision(
        db=db,
        project_id=project_id,
        decision_id=decision_id,
        contested_by=ctx["user_id"],
        new_value=req.new_value,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Decisão não encontrada")
    return AppliedDefaultItem(
        id=str(row.id),
        gap_id=row.gap_id,
        category=row.category,
        decision_key=row.decision_key,
        decision_value=row.decision_value,
        source_citation=row.source_citation,
        rationale=row.rationale,
        applied_at=row.applied_at.isoformat() if row.applied_at else "",
        contested_at=row.contested_at.isoformat() if row.contested_at else None,
        contested_value=row.contested_value,
        effective_value=row.contested_value or row.decision_value,
    )
```

- [ ] **Step 2: Registrar em `main.py`**

Adicione (em ordem alfabética no bloco de imports, após `admin_gca_router` ou similar):

```python
from app.routers.applied_defaults_router import router as applied_defaults_router
```

E no bloco `app.include_router(...)`:

```python
app.include_router(applied_defaults_router, prefix=f"{settings.API_PREFIX}", tags=["applied-defaults"])
```

- [ ] **Step 3: Validar + restart**

Run:
```
python3 -c "import ast; ast.parse(open('/home/luiz/GCA/backend/app/routers/applied_defaults_router.py').read()); print('router OK')"
python3 -c "import ast; ast.parse(open('/home/luiz/GCA/backend/app/main.py').read()); print('main OK')"
docker restart gca-backend && sleep 5
docker logs gca-backend --tail=3 2>&1 | tail -3
```
Expected: `router OK` + `main OK` + `Application startup complete.`

- [ ] **Step 4: Commit**

```bash
git -C /home/luiz/GCA add backend/app/routers/applied_defaults_router.py backend/app/main.py
git -C /home/luiz/GCA commit -m "M02 Task 6 — router applied_defaults (list + contest) + registro em main"
```

---

## Task 7: M01 ignora gaps já cobertos por applied_defaults

**Files:**
- Modify: `backend/app/services/iterative_questionnaire_service.py`

- [ ] **Step 1: Filtrar gaps antes de gerar perguntas**

Em `_collect_arguider_gaps` (já existente), NÃO precisa mudar — ele só agrega gaps do Arguidor. Mas o Arguidor (depois da Task 5) já filtra gaps resolvidos pelo resolver. Então gaps com default aplicado nem aparecem em `module_candidates`.

Verificação adicional de segurança: em `generate_iteration`, adicionar bloco que lê `applied_defaults` do projeto e remove da análise quaisquer gaps cuja `decision_key` já tem default aplicado (defesa em profundidade caso o Arguidor antigo esteja em cache).

Localizar em `iterative_questionnaire_service.py` a função `generate_iteration` (~linha 160). Logo após a linha `gaps = await _collect_arguider_gaps(db, project_id, list(target_pillars_scores.keys()))`, adicionar:

```python
    # M02 — remove gaps cuja decision_key já tem default aplicado (defesa em profundidade).
    try:
        from app.services.domain_defaults_resolver import list_applied
        applied = await list_applied(db, project_id, include_contested=False)
        applied_keys = {a.decision_key for a in applied}
        # Os gaps vêm como lista por pilar. Filtra cada lista.
        for pillar, gap_list in list(gaps.items()):
            filtered = [
                g for g in (gap_list or [])
                if isinstance(g, dict)
                and not any(
                    key.split(".", 1)[-1].lower() in (g.get("name", "") + " " + g.get("description", "")).lower()
                    for key in applied_keys
                )
            ]
            gaps[pillar] = filtered
    except Exception:  # noqa: BLE001
        pass  # Não bloqueia geração — Task 5 já faz o principal.
```

- [ ] **Step 2: Validar**

Run: `python3 -c "import ast; ast.parse(open('/home/luiz/GCA/backend/app/services/iterative_questionnaire_service.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git -C /home/luiz/GCA add backend/app/services/iterative_questionnaire_service.py
git -C /home/luiz/GCA commit -m "M02 Task 7 — generate_iteration filtra gaps com default aplicado"
```

---

## Task 8: Testes standalone M02

**Files:**
- Create: `backend/app/tests/test_m02_domain_defaults.py`

- [ ] **Step 1: Criar testes standalone**

Conteúdo completo:

```python
"""M02 — testes unit standalone (padrão MVP 29, sem pytest/DB de prod)."""
from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.domain_defaults_kb import all_defaults, find_matches
from app.services.domain_defaults_resolver import infer_project_context_tags


def test_kb_has_entries():
    assert len(all_defaults()) >= 10, "KB deve ter ≥10 defaults canônicos"


def test_kb_entries_have_required_fields():
    for entry in all_defaults():
        assert "key" in entry and entry["key"], f"entry sem key: {entry}"
        assert "category" in entry and entry["category"] in (
            "legal", "security", "technical", "compliance", "architecture",
        ), f"category inválida: {entry.get('category')}"
        assert "matches_any_of" in entry and len(entry["matches_any_of"]) >= 1
        assert "value" in entry and entry["value"]
        assert "source" in entry and entry["source"], f"entry sem source: {entry['key']}"
        assert "rationale" in entry


def test_kb_keys_are_unique():
    keys = [e["key"] for e in all_defaults()]
    assert len(keys) == len(set(keys)), f"keys duplicadas: {[k for k in keys if keys.count(k) > 1]}"


def test_find_matches_retention_civil_hit():
    matches = find_matches(
        "prazo de retenção de processos cíveis não definido",
        ["domain:juridico", "project_type:processo_civil"],
    )
    keys = [m["key"] for m in matches]
    assert "retention.civil_cases" in keys


def test_find_matches_respects_applies_when():
    # Sem tag de domínio jurídico, não deve retornar defaults com applies_when domain:juridico
    matches = find_matches("retenção cível", [])
    keys = [m["key"] for m in matches]
    assert "retention.civil_cases" not in keys


def test_find_matches_universal_default_without_tags():
    # password_hashing não tem applies_when — deve aparecer com contexto vazio.
    matches = find_matches("armazenamento de senha em hash", [])
    keys = [m["key"] for m in matches]
    assert "security.password_hashing" in keys


def test_find_matches_ripd_lgpd():
    matches = find_matches(
        "RIPD não elaborado",
        ["compliance:lgpd"],
    )
    keys = [m["key"] for m in matches]
    assert "compliance.ripd_structure" in keys


def test_find_matches_datajud_rate_limit():
    matches = find_matches(
        "rate limit DataJud não definido",
        ["integration:datajud"],
    )
    keys = [m["key"] for m in matches]
    assert "technical.datajud_rate_limit" in keys


def test_find_matches_no_hit_returns_empty():
    matches = find_matches("pergunta completamente genérica sem palavra-chave canônica xyz", [])
    assert matches == []


def test_infer_tags_juridico_civil():
    ocg = {
        "PROJECT_PROFILE": {"domain": "Automação Jurídica Assistida — processo civil", "deliverables": ["AJA"]},
        "STACK_RECOMMENDATION": {"backend": {"library": "sqlite"}},
    }
    tags = infer_project_context_tags(ocg)
    assert "domain:juridico" in tags
    assert "project_type:processo_civil" in tags
    assert "stack:sqlite" in tags


def test_infer_tags_empty_ocg():
    assert infer_project_context_tags(None) == []
    assert infer_project_context_tags({}) == []


def test_infer_tags_datajud_integration():
    ocg = {
        "PROJECT_PROFILE": {"domain": "advogados e processos judiciais. Integração DataJud CNJ."},
        "STACK_RECOMMENDATION": {},
    }
    tags = infer_project_context_tags(ocg)
    assert "integration:datajud" in tags


def _run_all():
    import inspect
    tests = [v for k, v in globals().items() if k.startswith("test_") and inspect.isfunction(v)]
    passed, failed = 0, []
    for t in tests:
        try:
            t(); passed += 1
            print(f"  ✓ {t.__name__}")
        except AssertionError as e:
            failed.append((t.__name__, f"assertion: {e}")); print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed.append((t.__name__, f"{type(e).__name__}: {e}")); print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{'='*60}\nTotal: {len(tests)}  Passou: {passed}  Falhou: {len(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run_all())
```

- [ ] **Step 2: Copiar + rodar no container**

Run:
```
docker cp /home/luiz/GCA/backend/app/tests/test_m02_domain_defaults.py gca-backend:/app/app/tests/test_m02_domain_defaults.py
docker exec gca-backend python -m app.tests.test_m02_domain_defaults
```
Expected: `Total: 11  Passou: 11  Falhou: 0`

- [ ] **Step 3: Commit**

```bash
git -C /home/luiz/GCA add backend/app/tests/test_m02_domain_defaults.py
git -C /home/luiz/GCA commit -m "M02 Task 8 — testes standalone (11 testes KB + resolver)"
```

---

## Task 9: Frontend — aba "Decisões Automáticas"

**Files:**
- Create: `frontend/src/hooks/useAppliedDefaults.ts`
- Create: `frontend/src/pages/projects/AppliedDefaultsPage.tsx`
- Modify: `frontend/src/pages/projects/ProjectDetailLayout.tsx` (adicionar item ao MODULES array)
- Modify: `frontend/src/routes.tsx` (adicionar rota)

- [ ] **Step 1: Hook de fetch**

Conteúdo de `frontend/src/hooks/useAppliedDefaults.ts`:

```typescript
import { useEffect, useState, useCallback } from 'react'
import { apiClient } from '@/lib/api'

export interface AppliedDefaultItem {
  id: string
  gap_id: string
  category: string
  decision_key: string
  decision_value: string
  source_citation: string
  rationale: string | null
  applied_at: string
  contested_at: string | null
  contested_value: string | null
  effective_value: string
}

export interface AppliedDefaultsResponse {
  items: AppliedDefaultItem[]
  count_by_category: Record<string, number>
  contested_count: number
}

/**
 * M02 — lista de decisões automáticas do projeto. Polling 30s
 * (padrão das páginas reativas do GCA). `refetch` pra atualização
 * imediata após contest.
 */
export function useAppliedDefaults(projectId: string | undefined) {
  const [data, setData] = useState<AppliedDefaultsResponse | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    if (!projectId) return
    try {
      const res = await apiClient.get(`/projects/${projectId}/applied-defaults`)
      setData(res.data)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    if (!projectId) return
    load()
    const interval = setInterval(load, 30_000)
    return () => clearInterval(interval)
  }, [projectId, load])

  return { data, loading, refetch: load }
}
```

- [ ] **Step 2: Página**

Conteúdo completo de `frontend/src/pages/projects/AppliedDefaultsPage.tsx`:

```tsx
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { CheckCircle2, AlertTriangle, BookOpen, Loader2, Edit3 } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useAppliedDefaults, AppliedDefaultItem } from '@/hooks/useAppliedDefaults'
import { formatDateTimeBR } from '@/lib/datetime'

const CATEGORY_LABEL: Record<string, string> = {
  legal: 'Jurídico',
  security: 'Segurança',
  technical: 'Técnico',
  compliance: 'Compliance',
  architecture: 'Arquitetura',
}

const CATEGORY_COLOR: Record<string, string> = {
  legal: 'text-amber-400 border-amber-800/40 bg-amber-950/20',
  security: 'text-red-400 border-red-800/40 bg-red-950/20',
  technical: 'text-cyan-400 border-cyan-800/40 bg-cyan-950/20',
  compliance: 'text-violet-400 border-violet-800/40 bg-violet-950/20',
  architecture: 'text-emerald-400 border-emerald-800/40 bg-emerald-950/20',
}

export function AppliedDefaultsPage() {
  const { id: projectId } = useParams<{ id: string }>()
  const { data, loading, refetch } = useAppliedDefaults(projectId)
  const [contestingId, setContestingId] = useState<string | null>(null)
  const [contestValue, setContestValue] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (loading) {
    return (
      <div className="p-8 flex items-center gap-2 text-slate-400">
        <Loader2 className="w-4 h-4 animate-spin" /> Carregando...
      </div>
    )
  }

  if (!data) {
    return <div className="p-8 text-slate-500">Não foi possível carregar as decisões.</div>
  }

  if (data.items.length === 0) {
    return (
      <div className="p-6 max-w-5xl">
        <h1 className="text-xl font-semibold text-slate-100 mb-1">Decisões Automáticas</h1>
        <p className="text-xs text-slate-500 mb-6">
          Aqui aparecem decisões que o GCA aplicou automaticamente no seu projeto com base
          em domínio público (LGPD, Código Civil, defaults técnicos). Você pode contestar
          qualquer decisão.
        </p>
        <div className="rounded-lg border border-slate-800 bg-slate-900 px-4 py-6 text-sm text-slate-500">
          Ainda não há decisões automáticas. Elas aparecem à medida que o Arguidor
          identifica gaps com resposta canônica de domínio público.
        </div>
      </div>
    )
  }

  const groups: Record<string, AppliedDefaultItem[]> = {}
  for (const it of data.items) {
    const cat = it.category
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(it)
  }

  const startContest = (it: AppliedDefaultItem) => {
    setContestingId(it.id)
    setContestValue(it.contested_value || it.decision_value)
    setError(null)
  }

  const submitContest = async (decisionId: string) => {
    if (!projectId || !contestValue.trim()) return
    setSubmitting(true); setError(null)
    try {
      await apiClient.post(
        `/projects/${projectId}/applied-defaults/${decisionId}/contest`,
        { new_value: contestValue },
      )
      setContestingId(null)
      setContestValue('')
      await refetch()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      setError(e.response?.data?.detail || 'Falha ao contestar')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="p-6 max-w-5xl">
      <header className="mb-6">
        <h1 className="text-xl font-semibold text-slate-100 mb-1">Decisões Automáticas</h1>
        <p className="text-xs text-slate-500">
          {data.items.length} decisões aplicadas · {data.contested_count} contestadas.
          Cada decisão vem de domínio público (citação verificável). Contestar substitui o valor pro CodeGen.
        </p>
      </header>

      {error && (
        <div className="mb-4 px-3 py-2 bg-red-950/30 border border-red-900/40 rounded text-xs text-red-400">{error}</div>
      )}

      {Object.entries(groups).map(([cat, items]) => (
        <section key={cat} className="mb-6">
          <h2 className={`text-xs uppercase tracking-wide font-semibold mb-2 ${CATEGORY_COLOR[cat]?.split(' ')[0] || 'text-slate-300'}`}>
            {CATEGORY_LABEL[cat] || cat} ({items.length})
          </h2>
          <div className="space-y-2">
            {items.map((it) => {
              const isContested = it.contested_at !== null
              const isEditing = contestingId === it.id
              return (
                <div
                  key={it.id}
                  className={`border rounded-lg p-4 ${isContested ? 'border-amber-700/40 bg-amber-950/10' : 'border-slate-800 bg-slate-900'}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        {isContested ? (
                          <Edit3 className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
                        ) : (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                        )}
                        <span className="text-xs font-mono text-slate-400">{it.decision_key}</span>
                        <span className="text-[10px] text-slate-600">({it.gap_id})</span>
                      </div>
                      <pre className="text-xs text-slate-200 whitespace-pre-wrap font-sans mb-2">
                        {isContested ? it.contested_value : it.decision_value}
                      </pre>
                      <div className="flex items-center gap-2 text-[10px] text-slate-500">
                        <BookOpen className="w-3 h-3" />
                        <span>{it.source_citation}</span>
                        <span className="text-slate-700">·</span>
                        <span>aplicado {formatDateTimeBR(it.applied_at)}</span>
                        {isContested && (
                          <>
                            <span className="text-slate-700">·</span>
                            <span className="text-amber-400">contestado {formatDateTimeBR(it.contested_at)}</span>
                          </>
                        )}
                      </div>
                      {it.rationale && (
                        <p className="mt-2 text-[10px] text-slate-500 italic">{it.rationale}</p>
                      )}
                    </div>
                    {!isEditing && (
                      <button
                        onClick={() => startContest(it)}
                        className="flex-shrink-0 inline-flex items-center gap-1 px-3 py-1 rounded text-xs bg-slate-800 hover:bg-slate-700 text-slate-300"
                      >
                        <Edit3 className="w-3 h-3" /> {isContested ? 'Reeditar' : 'Contestar'}
                      </button>
                    )}
                  </div>

                  {isEditing && (
                    <div className="mt-3 pt-3 border-t border-slate-800">
                      <p className="text-[10px] text-slate-500 mb-2">
                        Escreva o valor correto pro seu caso específico. Será usado pelo CodeGen em vez do default.
                      </p>
                      <textarea
                        value={contestValue}
                        onChange={(e) => setContestValue(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 font-sans"
                        rows={4}
                      />
                      <div className="mt-2 flex gap-2">
                        <button
                          onClick={() => submitContest(it.id)}
                          disabled={submitting || !contestValue.trim()}
                          className="px-3 py-1 rounded text-xs bg-violet-600 hover:bg-violet-700 text-white disabled:opacity-50"
                        >
                          {submitting ? 'Salvando...' : 'Salvar contestação'}
                        </button>
                        <button
                          onClick={() => { setContestingId(null); setContestValue('') }}
                          className="px-3 py-1 rounded text-xs bg-slate-800 hover:bg-slate-700 text-slate-300"
                        >
                          Cancelar
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      ))}

      <div className="mt-6 p-4 rounded border border-amber-800/40 bg-amber-950/10">
        <div className="flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-amber-200/90">
            Cada default foi aplicado com base em citação pública verificável. Se o seu caso difere, use
            "Contestar" — o valor que você escrever substitui o default no CodeGen sem remover a
            rastreabilidade da decisão original.
          </p>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Adicionar ao MODULES na sidebar (ProjectDetailLayout)**

Localizar o MODULES array em `frontend/src/pages/projects/ProjectDetailLayout.tsx` e inserir entrada logo após `iterative-questionnaire`:

```tsx
  { path: 'applied-defaults', label: 'Decisões Automáticas', icon: BookOpen },
```

Importar `BookOpen` se ainda não estiver na lista `from 'lucide-react'`.

- [ ] **Step 4: Adicionar rota em `routes.tsx`**

Importar no topo:
```tsx
import { AppliedDefaultsPage } from './pages/projects/AppliedDefaultsPage';
```

Inserir no children block do ProjectDetailLayout (após `iterative-questionnaire` ou grupo equivalente):
```tsx
  { path: 'applied-defaults', element: <RequireProjectSetup><AppliedDefaultsPage /></RequireProjectSetup> },
```

- [ ] **Step 5: Build + restart**

Run:
```
docker exec gca-frontend npm run build 2>&1 | tail -5
docker restart gca-frontend 2>&1 | tail -1
```
Expected: `✓ built in Xs` sem erros.

- [ ] **Step 6: Commit**

```bash
git -C /home/luiz/GCA add frontend/src/hooks/useAppliedDefaults.ts frontend/src/pages/projects/AppliedDefaultsPage.tsx frontend/src/pages/projects/ProjectDetailLayout.tsx frontend/src/routes.tsx
git -C /home/luiz/GCA commit -m "M02 Task 9 — aba Decisões Automáticas (hook + página + sidebar + rota)"
```

---

## Task 10: Relatório de impacto

**Files:**
- Create: `docs/design/m02_impact_report.md`

- [ ] **Step 1: Relatório (preenchido parcialmente, resto em dogfood)**

Conteúdo:

```markdown
# M02 — Relatório de Impacto (Domain Defaults Resolver)

**Data:** [DATA DA EXECUÇÃO]
**Status:** MVP M02 entregue (Tasks 1-9)

## Arquitetura aplicada

- 1 tabela nova `applied_defaults` — histórico com `gap_id`, `decision_key`, `source_citation`.
- KB canônico em Python estruturada por categoria (legal/security/technical/compliance/architecture).
- Resolver determinístico via substring match + filtro por `applies_when` (tags do projeto).
- Hook no Arguidor filtra gaps com default aplicável; reduzidos do output NÃO viram gap nem pergunta M01.
- M01 `generate_iteration` ignora `applied_defaults` existentes (defesa em profundidade).
- UI de contestação: user substitui `decision_value` por `contested_value` — CodeGen usa o contestado.

## KB inicial (11 defaults canônicos)

| Categoria | Key | Fonte |
|---|---|---|
| legal | retention.civil_cases | CC art. 206 §5º I |
| legal | retention.labor_cases | CLT art. 11 |
| security | retention.access_logs | ISO 27001 A.8.15 + Marco Civil art. 15 |
| legal | retention.deactivated_user_data | LGPD Art. 16 + OAB |
| compliance | compliance.ripd_structure | LGPD Art. 38 |
| compliance | compliance.pii_masking | CGU 01/2021 + CNJ 121/2010 |
| security | security.password_hashing | OWASP + NIST SP 800-63B |
| security | security.jwt_secret | RFC 7519 + OWASP JWT |
| security | security.icp_brasil_signing | ITI + MP 2.200-2/2001 |
| technical | technical.datajud_rate_limit | CNJ TdU item 3.13 |
| technical | technical.datajud_endpoint_base | Portal DataJud CNJ |
| architecture | architecture.sqlite_encryption | SQLCipher + NIST SP 800-132 |

## Dogfood AJA (projeto 65cab180) — a medir após execução

| Métrica | Valor |
|---|---|
| Defaults aplicados | _preencher_ |
| Gaps evitados no M01 | _preencher_ |
| Delta OCG após aplicar defaults | _preencher_ |
| Decisões contestadas pelo user | _preencher_ |

## Tasks entregues

1. Migration 039
2. Model AppliedDefault
3. KB canônica (11 defaults)
4. Resolver + list/contest/infer_tags
5. Hook no Arguidor
6. Router 2 endpoints
7. M01 filtra gaps resolvidos
8. 11 testes standalone
9. Aba Decisões Automáticas
10. Este relatório

## Pendências (DT-095 candidatas)

- KB com LLM-assisted matching (fuzzy, não só substring).
- Expansão da KB: direito tributário, criminal, administrativo (hoje só cível+trabalhista).
- Propagar contestação pro Arguidor sem esperar nova ingestão.
- Notificação push quando defaults novos são aplicados (hoje só aparece na aba).
- Admin global: edição do KB via UI (sem deploy).
```

- [ ] **Step 2: Commit final**

```bash
git -C /home/luiz/GCA add docs/design/m02_impact_report.md
git -C /home/luiz/GCA commit -m "M02 Task 10 — relatório de impacto (MVP FECHADO)"
```

---

## Self-Review

**1. Spec coverage (proposta em `gca_mvp_m02_domain_defaults_proposal.md`):**

- [x] Tabela `applied_defaults` — Task 1.
- [x] Service `domain_defaults_resolver.py` + KB — Tasks 3, 4.
- [x] Hook no Arguidor — Task 5.
- [x] Router `/applied-defaults` (list + contest) — Task 6.
- [x] M01 ignora gaps resolvidos — Task 7.
- [x] Frontend aba — Task 9.
- [ ] Hook no OCG Updater pra refletir defaults nos deltas — **não coberto por tarefa dedicada**. O efeito de P2_compliance subir quando RIPD é aplicado VIRÁ pela ingestão seguinte que o Arguidor vai rodar sem o gap G003. Ou seja, o efeito é indireto mas canônico (pipeline ativo). Se ficar insuficiente em dogfood, vira DT.
- [x] Testes — Task 8.

**2. Placeholder scan:** nenhum TBD/TODO/similar escrito. Único placeholder intencional: "_preencher_" no relatório final (Task 10), preenchido após dogfood.

**3. Type consistency:**
- `AppliedDefault` (model) e `AppliedDefaultItem` (Pydantic/TS interface) têm os mesmos campos: id, gap_id, category, decision_key, decision_value, source_citation, rationale, applied_at, contested_at, contested_value. O Pydantic adiciona `effective_value` (decision_value ou contested_value) como conveniência.
- Categorias (`legal`|`security`|`technical`|`compliance`|`architecture`) são consistentes na tabela, na KB, no resolver e no frontend.
- `decision_key` sempre no formato `categoria.especificacao` (ex: `retention.civil_cases`) — consistente na KB, no resolver, no router e na UI.
