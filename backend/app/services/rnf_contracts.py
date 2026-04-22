"""MVP 23 Fase 23.1 — Helpers canônicos pra `RNF_CONTRACTS` do OCG.

Fornece API estável de leitura + validação leve pros consumidores:
  - codegen_prompt_builder (Fase 23.3): `contract_as_prompt_block`
  - code_validation_service (Fase 23.4): `extract_static_checks`
  - test_spec_generator (Fase 23.4): `extract_test_scenarios`
  - integration_router / OCG endpoints (Fase 23.5): `validate_contract_dict`

Decisão binária canônica #2 do MVP 23: todos os campos são opcionais
e podem ser None. Fallback zero-impact em OCGs pré-23 (RNF_CONTRACTS=={}).

Decisão binária #3: validação estática é **determinística** — sem LLM no
caminho crítico. Grep estruturado por middleware/decorator declarado.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


EnforcementMode = Literal["runtime", "static", "both"]


# ─── Dataclasses de leitura (read-only views) ────────────────────────


@dataclass(frozen=True)
class PerformanceOperation:
    op: str
    budget_ms: int


@dataclass(frozen=True)
class PerformanceContract:
    latency_p95_ms: Optional[int] = None
    throughput_rps: Optional[int] = None
    per_operation: tuple[PerformanceOperation, ...] = ()

    @property
    def is_empty(self) -> bool:
        return (
            self.latency_p95_ms is None
            and self.throughput_rps is None
            and not self.per_operation
        )


@dataclass(frozen=True)
class SecurityContract:
    required_cwe_protections: tuple[str, ...] = ()
    rate_limit_rpm_public: Optional[int] = None
    rate_limit_rpm_authenticated: Optional[int] = None
    sensitive_data_categories: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return (
            not self.required_cwe_protections
            and self.rate_limit_rpm_public is None
            and self.rate_limit_rpm_authenticated is None
            and not self.sensitive_data_categories
        )


@dataclass(frozen=True)
class ComplianceItem:
    regulation: str
    requirement_id: str
    enforcement: EnforcementMode = "both"


@dataclass(frozen=True)
class AvailabilityContract:
    uptime_pct: Optional[float] = None
    rpo_minutes: Optional[int] = None
    rto_minutes: Optional[int] = None

    @property
    def is_empty(self) -> bool:
        return (
            self.uptime_pct is None
            and self.rpo_minutes is None
            and self.rto_minutes is None
        )


@dataclass(frozen=True)
class RnfContracts:
    """View imutável canônica dos RNF_CONTRACTS do OCG."""
    performance: PerformanceContract = field(default_factory=PerformanceContract)
    security: SecurityContract = field(default_factory=SecurityContract)
    compliance: tuple[ComplianceItem, ...] = ()
    availability: AvailabilityContract = field(default_factory=AvailabilityContract)

    @property
    def is_empty(self) -> bool:
        """True quando não há nenhum contrato declarado — codegen cai no default."""
        return (
            self.performance.is_empty
            and self.security.is_empty
            and not self.compliance
            and self.availability.is_empty
        )


# ─── Parsing ─────────────────────────────────────────────────────────


def from_ocg_dict(raw: Any) -> RnfContracts:
    """Converte `OCGResponse.RNF_CONTRACTS` (dict ou None) em view canônica.

    Tolerante a:
      - None, {} → retorna RnfContracts vazio
      - Campos ausentes → default
      - Campos com tipo errado → ignora silenciosamente (log no caller)
      - OCGs pré-23 (sem campo RNF_CONTRACTS) → retorna vazio

    Nunca levanta; sempre retorna RnfContracts válido.
    """
    if not isinstance(raw, dict):
        return RnfContracts()

    perf_raw = raw.get("performance") if isinstance(raw.get("performance"), dict) else {}
    sec_raw = raw.get("security") if isinstance(raw.get("security"), dict) else {}
    comp_raw = raw.get("compliance") if isinstance(raw.get("compliance"), list) else []
    avail_raw = raw.get("availability") if isinstance(raw.get("availability"), dict) else {}

    per_op = tuple(
        PerformanceOperation(op=str(x.get("op", "")), budget_ms=int(x.get("budget_ms", 0)))
        for x in (perf_raw.get("per_operation") or [])
        if isinstance(x, dict) and x.get("op") and x.get("budget_ms") is not None
    )

    performance = PerformanceContract(
        latency_p95_ms=_safe_int(perf_raw.get("latency_p95_ms")),
        throughput_rps=_safe_int(perf_raw.get("throughput_rps")),
        per_operation=per_op,
    )

    security = SecurityContract(
        required_cwe_protections=tuple(
            str(x) for x in (sec_raw.get("required_cwe_protections") or [])
            if isinstance(x, str) and x
        ),
        rate_limit_rpm_public=_safe_int(sec_raw.get("rate_limit_rpm_public")),
        rate_limit_rpm_authenticated=_safe_int(sec_raw.get("rate_limit_rpm_authenticated")),
        sensitive_data_categories=tuple(
            str(x) for x in (sec_raw.get("sensitive_data_categories") or [])
            if isinstance(x, str) and x
        ),
    )

    compliance = tuple(
        ComplianceItem(
            regulation=str(x.get("regulation", "")),
            requirement_id=str(x.get("requirement_id", "")),
            enforcement=_safe_enforcement(x.get("enforcement")),
        )
        for x in comp_raw
        if isinstance(x, dict) and x.get("regulation") and x.get("requirement_id")
    )

    availability = AvailabilityContract(
        uptime_pct=_safe_float(avail_raw.get("uptime_pct")),
        rpo_minutes=_safe_int(avail_raw.get("rpo_minutes")),
        rto_minutes=_safe_int(avail_raw.get("rto_minutes")),
    )

    return RnfContracts(
        performance=performance,
        security=security,
        compliance=compliance,
        availability=availability,
    )


# ─── Validação de entrada (endpoint PUT) ─────────────────────────────


@dataclass
class ValidationError:
    path: str
    message: str


def validate_contract_dict(raw: Any) -> list[ValidationError]:
    """Valida dict de entrada (ex: PUT endpoint) sem converter.

    Retorna lista de erros. Lista vazia = válido. Nunca levanta.

    Usado pela Fase 23.5 (UI) e endpoints que escrevem RNF_CONTRACTS
    para dar feedback canônico ao caller antes de persistir.
    """
    errors: list[ValidationError] = []

    if raw is None or raw == {}:
        return errors  # vazio é válido

    if not isinstance(raw, dict):
        errors.append(ValidationError(path="$", message="RNF_CONTRACTS deve ser dict"))
        return errors

    allowed_roots = {"performance", "security", "compliance", "availability"}
    for key in raw.keys():
        if key not in allowed_roots:
            errors.append(ValidationError(
                path=f"$.{key}",
                message=f"chave canônica desconhecida (aceitas: {sorted(allowed_roots)})",
            ))

    if "performance" in raw:
        errors.extend(_validate_performance(raw["performance"]))
    if "security" in raw:
        errors.extend(_validate_security(raw["security"]))
    if "compliance" in raw:
        errors.extend(_validate_compliance(raw["compliance"]))
    if "availability" in raw:
        errors.extend(_validate_availability(raw["availability"]))

    return errors


# ─── Extractors pro consumidor downstream ────────────────────────────


def contract_as_prompt_block(rnf: RnfContracts) -> str:
    """Formata contrato canônico como bloco de instruções pro LLM (Fase 23.3).

    Retorna string vazia quando rnf.is_empty — caller pula bloco.
    """
    if rnf.is_empty:
        return ""

    lines: list[str] = ["## Requisitos Não-Funcionais (contrato obrigatório)"]

    p = rnf.performance
    if not p.is_empty:
        lines.append("")
        lines.append("### Performance")
        if p.latency_p95_ms is not None:
            lines.append(f"- Latência P95 máxima: **{p.latency_p95_ms} ms** (endpoint-padrão).")
        if p.throughput_rps is not None:
            lines.append(f"- Throughput esperado: **{p.throughput_rps} req/s** sustentado.")
        for op in p.per_operation:
            lines.append(f"- Operação `{op.op}`: budget **{op.budget_ms} ms**.")

    s = rnf.security
    if not s.is_empty:
        lines.append("")
        lines.append("### Segurança")
        if s.required_cwe_protections:
            lines.append(
                f"- Proteções obrigatórias contra: "
                f"{', '.join(s.required_cwe_protections)}."
            )
        if s.rate_limit_rpm_public is not None:
            lines.append(f"- Rate limit público: **{s.rate_limit_rpm_public} req/min** por cliente.")
        if s.rate_limit_rpm_authenticated is not None:
            lines.append(
                f"- Rate limit autenticado: **{s.rate_limit_rpm_authenticated} req/min** por user."
            )
        if s.sensitive_data_categories:
            lines.append(
                f"- Categorias de dado sensível: {', '.join(s.sensitive_data_categories)} "
                f"(nunca logar, sempre encrypted em repouso)."
            )

    if rnf.compliance:
        lines.append("")
        lines.append("### Compliance")
        for c in rnf.compliance:
            lines.append(
                f"- {c.regulation} / {c.requirement_id} "
                f"(enforcement: `{c.enforcement}`)."
            )

    a = rnf.availability
    if not a.is_empty:
        lines.append("")
        lines.append("### Disponibilidade")
        if a.uptime_pct is not None:
            lines.append(f"- SLA de uptime: **{a.uptime_pct}%**.")
        if a.rpo_minutes is not None:
            lines.append(f"- RPO (tolerância de perda): **{a.rpo_minutes} min**.")
        if a.rto_minutes is not None:
            lines.append(f"- RTO (tempo de recuperação): **{a.rto_minutes} min**.")

    lines.append("")
    lines.append(
        "> **O código gerado DEVE documentar no docstring qual(is) contrato(s) "
        "está atendendo** (ex: `Atende: security.rate_limit_rpm_public=60, "
        "security.CWE-89 via ORM`)."
    )
    return "\n".join(lines)


def extract_static_checks(rnf: RnfContracts) -> list[dict[str, Any]]:
    """Lista de checks estáticos pós-geração (Fase 23.4).

    Cada check é um dict com:
      - `id`: identificador canônico
      - `label`: descrição humana
      - `patterns`: lista de regex/strings que precisam aparecer no código
        (qualquer match de qualquer padrão satisfaz)
      - `scope`: "per_file" | "any_file_in_module"
      - `severity`: "blocker" | "warning"

    Retorna lista vazia quando rnf.is_empty.
    """
    checks: list[dict[str, Any]] = []

    s = rnf.security
    if s.rate_limit_rpm_public is not None or s.rate_limit_rpm_authenticated is not None:
        checks.append({
            "id": "rate_limit_middleware",
            "label": "Middleware de rate limiting presente",
            "patterns": [
                r"slowapi|Limiter|RateLimiter|express-rate-limit|@RateLimit",
            ],
            "scope": "any_file_in_module",
            "severity": "blocker",
        })

    for cwe in s.required_cwe_protections:
        cwe_id = cwe.upper().replace("CWE-", "")
        if cwe_id == "89":
            checks.append({
                "id": f"cwe_{cwe_id}_sql_injection",
                "label": f"{cwe}: SQL parametrizado (sem concat de string)",
                "patterns": [
                    # positivo — padrões canônicos de query parametrizada
                    r"text\(.*:\w+.*\)",  # SQLAlchemy text com :param
                    r"execute\(.*,\s*\{",  # execute(sql, {params})
                    r"select\(",           # SQLAlchemy select
                    r"\?\s*,\s*\(",        # sqlite3 ?/execute
                ],
                "scope": "per_file",
                "severity": "blocker",
            })
        elif cwe_id == "79":
            checks.append({
                "id": f"cwe_{cwe_id}_xss",
                "label": f"{cwe}: escape de output HTML",
                "patterns": [
                    r"escape\(|Markup\(|bleach\.|html\.escape",
                ],
                "scope": "per_file",
                "severity": "warning",
            })
        elif cwe_id == "798":
            checks.append({
                "id": f"cwe_{cwe_id}_hardcoded_credentials",
                "label": f"{cwe}: segredos vêm do vault, não hardcoded",
                "patterns": [
                    r"VaultService|os\.environ|settings\.",
                ],
                "scope": "per_file",
                "severity": "blocker",
            })

    if s.sensitive_data_categories:
        checks.append({
            "id": "sensitive_data_not_logged",
            "label": "Dado sensível não aparece em logger.info/print",
            # padrões NEGATIVOS (encontrar = fail). Implementação do validator
            # usa esta info como anti-pattern; convenção: prefixo `!` indica
            # "não deve aparecer". Validator interpreta e inverte.
            "patterns": ["!logger\\.info.*password", "!print.*token"],
            "scope": "per_file",
            "severity": "blocker",
        })

    return checks


def extract_test_scenarios(rnf: RnfContracts) -> list[dict[str, Any]]:
    """Cenários de teste RNF pro test_spec_generator (Fase 23.4).

    Cada cenário:
      - `id`: canônico
      - `kind`: "latency" | "rate_limit" | "security_regression" | "compliance"
      - `description`: humano
      - `assertion_template`: sugestão de asserção (string)
    """
    scenarios: list[dict[str, Any]] = []

    p = rnf.performance
    if p.latency_p95_ms is not None:
        scenarios.append({
            "id": "latency_p95",
            "kind": "latency",
            "description": f"P95 do endpoint deve ser ≤ {p.latency_p95_ms} ms",
            "assertion_template": f"assert p95_ms <= {p.latency_p95_ms}",
        })
    for op in p.per_operation:
        scenarios.append({
            "id": f"latency_{op.op.replace(' ', '_').replace('/', '_').strip('_')}",
            "kind": "latency",
            "description": f"Operação '{op.op}' deve ser ≤ {op.budget_ms} ms",
            "assertion_template": f"assert duration_ms <= {op.budget_ms}",
        })

    s = rnf.security
    if s.rate_limit_rpm_public is not None:
        scenarios.append({
            "id": "rate_limit_public",
            "kind": "rate_limit",
            "description": (
                f"Excesso de {s.rate_limit_rpm_public} req/min público "
                f"retorna HTTP 429"
            ),
            "assertion_template": "assert response.status_code == 429",
        })
    for cwe in s.required_cwe_protections:
        scenarios.append({
            "id": f"security_regression_{cwe.lower().replace('-', '_')}",
            "kind": "security_regression",
            "description": f"Regressão: {cwe} não é reintroduzido",
            "assertion_template": "# teste específico pela natureza do CWE",
        })

    for c in rnf.compliance:
        scenarios.append({
            "id": f"compliance_{c.regulation}_{c.requirement_id}".lower().replace(".", "_"),
            "kind": "compliance",
            "description": (
                f"Atende {c.regulation}/{c.requirement_id} "
                f"(enforcement: {c.enforcement})"
            ),
            "assertion_template": "# validado via SAST + teste de integração",
        })

    return scenarios


# ─── Privates ────────────────────────────────────────────────────────


def _safe_int(v: Any) -> Optional[int]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _safe_float(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _safe_enforcement(v: Any) -> EnforcementMode:
    if v in ("runtime", "static", "both"):
        return v
    return "both"


def _validate_performance(raw: Any) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if raw is None:
        return errors
    if not isinstance(raw, dict):
        errors.append(ValidationError(path="$.performance", message="deve ser dict"))
        return errors
    for key in ("latency_p95_ms", "throughput_rps"):
        if key in raw and raw[key] is not None:
            v = raw[key]
            if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
                errors.append(ValidationError(
                    path=f"$.performance.{key}",
                    message=f"deve ser número ≥ 0, recebido {type(v).__name__}",
                ))
    if "per_operation" in raw:
        po = raw["per_operation"]
        if not isinstance(po, list):
            errors.append(ValidationError(
                path="$.performance.per_operation", message="deve ser lista",
            ))
        else:
            for i, item in enumerate(po):
                if not isinstance(item, dict) or "op" not in item or "budget_ms" not in item:
                    errors.append(ValidationError(
                        path=f"$.performance.per_operation[{i}]",
                        message="cada item precisa de {op, budget_ms}",
                    ))
    return errors


def _validate_security(raw: Any) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if raw is None:
        return errors
    if not isinstance(raw, dict):
        errors.append(ValidationError(path="$.security", message="deve ser dict"))
        return errors
    for key in ("rate_limit_rpm_public", "rate_limit_rpm_authenticated"):
        if key in raw and raw[key] is not None:
            v = raw[key]
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                errors.append(ValidationError(
                    path=f"$.security.{key}",
                    message=f"deve ser int ≥ 0, recebido {type(v).__name__}",
                ))
    for list_key in ("required_cwe_protections", "sensitive_data_categories"):
        if list_key in raw:
            v = raw[list_key]
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                errors.append(ValidationError(
                    path=f"$.security.{list_key}",
                    message="deve ser lista de strings",
                ))
    return errors


def _validate_compliance(raw: Any) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if raw is None:
        return errors
    if not isinstance(raw, list):
        errors.append(ValidationError(path="$.compliance", message="deve ser lista"))
        return errors
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(ValidationError(
                path=f"$.compliance[{i}]", message="item deve ser dict",
            ))
            continue
        for req in ("regulation", "requirement_id"):
            if not item.get(req):
                errors.append(ValidationError(
                    path=f"$.compliance[{i}].{req}",
                    message="campo obrigatório",
                ))
        enf = item.get("enforcement")
        if enf is not None and enf not in ("runtime", "static", "both"):
            errors.append(ValidationError(
                path=f"$.compliance[{i}].enforcement",
                message="deve ser 'runtime', 'static' ou 'both'",
            ))
    return errors


def _validate_availability(raw: Any) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if raw is None:
        return errors
    if not isinstance(raw, dict):
        errors.append(ValidationError(path="$.availability", message="deve ser dict"))
        return errors
    if "uptime_pct" in raw and raw["uptime_pct"] is not None:
        v = raw["uptime_pct"]
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0 or v > 100:
            errors.append(ValidationError(
                path="$.availability.uptime_pct",
                message="deve ser número entre 0 e 100",
            ))
    for key in ("rpo_minutes", "rto_minutes"):
        if key in raw and raw[key] is not None:
            v = raw[key]
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                errors.append(ValidationError(
                    path=f"$.availability.{key}",
                    message=f"deve ser int ≥ 0",
                ))
    return errors
