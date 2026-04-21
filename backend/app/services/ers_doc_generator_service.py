"""MVP 19 Fase 19.2 — Generator ERS (IEEE 830) + commit no Git do projeto.

Gera `docs/ERS.md` a partir do estado canônico do projeto no GCA
(OCG, module_candidates, external_repos) seguindo a estrutura IEEE 830-1998
e commita no repositório Git do projeto via `git_service` existente.

Em 19.2 isolado: seções 1.3 (glossário) e 4 (matriz de rastreabilidade)
saem com placeholder "será populado na próxima fase". Fases 19.3 e 19.4
completam cada uma dessas seções.

Histórico: não há tabela de snapshots — `git log -p docs/ERS.md` no repo
do projeto é o histórico canônico (decisão binária #5 do MVP 19).

Freshness: não há tabela dedicada — calculado ao vivo por diff entre
`LIVEDOCS_UPDATED` (último regen do ERS) e eventos posteriores que
impactam o conteúdo (`OCG_UPDATED`, `BACKLOG_REGENERATED`, etc).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    GlobalAuditLog,
    ModuleCandidate,
    OCG,
    Project,
    ProjectExternalRepo,
)
from app.services.audit_service import AuditEvents, AuditService
from app.services.git_service import GitService


logger = structlog.get_logger(__name__)


ERS_FILE_PATH = "docs/ERS.md"


# ============================================================================
# Freshness (ao vivo, via audit log — sem tabela dedicada)
# ============================================================================

# Eventos que impactam conteúdo do ERS quando acontecem após o último regen.
_STALE_TRIGGER_EVENTS: dict[str, str] = {
    AuditEvents.OCG_UPDATED: "OCG atualizado",
    AuditEvents.OCG_ROLLED_BACK: "OCG revertido",
    AuditEvents.OCG_CONSOLIDATED: "OCG consolidado",
    AuditEvents.BACKLOG_REGENERATED: "Backlog regenerado",
    AuditEvents.ARGUIDER_RESPONSE_REGISTERED: "Resposta do Arguidor registrada",
    AuditEvents.DOCUMENT_INGESTED: "Documento ingerido",
    AuditEvents.CODEGEN_SCAFFOLD_APPLIED: "Scaffold aplicado",
    AuditEvents.CODEGEN_FILE_REGENERATED: "Arquivo regenerado",
    AuditEvents.GATEKEEPER_EVALUATED: "Gatekeeper reavaliou",
}


async def get_ers_freshness(db: AsyncSession, project_id: UUID) -> dict:
    """Calcula o estado de frescor do ERS para um projeto.

    Retorna:
        {
            "is_stale": bool,
            "ever_generated": bool,
            "last_generated_at": ISO datetime | None,
            "last_commit_sha": str | None,
            "last_ocg_version": int | None,
            "stale_reasons": [{"event_type", "label", "since", "count"}],
        }

    Implementação: busca o último `LIVEDOCS_UPDATED` com `doc_type='ers'`
    no audit_log_global e conta eventos em `_STALE_TRIGGER_EVENTS`
    posteriores.
    """
    # Último regen do ERS.
    result = await db.execute(
        select(GlobalAuditLog)
        .where(
            GlobalAuditLog.event_type == AuditEvents.LIVEDOCS_UPDATED,
            GlobalAuditLog.resource_id == project_id,
        )
        .order_by(desc(GlobalAuditLog.created_at))
        .limit(20)  # amostra pra filtrar doc_type='ers' sem adicionar índice
    )
    last_ers_regen: Optional[GlobalAuditLog] = None
    for row in result.scalars().all():
        details = _parse_details(row.details)
        if details.get("doc_type") == "ers":
            last_ers_regen = row
            break

    last_generated_at = last_ers_regen.created_at if last_ers_regen else None
    last_commit_sha = None
    last_ocg_version = None
    if last_ers_regen is not None:
        details = _parse_details(last_ers_regen.details)
        last_commit_sha = details.get("commit_sha")
        last_ocg_version = details.get("version_to")

    # Eventos que marcam stale: posteriores ao último regen (ou todos, se
    # nunca gerado).
    stale_query = select(GlobalAuditLog).where(
        GlobalAuditLog.resource_id == project_id,
        GlobalAuditLog.event_type.in_(list(_STALE_TRIGGER_EVENTS.keys())),
    )
    if last_generated_at is not None:
        stale_query = stale_query.where(GlobalAuditLog.created_at > last_generated_at)
    stale_query = stale_query.order_by(desc(GlobalAuditLog.created_at)).limit(100)

    stale_rows = (await db.execute(stale_query)).scalars().all()

    # Agrupa por event_type pra não poluir o UI com duplicatas.
    counts: dict[str, dict] = {}
    for row in stale_rows:
        et = row.event_type
        if et not in counts:
            counts[et] = {
                "event_type": et,
                "label": _STALE_TRIGGER_EVENTS.get(et, et),
                "since": row.created_at.isoformat(),
                "count": 0,
            }
        counts[et]["count"] += 1

    stale_reasons = list(counts.values())
    is_stale = len(stale_reasons) > 0 or last_ers_regen is None

    return {
        "is_stale": is_stale,
        "ever_generated": last_ers_regen is not None,
        "last_generated_at": last_generated_at.isoformat() if last_generated_at else None,
        "last_commit_sha": last_commit_sha,
        "last_ocg_version": last_ocg_version,
        "stale_reasons": stale_reasons,
    }


def _parse_details(details_raw) -> dict:
    """Audit details é Text(JSON); parse defensivo."""
    if not details_raw:
        return {}
    if isinstance(details_raw, dict):
        return details_raw
    try:
        return json.loads(details_raw)
    except (TypeError, ValueError):
        return {}


# ============================================================================
# Coleta de dados
# ============================================================================

async def _load_ers_context(db: AsyncSession, project_id: UUID) -> dict[str, Any]:
    """Coleta tudo que o generator precisa num único pacote."""
    # Projeto
    proj_result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = proj_result.scalar_one_or_none()

    # OCG corrente (maior version)
    ocg_result = await db.execute(
        select(OCG)
        .where(OCG.project_id == project_id)
        .order_by(desc(OCG.version))
        .limit(1)
    )
    ocg = ocg_result.scalar_one_or_none()
    ocg_data: dict = {}
    ocg_version = None
    if ocg is not None:
        ocg_version = ocg.version
        if ocg.ocg_data:
            try:
                ocg_data = json.loads(ocg.ocg_data)
            except (TypeError, ValueError):
                ocg_data = {}

    # Módulos (categorizados e não-categorizados)
    mods_result = await db.execute(
        select(ModuleCandidate).where(ModuleCandidate.project_id == project_id)
    )
    modules = list(mods_result.scalars().all())

    # Repos externos
    repos_result = await db.execute(
        select(ProjectExternalRepo).where(ProjectExternalRepo.project_id == project_id)
    )
    external_repos = list(repos_result.scalars().all())

    return {
        "project": project,
        "ocg_version": ocg_version,
        "ocg_data": ocg_data,
        "modules": modules,
        "external_repos": external_repos,
    }


# ============================================================================
# Construção do markdown IEEE 830
# ============================================================================

async def build_ers_markdown(db: AsyncSession, project_id: UUID) -> str:
    """Consolida estado do projeto em um ERS IEEE 830 em markdown.

    Função pura-ish: lê DB mas não escreve. Útil em testes e preview.
    """
    ctx = await _load_ers_context(db, project_id)
    project = ctx["project"]
    ocg_data = ctx["ocg_data"]
    ocg_version = ctx["ocg_version"]
    modules: list[ModuleCandidate] = ctx["modules"]
    external_repos: list[ProjectExternalRepo] = ctx["external_repos"]

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    project_name = project.name if project else "(projeto sem nome)"
    project_slug = project.slug if project else "?"

    lines: list[str] = []
    lines.append(f"# ERS — Especificação de Requisitos de Software")
    lines.append("")
    lines.append(f"> **Projeto**: {project_name} (`{project_slug}`)  ")
    lines.append(f"> **Versão do OCG**: {ocg_version if ocg_version is not None else '—'}  ")
    lines.append(f"> **Gerado em**: {now_iso}  ")
    lines.append(f"> **Padrão**: IEEE 830-1998  ")
    lines.append(f"> **Fonte**: GCA — Gestão de Codificação Assistida")
    lines.append("")
    lines.append(
        "> Este documento é gerado automaticamente pelo GCA a partir do "
        "contexto canônico do projeto (OCG, backlog, testes, repositórios). "
        "O histórico de revisões vive no Git: `git log -p docs/ERS.md`."
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # ----------------- Seção 1 — Introdução -----------------
    lines.append("## 1. Introdução")
    lines.append("")

    # 1.1 Propósito
    lines.append("### 1.1 Propósito")
    lines.append("")
    profile = ocg_data.get("PROJECT_PROFILE") or {}
    # OCG profile vence sobre project.description porque o profile é
    # consolidado pelo Analyzer a partir do questionário inteiro (mais
    # rico que a linha que o GP escreveu ao criar o projeto).
    project_description = _first_non_empty(
        profile.get("description"),
        profile.get("business_description"),
        project.description if project else None,
    )
    if project_description:
        lines.append(project_description)
    else:
        lines.append("_(A ser preenchido a partir de ingestões e respostas do Arguidor.)_")
    lines.append("")

    # 1.2 Escopo
    lines.append("### 1.2 Escopo")
    lines.append("")
    deliverables = ocg_data.get("DELIVERABLES") or {}
    deliverables_list = _deliverables_as_list(deliverables)
    if deliverables_list:
        lines.append("**Entregáveis previstos:**")
        lines.append("")
        for d in deliverables_list:
            lines.append(f"- {d}")
    else:
        lines.append("_(A ser preenchido — entregáveis derivados do questionário e do roadmap.)_")
    lines.append("")

    # 1.3 Definições, Siglas e Abreviaturas (glossário vivo)
    lines.append("### 1.3 Definições, Siglas e Abreviaturas")
    lines.append("")
    # Import local pra evitar ciclo.
    from app.services.glossary_service import list_approved_for_ers

    approved_terms = await list_approved_for_ers(db, project_id)
    if approved_terms:
        lines.append(
            "Termos específicos deste projeto (aprovados pelo GP). Para acrônimos "
            "canônicos do GCA (OCG, RBAC, GP, P1–P7, etc), consulte o capítulo 1 "
            "do help global."
        )
        lines.append("")
        lines.append("| Termo | Definição |")
        lines.append("|---|---|")
        for t in approved_terms:
            raw_def = t.definition.strip() if t.definition else "_(sem definição — GP edita na aba Glossário)_"
            # Escapa pipes que quebram tabela markdown; colapsa quebras de linha.
            definition_escaped = raw_def.replace("|", "\\|").replace("\n", " ")
            term_escaped = t.term.replace("|", "\\|")
            lines.append(f"| **{term_escaped}** | {_truncate(definition_escaped, 300)} |")
        lines.append("")
    else:
        lines.append(
            "_Nenhum termo aprovado ainda. Rode a extração automática em "
            "`/projects/:id/docs` → aba Glossário e aprove os candidatos relevantes. "
            "Para acrônimos canônicos do GCA (OCG, RBAC, GP, P1–P7, etc), consulte "
            "o capítulo 1 do help global._"
        )
        lines.append("")

    # 1.4 Referências
    lines.append("### 1.4 Referências")
    lines.append("")
    refs: list[str] = []
    if external_repos:
        for repo in external_repos:
            refs.append(f"- Repositório externo: [{repo.repo_url}]({repo.repo_url}) (branch `{repo.branch}`)")
    if profile.get("references"):
        for r in _as_list(profile.get("references")):
            refs.append(f"- {r}")
    if refs:
        lines.extend(refs)
    else:
        lines.append("_(Sem referências externas declaradas até o momento.)_")
    lines.append("")

    lines.append("---")
    lines.append("")

    # ----------------- Seção 2 — Descrição Geral -----------------
    lines.append("## 2. Descrição Geral")
    lines.append("")

    # 2.1 Perspectiva do Produto
    lines.append("### 2.1 Perspectiva do Produto")
    lines.append("")
    arch = ocg_data.get("ARCHITECTURE_OVERVIEW") or {}
    style = arch.get("style") or arch.get("architecture_style")
    if style:
        lines.append(f"- **Estilo arquitetural**: {style}")
    exec_model = arch.get("execution_model") or profile.get("execution_model")
    if exec_model:
        lines.append(f"- **Modelo de execução**: {_join_if_list(exec_model)}")
    if not style and not exec_model:
        lines.append("_(A ser preenchido.)_")
    lines.append("")

    # 2.2 Funcionalidades do Produto (resumo do que o sistema faz)
    lines.append("### 2.2 Funcionalidades do Produto")
    lines.append("")
    functional_mods = [m for m in modules if m.requirement_category == "functional"]
    if functional_mods:
        lines.append("Resumo baseado nos requisitos funcionais do projeto (detalhe na seção 3.1):")
        lines.append("")
        for m in functional_mods[:10]:
            lines.append(f"- **{m.name}** — {_truncate(m.description, 120)}")
        if len(functional_mods) > 10:
            lines.append(f"- _… e mais {len(functional_mods) - 10} requisitos funcionais._")
    else:
        lines.append(
            "_(Requisitos ainda não classificados pelo GP. Funcionalidades "
            "aparecerão aqui conforme módulos forem marcados como `functional`.)_"
        )
    lines.append("")

    # 2.3 Características dos Usuários
    lines.append("### 2.3 Características dos Usuários")
    lines.append("")
    lines.append(
        "Papéis canônicos no GCA: **Admin** (instância), **GP** (projeto, soberano), "
        "**Dev**, **Tester** e **QA**. Ver capítulo 3 do help global para "
        "detalhes das permissões e fluxos operacionais."
    )
    lines.append("")

    # 2.4 Restrições
    lines.append("### 2.4 Restrições")
    lines.append("")
    stack = ocg_data.get("STACK_RECOMMENDATION") or {}
    restrictions = _stack_restrictions(stack)
    if restrictions:
        lines.extend(restrictions)
    else:
        lines.append("_(A stack recomendada ainda não foi consolidada pelo OCG.)_")
    lines.append("")

    # 2.5 Suposições e Dependências
    lines.append("### 2.5 Suposições e Dependências")
    lines.append("")
    assumptions = _as_list(profile.get("assumptions"))
    dependencies = _as_list(profile.get("dependencies"))
    if assumptions:
        lines.append("**Suposições:**")
        for a in assumptions:
            lines.append(f"- {a}")
        lines.append("")
    if dependencies:
        lines.append("**Dependências externas:**")
        for d in dependencies:
            lines.append(f"- {d}")
        lines.append("")
    if external_repos:
        lines.append("**Integrações com repositórios externos:**")
        for repo in external_repos:
            compat = repo.compatibility_status or "não avaliado"
            lines.append(f"- {repo.repo_url} — compatibilidade: {compat}")
        lines.append("")
    if not assumptions and not dependencies and not external_repos:
        lines.append("_(Sem suposições ou dependências externas declaradas.)_")
    lines.append("")

    lines.append("---")
    lines.append("")

    # ----------------- Seção 3 — Requisitos Específicos -----------------
    lines.append("## 3. Requisitos Específicos")
    lines.append("")

    # 3.1 Requisitos Funcionais
    lines.append("### 3.1 Requisitos Funcionais")
    lines.append("")
    if functional_mods:
        for i, m in enumerate(functional_mods, 1):
            lines.extend(_render_requirement(f"RF-{i:03d}", m))
    else:
        lines.append(
            "_Nenhum requisito classificado como `functional` pelo GP até o momento._"
        )
        lines.append("")

    # 3.2 Requisitos Não-Funcionais
    lines.append("### 3.2 Requisitos Não-Funcionais")
    lines.append("")
    non_functional_mods = [m for m in modules if m.requirement_category == "non_functional"]
    if non_functional_mods:
        for i, m in enumerate(non_functional_mods, 1):
            lines.extend(_render_requirement(f"RNF-{i:03d}", m))
    else:
        lines.append(
            "_Nenhum requisito classificado como `non_functional` pelo GP até o momento. "
            "Achados dos pilares P4 (performance) e P7 (segurança) podem ser convertidos "
            "em RNFs via UI do backlog._"
        )
        lines.append("")

    # 3.2.1-3.2.3 NFRs derivados dos pilares (somente leitura)
    pillar_scores = ocg_data.get("PILLAR_SCORES") or {}
    p4_findings = _pillar_findings(pillar_scores, "P4")
    p7_findings = _pillar_findings(pillar_scores, "P7")
    compliance = ocg_data.get("COMPLIANCE_CHECKLIST") or []
    if p4_findings or p7_findings or compliance:
        lines.append("#### 3.2.1 Achados dos pilares (leitura do OCG)")
        lines.append("")
        if p4_findings:
            lines.append("**P4 — Performance / NFRs:**")
            for f in p4_findings[:8]:
                lines.append(f"- {f}")
            lines.append("")
        if p7_findings:
            lines.append("**P7 — Segurança:**")
            for f in p7_findings[:8]:
                lines.append(f"- {f}")
            lines.append("")
        if compliance:
            lines.append("**Compliance:**")
            for c in _as_list(compliance)[:8]:
                lines.append(f"- {_format_entry(c)}")
            lines.append("")

    # 3.3 Regras de Negócio
    lines.append("### 3.3 Regras de Negócio")
    lines.append("")
    business_rules = ocg_data.get("BUSINESS_RULES") or []
    business_rule_mods = [m for m in modules if m.requirement_category == "business_rule"]

    if business_rules or business_rule_mods:
        # Regras do OCG (BUSINESS_RULES)
        for i, br in enumerate(business_rules, 1):
            lines.extend(_render_business_rule(f"BR-{i:03d}", br))
        # Módulos classificados como business_rule (complemento)
        start = len(business_rules) + 1
        for i, m in enumerate(business_rule_mods, start=start):
            lines.extend(_render_requirement(f"BR-{i:03d}", m))
    else:
        lines.append(
            "_Nenhuma regra de negócio registrada. GP popula via a aba OCG "
            "(seção BUSINESS_RULES) ou marcando módulos do backlog como "
            "`business_rule`._"
        )
        lines.append("")

    # 3.4 Interfaces Externas
    lines.append("### 3.4 Interfaces Externas")
    lines.append("")
    if external_repos:
        for repo in external_repos:
            lines.append(f"- **{repo.provider.upper()}**: `{repo.repo_url}`")
            if repo.compatibility_status:
                lines.append(f"  - Compatibilidade GCA: {repo.compatibility_status}")
    else:
        lines.append("_Nenhum repositório externo vinculado ao projeto._")
    lines.append("")

    # Não categorizados (visibilidade para o GP classificar)
    uncategorized = [m for m in modules if m.requirement_category is None]
    if uncategorized:
        lines.append("### 3.5 Requisitos pendentes de classificação")
        lines.append("")
        lines.append(
            f"Existem **{len(uncategorized)}** módulos no backlog ainda não "
            "classificados pelo GP. Abaixo até 10 exemplos — classifique cada um "
            "como `functional`, `non_functional` ou `business_rule` na aba Backlog "
            "do projeto para que apareçam nas seções corretas deste documento:"
        )
        lines.append("")
        for m in uncategorized[:10]:
            lines.append(f"- **{m.name}** ({m.module_type}, prioridade `{m.priority}`)")
        if len(uncategorized) > 10:
            lines.append(f"- _… e mais {len(uncategorized) - 10} módulos._")
        lines.append("")

    lines.append("---")
    lines.append("")

    # ----------------- Seção 4 — Matriz de Rastreabilidade -----------------
    lines.append("## 4. Matriz de Rastreabilidade")
    lines.append("")
    lines.append(
        "_A matriz cruzando requisitos × casos de teste × arquivos/commits será "
        "populada na Fase 19.4 do MVP 19. Por enquanto, os dados brutos de "
        "`test_specs` e de auditoria de CodeGen estão acessíveis em `/projects/:id/qa` "
        "e `/projects/:id/audit` respectivamente._"
    )
    lines.append("")

    lines.append("---")
    lines.append("")

    # ----------------- Histórico -----------------
    lines.append("## Histórico de Revisão")
    lines.append("")
    lines.append(
        "O histórico completo do ERS vive no Git do projeto. Para ver diffs "
        "entre versões, use:"
    )
    lines.append("")
    lines.append("```bash")
    lines.append(f"git log -p {ERS_FILE_PATH}")
    lines.append("```")
    lines.append("")
    lines.append(
        f"Cada regeneração cria um commit com mensagem canônica "
        f"`docs(ers): regen a partir do OCG vN — <motivos>` emitido pelo GCA "
        f"na aba Doc Viva do projeto."
    )
    lines.append("")

    return "\n".join(lines) + "\n"


# ============================================================================
# Geração + commit
# ============================================================================

async def generate_and_commit_ers(
    db: AsyncSession,
    project_id: UUID,
    actor_id: Optional[UUID],
) -> dict:
    """Gera o ERS e commita `docs/ERS.md` no repositório do projeto.

    Retorna:
        {
            "success": bool,
            "commit_sha": str | None,
            "path": "docs/ERS.md",
            "ocg_version": int | None,
            "stale_reasons": [...],
            "message": str,
        }

    Levanta `ValueError` quando o projeto não tem repositório Git conectado —
    o caller traduz em HTTP 400 para o frontend mostrar mensagem clara.
    """
    # 1. Coleta freshness atual (antes de regenerar) para registrar no audit.
    freshness_before = await get_ers_freshness(db, project_id)
    stale_reasons_snapshot = [r["event_type"] for r in freshness_before["stale_reasons"]]

    # 2. Monta o markdown.
    markdown = await build_ers_markdown(db, project_id)

    # 3. Commit no repositório do projeto.
    git = GitService(db)
    ocg_version = None
    # Recupera a versão atual do OCG pra compor a mensagem e o audit.
    ocg_ctx_result = await db.execute(
        select(OCG)
        .where(OCG.project_id == project_id)
        .order_by(desc(OCG.version))
        .limit(1)
    )
    current_ocg = ocg_ctx_result.scalar_one_or_none()
    if current_ocg is not None:
        ocg_version = current_ocg.version

    summary = _summarize_reasons(stale_reasons_snapshot) or "regen manual"
    commit_msg = f"docs(ers): regen a partir do OCG v{ocg_version or '-'} — {summary}"

    commit_result = await git.commit_file(
        project_id=project_id,
        file_path=ERS_FILE_PATH,
        content=markdown,
        commit_message=commit_msg,
    )

    if not commit_result.get("success"):
        # Erro explícito — projeto sem repo, PAT inválido, API do provider
        # fora, etc. Propagamos para o caller via ValueError.
        raise ValueError(
            commit_result.get("message")
            or "Falha ao commitar docs/ERS.md no repositório do projeto"
        )

    commit_sha = commit_result.get("commit_sha", "")

    # 4. Audit: LIVEDOCS_UPDATED com doc_type='ers'.
    audit = AuditService(db)
    await audit.log_event(
        event_type=AuditEvents.LIVEDOCS_UPDATED,
        resource_type="live_doc",
        actor_id=actor_id,
        resource_id=project_id,
        details={
            "doc_type": "ers",
            "commit_sha": commit_sha,
            "path": ERS_FILE_PATH,
            "version_to": ocg_version,
            "stale_reasons": stale_reasons_snapshot,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    await db.commit()

    logger.info(
        "ers.generated_and_committed",
        project_id=str(project_id),
        commit_sha=commit_sha,
        ocg_version=ocg_version,
        stale_count=len(stale_reasons_snapshot),
    )

    return {
        "success": True,
        "commit_sha": commit_sha,
        "path": ERS_FILE_PATH,
        "ocg_version": ocg_version,
        "stale_reasons": stale_reasons_snapshot,
        "message": commit_msg,
    }


# ============================================================================
# Helpers internos
# ============================================================================

def _parse_details_field(value) -> dict:
    return _parse_details(value)


def _first_non_empty(*values) -> Optional[str]:
    for v in values:
        if v and isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    if value:
        return [value]
    return []


def _join_if_list(value) -> str:
    items = _as_list(value)
    return ", ".join(str(x) for x in items) or "—"


def _truncate(text: Optional[str], limit: int) -> str:
    if not text:
        return "_(sem descrição)_"
    text = str(text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _deliverables_as_list(deliverables) -> list[str]:
    """DELIVERABLES aceita dict por categoria ou lista direta."""
    if not deliverables:
        return []
    result: list[str] = []
    if isinstance(deliverables, dict):
        for category, items in deliverables.items():
            items_list = _as_list(items)
            if not items_list:
                continue
            for item in items_list:
                result.append(f"[{category}] {_format_entry(item)}")
    elif isinstance(deliverables, list):
        for item in deliverables:
            result.append(_format_entry(item))
    return result


def _format_entry(entry) -> str:
    """Formata string/dict em uma linha legível pro markdown."""
    if isinstance(entry, dict):
        title = entry.get("title") or entry.get("name") or entry.get("item") or entry.get("description")
        if title:
            return str(title)
        return json.dumps(entry, ensure_ascii=False)
    return str(entry)


def _stack_restrictions(stack: dict) -> list[str]:
    if not isinstance(stack, dict):
        return []
    out: list[str] = []
    backend = stack.get("backend") or {}
    if isinstance(backend, dict):
        lang = backend.get("language")
        framework = backend.get("framework")
        if lang:
            out.append(f"- **Linguagem backend**: {lang}")
        if framework:
            out.append(f"- **Framework backend**: {_join_if_list(framework)}")
    frontend = stack.get("frontend") or {}
    if isinstance(frontend, dict):
        fe_stack = frontend.get("stack") or frontend.get("framework")
        if fe_stack:
            out.append(f"- **Frontend**: {_join_if_list(fe_stack)}")
    db = stack.get("database") or {}
    if isinstance(db, dict):
        engine = db.get("engine")
        if engine:
            out.append(f"- **Banco**: {engine}")
    cache = stack.get("cache") or {}
    if isinstance(cache, dict) and cache.get("enabled"):
        out.append("- **Cache**: habilitado")
    msg = stack.get("messaging") or {}
    if isinstance(msg, dict) and msg.get("enabled"):
        purpose = msg.get("purpose")
        out.append(f"- **Mensageria**: habilitada ({_join_if_list(purpose)})" if purpose else "- **Mensageria**: habilitada")
    return out


def _pillar_findings(pillar_scores: dict, pillar_key: str) -> list[str]:
    if not isinstance(pillar_scores, dict):
        return []
    data = pillar_scores.get(pillar_key)
    if not isinstance(data, dict):
        return []
    findings = data.get("findings") or []
    result: list[str] = []
    for f in _as_list(findings):
        if isinstance(f, dict):
            sev = f.get("severity", "info")
            desc = f.get("description") or f.get("message") or f.get("title")
            rec = f.get("recommendation")
            line = f"[{sev}] {desc}"
            if rec:
                line += f" — {rec}"
            result.append(line)
        else:
            result.append(str(f))
    return result


def _render_requirement(prefix: str, module: ModuleCandidate) -> list[str]:
    lines: list[str] = []
    lines.append(f"- **{prefix} — {module.name}**")
    lines.append(f"    - Descrição: {_truncate(module.description, 300)}")
    lines.append(f"    - Tipo: `{module.module_type}` · Prioridade: `{module.priority}` · Status: `{module.status}`")
    if module.requirement_category:
        lines.append(f"    - Categoria IEEE 830: `{module.requirement_category}`")
    lines.append("")
    return lines


def _render_business_rule(prefix: str, br) -> list[str]:
    """Renderiza regra de negócio. Se o dict tiver `id` explícito (ex:
    'BR-GCA-001' cadastrado pelo GP), esse id prevalece; caso contrário
    usa o `prefix` autoincrementado (BR-001, BR-002…)."""
    lines: list[str] = []
    if isinstance(br, dict):
        rule_id = br.get("id") or prefix
        title = br.get("title") or br.get("name") or rule_id
        desc = br.get("description") or br.get("details") or ""
        source = br.get("source")
        lines.append(f"- **{rule_id} — {title}**")
        if desc:
            lines.append(f"    - {desc}")
        if source:
            lines.append(f"    - Fonte: {source}")
    else:
        lines.append(f"- **{prefix}** — {br}")
    lines.append("")
    return lines


def _summarize_reasons(reasons: list[str]) -> str:
    """Ex: ['OCG_UPDATED', 'OCG_UPDATED', 'DOCUMENT_INGESTED'] → 'OCG_UPDATED x2, DOCUMENT_INGESTED'."""
    if not reasons:
        return ""
    counts: dict[str, int] = {}
    for r in reasons:
        counts[r] = counts.get(r, 0) + 1
    parts = []
    for r, c in counts.items():
        parts.append(f"{r} x{c}" if c > 1 else r)
    return ", ".join(parts)
