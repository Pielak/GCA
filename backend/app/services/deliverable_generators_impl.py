"""Implementações concretas dos auto-generators (C.2 + C.3 + C.4).

Cada generator é decorado com @register_generator e produz um artefato
markdown/mermaid/etc. a partir de campos do OCG. Determinístico (sem LLM)
para começar — mantém o pipeline rápido e auditável.

Convenção de paths gerados:
    docs/compliance.md           (compliance_doc)
    docs/architecture.mmd        (architecture_diagram)
    docs/adr/000N-<slug>.md      (adr — 1 por CRITICAL_FINDING)

Idempotência: cada generator inclui um header gerado com ``<!-- gca:auto -->``.
Caller pode escolher sobrescrever ou pular se header não bate (TODO Fase D).
Por enquanto sobrescreve — consciente trade-off para iteração rápida no
dogfood.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.deliverable_generators import (
    GeneratorResult,
    _commit_via_git,
    register_generator,
)


def _slugify(text: str, max_len: int = 60) -> str:
    """Slug ASCII para nomes de arquivo (ADR)."""
    s = unicodedata.normalize("NFD", text or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", s).lower().strip()
    s = re.sub(r"\s+", "-", s)
    return (s or "sem-titulo")[:max_len].rstrip("-")


# ────────────────────── compliance_doc ────────────────────────────────

@register_generator("compliance_doc")
@register_generator("compliance_checklist")
async def _gen_compliance_doc(
    project_id: UUID,
    db: AsyncSession,
    ocg_data: Dict[str, Any],
) -> GeneratorResult:
    """Gera ``docs/compliance.md`` com tabela de items do OCG.COMPLIANCE_CHECKLIST."""
    items = ocg_data.get("COMPLIANCE_CHECKLIST", []) or []
    if not isinstance(items, list) or not items:
        return GeneratorResult(
            kind="compliance_doc",
            committed=False,
            skipped_reason="OCG.COMPLIANCE_CHECKLIST vazio",
        )

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    project_name = ocg_data.get("PROJECT_PROFILE", {}).get("project_name", "(projeto)")

    lines: List[str] = [
        "<!-- gca:auto generator=compliance_doc -->",
        f"# Checklist de Compliance — {project_name}",
        "",
        f"_Gerado automaticamente em {now_iso} a partir de OCG.COMPLIANCE_CHECKLIST._",
        "",
        f"**Total**: {len(items)} item(s) — "
        f"**resolvidos**: {sum(1 for i in items if str(i.get('status', '')).upper() != 'PENDENTE')} | "
        f"**pendentes**: {sum(1 for i in items if str(i.get('status', '')).upper() == 'PENDENTE')}",
        "",
        "| # | Item | Status | Responsável |",
        "|---|------|--------|-------------|",
    ]
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        text = (item.get("item") or "").replace("|", "\\|")
        status = (item.get("status") or "PENDENTE").upper()
        owner = (item.get("owner") or "—").replace("|", "\\|")
        status_badge = "✅" if status != "PENDENTE" else "⏳"
        lines.append(f"| {idx} | {text} | {status_badge} {status} | {owner} |")

    content = "\n".join(lines) + "\n"
    path = "docs/compliance.md"

    ok = await _commit_via_git(
        project_id, db, path, content,
        commit_message=f"docs(compliance): regenerar checklist ({len(items)} items) [gca:auto]",
    )
    if not ok:
        return GeneratorResult(
            kind="compliance_doc",
            committed=False,
            skipped_reason="commit Git falhou (ver logs)",
        )
    return GeneratorResult(
        kind="compliance_doc",
        committed=True,
        path=path,
        bytes_written=len(content.encode("utf-8")),
        notes=f"{len(items)} items processados",
    )


# ────────────────────── adr ────────────────────────────────────────────

@register_generator("adr")
async def _gen_adr(
    project_id: UUID,
    db: AsyncSession,
    ocg_data: Dict[str, Any],
) -> GeneratorResult:
    """Gera ``docs/adr/0001-*.md`` para cada CRITICAL_FINDING + 1 ADR de stack.

    Formato MADR (Markdown Architecture Decision Records) simplificado.
    Cada finding crítico vira um ADR — facilita rastreabilidade decisão→risco.
    """
    findings_raw = ocg_data.get("CRITICAL_FINDINGS")
    # CRITICAL_FINDINGS pode ser dict ou list (varia entre versões do OCG)
    findings: List[Dict[str, Any]] = []
    if isinstance(findings_raw, list):
        findings = [f for f in findings_raw if isinstance(f, dict)]
    elif isinstance(findings_raw, dict):
        findings = [findings_raw]

    stack = ocg_data.get("STACK_RECOMMENDATION", {}) or {}
    project_name = ocg_data.get("PROJECT_PROFILE", {}).get("project_name", "(projeto)")
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if not findings and not stack:
        return GeneratorResult(
            kind="adr",
            committed=False,
            skipped_reason="OCG sem CRITICAL_FINDINGS nem STACK_RECOMMENDATION",
        )

    written = 0
    total_bytes = 0

    # ADR 0001: Stack Decision (se há stack)
    if stack:
        slug = "stack-recommendation"
        path = f"docs/adr/0001-{slug}.md"
        backend = stack.get("backend", {})
        frontend = stack.get("frontend", {})
        database = stack.get("database", {})
        content = (
            f"<!-- gca:auto generator=adr -->\n"
            f"# 0001. Stack tecnológica recomendada\n\n"
            f"- **Status:** Aceito\n"
            f"- **Data:** {now_iso}\n"
            f"- **Projeto:** {project_name}\n\n"
            f"## Contexto\n\n"
            f"O OCG do projeto definiu a stack inicial baseada em pilares "
            f"avaliados via Arguidor. Esta decisão consolida as escolhas para "
            f"frontend, backend e persistência.\n\n"
            f"## Decisão\n\n"
            f"- **Backend**: {backend.get('framework', '?')} "
            f"({backend.get('language', '?')})\n"
            f"- **Frontend**: {frontend.get('framework', '?')} "
            f"({frontend.get('language', '?')})\n"
            f"- **Database**: {database.get('primary', '?')}\n\n"
            f"## Justificativas (do OCG.STACK_RECOMMENDATION)\n\n"
            f"- Backend: {backend.get('rationale', 'N/A')}\n"
            f"- Frontend: {frontend.get('rationale', 'N/A')}\n"
            f"- Database: {database.get('rationale', 'N/A')}\n\n"
            f"## Consequências\n\n"
            f"Mudanças nesta stack devem ser registradas como novos ADRs "
            f"superseding este, com trigger no OCG.\n"
        )
        if await _commit_via_git(
            project_id, db, path, content,
            commit_message="docs(adr): 0001 stack recommendation [gca:auto]",
        ):
            written += 1
            total_bytes += len(content.encode("utf-8"))

    # ADRs 0002+: 1 por CRITICAL_FINDING
    for idx, finding in enumerate(findings, start=2):
        title = finding.get("finding", "")[:80] or f"Finding crítico {idx}"
        slug = _slugify(title, max_len=50)
        path = f"docs/adr/{idx:04d}-{slug}.md"
        severity = (finding.get("severity") or "?").upper()
        pillar = finding.get("pillar") or "?"
        recommendation = finding.get("recommendation") or "(sem recomendação)"

        content = (
            f"<!-- gca:auto generator=adr -->\n"
            f"# {idx:04d}. {title}\n\n"
            f"- **Status:** Proposto\n"
            f"- **Data:** {now_iso}\n"
            f"- **Pilar afetado:** {pillar}\n"
            f"- **Severidade:** {severity}\n\n"
            f"## Contexto\n\n"
            f"Finding crítico identificado pelo Arguidor durante análise do projeto:\n\n"
            f"> {finding.get('finding', 'N/A')}\n\n"
            f"## Decisão\n\n"
            f"{recommendation}\n\n"
            f"## Consequências\n\n"
            f"O Gatekeeper bloqueará progressão para CodeGen enquanto este "
            f"finding estiver `PENDENTE`. Marcar como resolvido apenas após "
            f"implementação verificável (e atualizar este ADR para `Aceito`).\n"
        )
        if await _commit_via_git(
            project_id, db, path, content,
            commit_message=f"docs(adr): {idx:04d} {slug} [gca:auto]",
        ):
            written += 1
            total_bytes += len(content.encode("utf-8"))

    if written == 0:
        return GeneratorResult(
            kind="adr",
            committed=False,
            skipped_reason="todos commits Git falharam",
        )
    return GeneratorResult(
        kind="adr",
        committed=True,
        path=f"docs/adr/ ({written} arquivos)",
        bytes_written=total_bytes,
        notes=f"{written} ADRs gerados (1 stack + {written-1 if stack else written} findings)",
    )


# ────────────────────── architecture_diagram (mermaid C4) ──────────────

@register_generator("sbom")
async def _gen_sbom(
    project_id: UUID,
    db: AsyncSession,
    ocg_data: Dict[str, Any],
) -> GeneratorResult:
    """Gera ``sbom.json`` (CycloneDX 1.5) a partir de pyproject.toml e/ou
    package.json lidos do repo Git.

    Não roda ferramentas externas — parseia os manifests diretamente.
    Cobre Python (poetry/pep621) + Node (package.json deps + devDeps).

    Para projetos com requirements.txt ou outros formatos, retorna skipped.
    """
    from app.services.git_service import GitService
    gs = GitService(db)

    components: List[Dict[str, Any]] = []
    sources_found: List[str] = []

    # Python: pyproject.toml (Poetry ou PEP 621)
    pyproject_paths = ["pyproject.toml", "backend/pyproject.toml"]
    py_content: Optional[str] = None
    py_path: Optional[str] = None
    for p in pyproject_paths:
        try:
            content = await gs.get_file_content(project_id, p)
            if content:
                py_content = content
                py_path = p
                break
        except Exception:  # noqa: BLE001
            continue

    if py_content:
        try:
            import tomllib
            parsed = tomllib.loads(py_content)
            # Poetry: tool.poetry.dependencies / tool.poetry.group.dev.dependencies
            poetry_deps = (
                parsed.get("tool", {}).get("poetry", {}).get("dependencies", {})
            )
            poetry_dev = (
                parsed.get("tool", {}).get("poetry", {}).get("group", {})
                .get("dev", {}).get("dependencies", {})
            )
            for name, spec in {**poetry_deps, **poetry_dev}.items():
                if name.lower() == "python":
                    continue
                version = spec if isinstance(spec, str) else (spec.get("version", "*") if isinstance(spec, dict) else "*")
                components.append({
                    "type": "library",
                    "bom-ref": f"pkg:pypi/{name}@{version}",
                    "name": name,
                    "version": str(version).lstrip("^~>=<"),
                    "purl": f"pkg:pypi/{name}@{str(version).lstrip('^~>=<')}",
                })
            # PEP 621: project.dependencies (lista de strings 'name>=version')
            for dep_str in parsed.get("project", {}).get("dependencies", []) or []:
                if not isinstance(dep_str, str):
                    continue
                # Parser muito simples: 'name>=1.0' → ('name', '1.0')
                m = re.match(r"^([A-Za-z0-9_.\-]+)[\s]*[>=<~!]*[\s]*([0-9].*)?", dep_str)
                if m:
                    name = m.group(1)
                    version = m.group(2) or "*"
                    components.append({
                        "type": "library",
                        "bom-ref": f"pkg:pypi/{name}@{version}",
                        "name": name,
                        "version": version,
                        "purl": f"pkg:pypi/{name}@{version}",
                    })
            sources_found.append(py_path or "pyproject.toml")
        except Exception as exc:  # noqa: BLE001
            # Parse falhou — pula sem derrubar generator inteiro
            pass

    # Node: package.json
    pkg_paths = ["package.json", "frontend/package.json"]
    pkg_content: Optional[str] = None
    pkg_path: Optional[str] = None
    for p in pkg_paths:
        try:
            content = await gs.get_file_content(project_id, p)
            if content:
                pkg_content = content
                pkg_path = p
                break
        except Exception:  # noqa: BLE001
            continue

    if pkg_content:
        try:
            pkg_parsed = json.loads(pkg_content)
            for name, version in {
                **(pkg_parsed.get("dependencies", {}) or {}),
                **(pkg_parsed.get("devDependencies", {}) or {}),
            }.items():
                ver_clean = str(version).lstrip("^~>=<")
                components.append({
                    "type": "library",
                    "bom-ref": f"pkg:npm/{name}@{ver_clean}",
                    "name": name,
                    "version": ver_clean,
                    "purl": f"pkg:npm/{name}@{ver_clean}",
                })
            sources_found.append(pkg_path or "package.json")
        except Exception:  # noqa: BLE001
            pass

    if not components:
        return GeneratorResult(
            kind="sbom",
            committed=False,
            skipped_reason="nenhum manifest encontrado no repo (pyproject.toml/package.json) ou parse falhou",
        )

    project_name = ocg_data.get("PROJECT_PROFILE", {}).get("project_name", "(projeto)")
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{project_id}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tools": [{"vendor": "GCA", "name": "deliverable_generator_sbom", "version": "1.0"}],
            "component": {
                "type": "application",
                "name": project_name,
                "bom-ref": f"app:{project_id}",
            },
        },
        "components": components,
        "_metadata": {
            "sources": sources_found,
            "note": "Gerado pelo GCA via parse direto de manifests (sem cyclonedx-cli). Para SBOM completo com transitive deps, rodar cyclonedx-bom no CI.",
        },
    }

    content = json.dumps(bom, ensure_ascii=False, indent=2) + "\n"
    path = "sbom.json"

    ok = await _commit_via_git(
        project_id, db, path, content,
        commit_message=f"chore(sbom): CycloneDX 1.5 ({len(components)} componentes de {len(sources_found)} manifests) [gca:auto]",
    )
    if not ok:
        return GeneratorResult(kind="sbom", committed=False, skipped_reason="commit Git falhou")
    return GeneratorResult(
        kind="sbom", committed=True, path=path,
        bytes_written=len(content.encode("utf-8")),
        notes=f"{len(components)} componentes de {sources_found}",
    )


@register_generator("test_plan")
async def _gen_test_plan(
    project_id: UUID,
    db: AsyncSession,
    ocg_data: Dict[str, Any],
) -> GeneratorResult:
    """Gera ``docs/test_plan.md`` a partir de OCG.TESTING_REQUIREMENTS.

    O OCG já estrutura testes em modalidades (unit, integration, security,
    performance, compliance, end_to_end). Cada modalidade tem campos
    variáveis (scope, tools, coverage_target, frequency, scenarios, method,
    rationale). Geramos uma seção MD por modalidade, listando todos os
    campos presentes.

    Sem LLM — todo dado vem do OCG.
    """
    testing = ocg_data.get("TESTING_REQUIREMENTS", {}) or {}
    if not testing or not isinstance(testing, dict):
        return GeneratorResult(
            kind="test_plan",
            committed=False,
            skipped_reason="OCG.TESTING_REQUIREMENTS vazio ou inválido",
        )

    project_name = ocg_data.get("PROJECT_PROFILE", {}).get("project_name", "(projeto)")
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Ordem de exibição (mais comuns primeiro), com fallback alfabético para outros
    ordered_keys = [
        "unit_testing", "integration_testing", "end_to_end_testing",
        "performance_testing", "security_testing", "compliance_testing",
    ]
    seen = set()
    sections_keys: list[str] = []
    for k in ordered_keys:
        if k in testing:
            sections_keys.append(k)
            seen.add(k)
    for k in sorted(testing.keys()):
        if k not in seen:
            sections_keys.append(k)

    lines: List[str] = [
        "<!-- gca:auto generator=test_plan -->",
        f"# Plano de Testes — {project_name}",
        "",
        f"_Gerado automaticamente em {now_iso} a partir de OCG.TESTING_REQUIREMENTS._",
        "",
        f"**{len(sections_keys)} modalidade(s) de teste definida(s).**",
        "",
        "## Sumário executivo",
        "",
        "| Modalidade | Tools | Coverage / Frequency |",
        "|------------|-------|----------------------|",
    ]
    for k in sections_keys:
        cfg = testing.get(k) if isinstance(testing.get(k), dict) else {}
        title = k.replace("_", " ").title()
        tools = (cfg.get("tools") or "—").replace("|", "\\|").replace("\n", " ")[:80]
        meta = (
            cfg.get("coverage_target")
            or cfg.get("frequency")
            or cfg.get("method")
            or "—"
        ).replace("|", "\\|").replace("\n", " ")[:80]
        lines.append(f"| {title} | {tools} | {meta} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Seções detalhadas
    for k in sections_keys:
        cfg = testing.get(k)
        if not isinstance(cfg, dict):
            lines.append(f"## {k.replace('_', ' ').title()}")
            lines.append("")
            lines.append(f"_Configuração inválida no OCG: {type(cfg).__name__}_")
            lines.append("")
            continue
        title = k.replace("_", " ").title()
        lines.append(f"## {title}")
        lines.append("")
        # Campos conhecidos primeiro, em ordem que faz sentido para leitura
        field_order = ["scope", "tools", "coverage_target", "frequency", "method", "scenarios", "rationale"]
        seen_fields = set()
        for field in field_order:
            if field in cfg:
                _format_field_md(lines, field, cfg[field])
                seen_fields.add(field)
        # Campos extras (futuros do OCG) ainda renderizados
        for field, val in cfg.items():
            if field not in seen_fields:
                _format_field_md(lines, field, val)
        lines.append("")

    content = "\n".join(lines) + "\n"
    path = "docs/test_plan.md"

    ok = await _commit_via_git(
        project_id, db, path, content,
        commit_message=f"docs(test): plano de testes ({len(sections_keys)} modalidades) [gca:auto]",
    )
    if not ok:
        return GeneratorResult(kind="test_plan", committed=False, skipped_reason="commit Git falhou")
    return GeneratorResult(
        kind="test_plan", committed=True, path=path,
        bytes_written=len(content.encode("utf-8")),
        notes=f"{len(sections_keys)} modalidades de teste",
    )


def _format_field_md(lines: List[str], field: str, value: Any) -> None:
    """Helper: formata um campo (scope/tools/etc.) como bloco MD legível."""
    label = field.replace("_", " ").title()
    if isinstance(value, str) and value.strip():
        lines.append(f"**{label}:** {value}")
        lines.append("")
    elif isinstance(value, list):
        lines.append(f"**{label}:**")
        for item in value:
            lines.append(f"- {item}")
        lines.append("")
    elif isinstance(value, dict):
        lines.append(f"**{label}:**")
        lines.append("")
        for sk, sv in value.items():
            lines.append(f"  - `{sk}`: {sv}")
        lines.append("")


@register_generator("dockerfile")
async def _gen_dockerfile(
    project_id: UUID,
    db: AsyncSession,
    ocg_data: Dict[str, Any],
) -> GeneratorResult:
    """Gera ``Dockerfile`` na raiz do repo, baseado em STACK.backend.

    Templates conhecidos: python/fastapi, node/express, go, java/spring.
    Para stacks não reconhecidas, retorna skipped (o GP escreve manual).
    """
    backend = (ocg_data.get("STACK_RECOMMENDATION", {}) or {}).get("backend", {}) or {}
    language = (backend.get("language") or "").lower().strip()
    framework = (backend.get("framework") or "").lower().strip()

    project_name = ocg_data.get("PROJECT_PROFILE", {}).get("project_name", "(projeto)")
    header = f"# Auto-gerado pelo GCA — não editar manualmente.\n# Projeto: {project_name}\n# Stack: {language} / {framework}\n"

    if language == "python":
        # FastAPI por padrão; ajustar se for Django/Flask exige diff
        port = "8000"
        if "django" in framework:
            cmd = "CMD [\"gunicorn\", \"-b\", \"0.0.0.0:8000\", \"app.wsgi:application\"]"
        elif "flask" in framework:
            cmd = "CMD [\"gunicorn\", \"-b\", \"0.0.0.0:8000\", \"app:app\"]"
        else:
            cmd = "CMD [\"uvicorn\", \"app.main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]"
        content = (
            header
            + "\nFROM python:3.11-slim\n\n"
            + "WORKDIR /app\n\n"
            + "RUN apt-get update && apt-get install -y --no-install-recommends \\\n"
            + "    build-essential libpq-dev && rm -rf /var/lib/apt/lists/*\n\n"
            + "COPY pyproject.toml ./\nRUN pip install --no-cache-dir poetry && poetry config virtualenvs.create false && poetry install --no-root --only main\n\n"
            + "COPY . .\n\n"
            + f"EXPOSE {port}\n\n"
            + f"{cmd}\n"
        )
    elif language in ("typescript", "javascript", "node"):
        content = (
            header
            + "\nFROM node:20-alpine\n\n"
            + "WORKDIR /app\n\n"
            + "COPY package.json package-lock.json* ./\nRUN npm ci --omit=dev\n\n"
            + "COPY . .\nRUN npm run build || true\n\n"
            + "EXPOSE 3000\n\n"
            + 'CMD ["npm", "start"]\n'
        )
    elif language == "go":
        content = (
            header
            + "\nFROM golang:1.22-alpine AS builder\nWORKDIR /src\nCOPY go.mod go.sum ./\nRUN go mod download\nCOPY . .\nRUN go build -o /out/app ./...\n\n"
            + "FROM gcr.io/distroless/base-debian12\nCOPY --from=builder /out/app /app\nEXPOSE 8080\nCMD [\"/app\"]\n"
        )
    elif language == "java":
        content = (
            header
            + "\nFROM eclipse-temurin:21-jdk-alpine AS builder\nWORKDIR /src\nCOPY . .\nRUN ./mvnw -B package -DskipTests || ./gradlew bootJar -x test\n\n"
            + "FROM eclipse-temurin:21-jre-alpine\nWORKDIR /app\nCOPY --from=builder /src/target/*.jar /app/app.jar\nEXPOSE 8080\nCMD [\"java\", \"-jar\", \"/app/app.jar\"]\n"
        )
    else:
        return GeneratorResult(
            kind="dockerfile",
            committed=False,
            skipped_reason=f"stack '{language}/{framework}' sem template Dockerfile conhecido",
        )

    path = "Dockerfile"
    ok = await _commit_via_git(
        project_id, db, path, content,
        commit_message=f"chore(docker): Dockerfile inicial para {language}/{framework} [gca:auto]",
    )
    if not ok:
        return GeneratorResult(kind="dockerfile", committed=False, skipped_reason="commit Git falhou")
    return GeneratorResult(
        kind="dockerfile", committed=True, path=path,
        bytes_written=len(content.encode("utf-8")),
        notes=f"template para {language}/{framework}",
    )


@register_generator("ci_pipeline")
async def _gen_ci_pipeline(
    project_id: UUID,
    db: AsyncSession,
    ocg_data: Dict[str, Any],
) -> GeneratorResult:
    """Gera ``.github/workflows/ci.yml`` com lint+test+build mínimos."""
    backend = (ocg_data.get("STACK_RECOMMENDATION", {}) or {}).get("backend", {}) or {}
    language = (backend.get("language") or "").lower().strip()
    project_name = ocg_data.get("PROJECT_PROFILE", {}).get("project_name", "project")

    # Steps por linguagem (mínimos viáveis)
    if language == "python":
        steps = (
            "      - name: Setup Python\n"
            "        uses: actions/setup-python@v5\n"
            "        with: { python-version: '3.11' }\n"
            "      - name: Install\n"
            "        run: pip install poetry && poetry install --no-root\n"
            "      - name: Lint\n"
            "        run: poetry run ruff check . || true\n"
            "      - name: Test\n"
            "        run: poetry run pytest -q || true\n"
        )
    elif language in ("typescript", "javascript", "node"):
        steps = (
            "      - name: Setup Node\n"
            "        uses: actions/setup-node@v4\n"
            "        with: { node-version: '20' }\n"
            "      - run: npm ci\n"
            "      - run: npm run lint --if-present\n"
            "      - run: npm test --if-present\n"
            "      - run: npm run build --if-present\n"
        )
    elif language == "go":
        steps = (
            "      - name: Setup Go\n"
            "        uses: actions/setup-go@v5\n"
            "        with: { go-version: '1.22' }\n"
            "      - run: go vet ./...\n"
            "      - run: go test ./...\n"
            "      - run: go build ./...\n"
        )
    elif language == "java":
        steps = (
            "      - name: Setup Java\n"
            "        uses: actions/setup-java@v4\n"
            "        with: { distribution: 'temurin', java-version: '21' }\n"
            "      - run: ./mvnw -B test || ./gradlew test\n"
        )
    else:
        return GeneratorResult(
            kind="ci_pipeline",
            committed=False,
            skipped_reason=f"stack '{language}' sem template CI conhecido",
        )

    content = (
        "# Auto-gerado pelo GCA — pipeline mínimo de CI.\n"
        f"# Projeto: {project_name}\n"
        f"name: CI\n\n"
        "on:\n"
        "  push:\n"
        "    branches: [main, master, develop]\n"
        "  pull_request:\n\n"
        "jobs:\n"
        "  test:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        + steps
    )
    path = ".github/workflows/ci.yml"
    ok = await _commit_via_git(
        project_id, db, path, content,
        commit_message=f"ci: pipeline inicial para {language} [gca:auto]",
    )
    if not ok:
        return GeneratorResult(kind="ci_pipeline", committed=False, skipped_reason="commit Git falhou")
    return GeneratorResult(
        kind="ci_pipeline", committed=True, path=path,
        bytes_written=len(content.encode("utf-8")),
        notes=f"workflow GitHub Actions ({language})",
    )


@register_generator("openapi")
async def _gen_openapi_stub(
    project_id: UUID,
    db: AsyncSession,
    ocg_data: Dict[str, Any],
) -> GeneratorResult:
    """Gera ``docs/openapi.yaml`` stub mínimo (skeleton para iteração).

    Frameworks como FastAPI já geram OpenAPI em runtime — este stub serve
    como contrato versionado em Git, útil para revisão de API e clientes
    gerados antes de o backend estar rodando.
    """
    project_name = ocg_data.get("PROJECT_PROFILE", {}).get("project_name", "API")
    backend = (ocg_data.get("STACK_RECOMMENDATION", {}) or {}).get("backend", {}) or {}
    framework = backend.get("framework", "")

    content = (
        "# Auto-gerado pelo GCA — stub inicial.\n"
        "# Frameworks como FastAPI/NestJS geram OpenAPI em runtime; este arquivo\n"
        "# serve como contrato versionado para revisão antes do código.\n"
        "openapi: 3.1.0\n"
        "info:\n"
        f"  title: {project_name} API\n"
        "  version: 0.1.0\n"
        f"  description: |\n"
        f"    API gerada inicialmente pelo GCA para {project_name}.\n"
        f"    Stack: {framework}. Substituir endpoints abaixo conforme implementação.\n"
        "servers:\n"
        "  - url: http://localhost:8000\n"
        "    description: Local dev\n"
        "paths:\n"
        "  /health:\n"
        "    get:\n"
        "      summary: Health check\n"
        "      responses:\n"
        "        '200':\n"
        "          description: OK\n"
        "          content:\n"
        "            application/json:\n"
        "              schema:\n"
        "                type: object\n"
        "                properties:\n"
        "                  status: { type: string, example: ok }\n"
        "components:\n"
        "  schemas: {}\n"
    )
    path = "docs/openapi.yaml"
    ok = await _commit_via_git(
        project_id, db, path, content,
        commit_message=f"docs(api): OpenAPI 3.1 stub inicial [gca:auto]",
    )
    if not ok:
        return GeneratorResult(kind="openapi", committed=False, skipped_reason="commit Git falhou")
    return GeneratorResult(
        kind="openapi", committed=True, path=path,
        bytes_written=len(content.encode("utf-8")),
        notes="stub OpenAPI 3.1 com endpoint /health",
    )


@register_generator("observability_dashboard")
async def _gen_observability(
    project_id: UUID,
    db: AsyncSession,
    ocg_data: Dict[str, Any],
) -> GeneratorResult:
    """Gera ``infra/grafana/dashboards/main.json`` skeleton + ``infra/prometheus.yml``.

    Skeleton mínimo permite scrape básico (latência, throughput, erros 5xx
    via /metrics se exposed). GP customiza após.
    """
    project_name = ocg_data.get("PROJECT_PROFILE", {}).get("project_name", "project")
    project_slug = re.sub(r"[^a-z0-9_]", "_", project_name.lower())[:30] or "project"

    prom = (
        "# Auto-gerado pelo GCA — scrape config inicial.\n"
        "global:\n"
        "  scrape_interval: 15s\n"
        "  evaluation_interval: 15s\n\n"
        "scrape_configs:\n"
        f"  - job_name: '{project_slug}'\n"
        "    static_configs:\n"
        "      - targets: ['backend:8000']\n"
        "    metrics_path: /metrics\n"
    )

    grafana = json.dumps({
        "title": f"{project_name} — Visão Geral",
        "schemaVersion": 41,
        "tags": ["gca:auto"],
        "panels": [
            {
                "id": 1, "type": "timeseries", "title": "Requests/sec",
                "datasource": "Prometheus",
                "targets": [{"expr": f'rate(http_requests_total{{job="{project_slug}"}}[5m])'}],
                "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8},
            },
            {
                "id": 2, "type": "timeseries", "title": "Latência p95 (s)",
                "datasource": "Prometheus",
                "targets": [{"expr": f'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{{job="{project_slug}"}}[5m])) by (le))'}],
                "gridPos": {"x": 12, "y": 0, "w": 12, "h": 8},
            },
            {
                "id": 3, "type": "stat", "title": "Erros 5xx (1h)",
                "datasource": "Prometheus",
                "targets": [{"expr": f'sum(increase(http_requests_total{{job="{project_slug}",status=~"5.."}}[1h]))'}],
                "gridPos": {"x": 0, "y": 8, "w": 6, "h": 4},
            },
        ],
    }, ensure_ascii=False, indent=2) + "\n"

    # Commit em duas chamadas (git_service.commit_file processa um por vez)
    ok1 = await _commit_via_git(
        project_id, db, "infra/prometheus.yml", prom,
        commit_message="infra(observability): prometheus scrape config [gca:auto]",
    )
    ok2 = await _commit_via_git(
        project_id, db, "infra/grafana/dashboards/main.json", grafana,
        commit_message="infra(observability): grafana dashboard inicial [gca:auto]",
    )
    if not (ok1 or ok2):
        return GeneratorResult(kind="observability_dashboard", committed=False, skipped_reason="commits Git falharam")
    bytes_written = (len(prom.encode("utf-8")) if ok1 else 0) + (len(grafana.encode("utf-8")) if ok2 else 0)
    paths_ok = []
    if ok1: paths_ok.append("infra/prometheus.yml")
    if ok2: paths_ok.append("infra/grafana/dashboards/main.json")
    return GeneratorResult(
        kind="observability_dashboard", committed=True,
        path=" + ".join(paths_ok),
        bytes_written=bytes_written,
        notes=f"prometheus scrape + grafana dashboard ({len(paths_ok)} arquivos)",
    )


@register_generator("architecture_diagram")
async def _gen_architecture_diagram(
    project_id: UUID,
    db: AsyncSession,
    ocg_data: Dict[str, Any],
) -> GeneratorResult:
    """Gera ``docs/architecture.mmd`` (mermaid) representando key_components do OCG."""
    arch = ocg_data.get("ARCHITECTURE_OVERVIEW", {}) or {}
    components: List[Any] = arch.get("key_components", []) or []
    style = arch.get("style", "(estilo não definido)")
    project_name = ocg_data.get("PROJECT_PROFILE", {}).get("project_name", "(projeto)")

    if not components:
        return GeneratorResult(
            kind="architecture_diagram",
            committed=False,
            skipped_reason="OCG.ARCHITECTURE_OVERVIEW.key_components vazio",
        )

    # Cada componente vira um node mermaid; conexões deduzidas via heurística
    # simples (frontend → backend → database). É melhor que nada — Fase C+
    # pode evoluir para LLM-augmented.
    nodes: List[str] = []
    edges: List[str] = []
    for idx, comp in enumerate(components, start=1):
        if not isinstance(comp, str):
            continue
        comp_clean = comp.replace('"', "'")[:80]
        node_id = f"C{idx}"
        # Heurística de classificação simples
        c_lower = comp.lower()
        if any(k in c_lower for k in ("frontend", "react", "vue", "spa", "ui")):
            shape = f'{node_id}["🖥️ {comp_clean}"]'
        elif any(k in c_lower for k in ("backend", "api", "fastapi", "service")):
            shape = f'{node_id}["⚙️ {comp_clean}"]'
        elif any(k in c_lower for k in ("postgres", "mysql", "database", "db", "redis")):
            shape = f'{node_id}[("🗄️ {comp_clean}")]'
        elif any(k in c_lower for k in ("kafka", "rabbitmq", "broker", "queue")):
            shape = f'{node_id}{{"📨 {comp_clean}"}}'
        else:
            shape = f'{node_id}["{comp_clean}"]'
        nodes.append(f"    {shape}")

    # Edges heurísticos: conecta nodes em sequência
    for i in range(1, len(nodes)):
        edges.append(f"    C{i} --> C{i+1}")

    diagram = (
        "%%{ init: { 'theme': 'dark' } }%%\n"
        "graph LR\n"
        f"    %% Auto-gerado pelo GCA — não editar manualmente.\n"
        f"    %% Style: {style}\n"
        + "\n".join(nodes)
        + "\n"
        + "\n".join(edges)
        + "\n"
    )
    header = f"<!-- gca:auto generator=architecture_diagram project={project_name} -->\n"
    content = header + diagram
    path = "docs/architecture.mmd"

    ok = await _commit_via_git(
        project_id, db, path, content,
        commit_message=f"docs(architecture): mermaid C4 ({len(nodes)} components) [gca:auto]",
    )
    if not ok:
        return GeneratorResult(
            kind="architecture_diagram",
            committed=False,
            skipped_reason="commit Git falhou",
        )
    return GeneratorResult(
        kind="architecture_diagram",
        committed=True,
        path=path,
        bytes_written=len(content.encode("utf-8")),
        notes=f"{len(nodes)} components no diagrama",
    )
