#!/usr/bin/env python3
"""
v3 — Captura em DUAS PASSADAS distintas:

  Passada 1: Admin puro (pielak.ctba@gmail.com)
    - telas públicas (5)
    - telas admin (12) — sidebar ADMINISTRAÇÃO com todas as seções
    - changelog user-facing (1)

  Passada 2: GP puro (Fernando, minicooper2020br@outlook.com)
    - telas do projeto Automação Jurídica (21) — sidebar MEUS
      PROJETOS expandida com sub-itens do projeto (Dashboard, OCG,
      Questionário, Repositórios, Ingestão, etc).

Motivação: a v2 logou só como Admin; o sidebar admin override
impedia a visualização do menu do GP. Esta versão troca context
explicitamente entre as 2 passadas.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Optional

try:
    from playwright.async_api import Page, TimeoutError as PWTimeout, async_playwright
except ImportError:
    print("ERRO: playwright não instalado.", file=sys.stderr)
    sys.exit(1)


ADMIN_EMAIL = "pielak.ctba@gmail.com"
GP_EMAIL = "minicooper2020br@outlook.com"

# Senha temporária — setada no DB antes deste script rodar.
# Ambas usam a mesma Topazio01# durante a captura.
ADMIN_PASSWORD = os.environ.get("GCA_ADMIN_PASSWORD")
GP_PASSWORD = os.environ.get("GCA_GP_PASSWORD") or ADMIN_PASSWORD
if not ADMIN_PASSWORD:
    print("ERRO: exporte GCA_ADMIN_PASSWORD.", file=sys.stderr)
    sys.exit(2)

PROJECT_SLUG = "automacao-juridica-assistida"
PROJECT_SHORT_SLUG = "automa-o-jur-di"   # /p/{short_slug} — endpoint by-slug busca por short_slug
PROJECT_ID = "65cab180-e00d-4eec-aaf2-fb4b5d0f4057"

OUTPUT_DIR = Path("/home/luiz/GCA/screenshots_v3")
BASE_URL = os.environ.get("GCA_BASE_URL", "http://localhost:5173")
VIEWPORT = {"width": 1600, "height": 1000}
NAV_TIMEOUT_MS = 30_000
SETTLE_MS = 2000


@dataclass
class Shot:
    n: int
    category: str  # publica | admin | projeto | global
    slug: str
    description: str
    url: Optional[str] = None
    pre_action: Optional[Callable[[Page], Awaitable[None]]] = None
    full_page: bool = True
    settle_ms: int = SETTLE_MS


async def safe_goto(page: Page, url: str) -> bool:
    full = url if url.startswith("http") else f"{BASE_URL}{url}"
    try:
        await page.goto(full, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
        return True
    except PWTimeout:
        print(f"  [!] timeout em {full}")
        return False


async def wait_settle(page: Page, ms: int = SETTLE_MS) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except PWTimeout:
        pass
    await page.wait_for_timeout(ms)


async def login_as(page: Page, email: str, password: str,
                   via_project_slug: str | None = None) -> bool:
    """Login.
    - Admin: via /login (genérico).
    - GP/Dev/Tester/QA: via /p/{slug} (ProjectLoginPage — o backend
      exige selecionar projeto pra não-admin).
    """
    login_path = f"/p/{via_project_slug}" if via_project_slug else "/login"
    print(f"  [login] {email} @ {BASE_URL}{login_path}")
    await page.context.clear_cookies()
    try:
        await page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
    except Exception:
        pass

    if not await safe_goto(page, login_path):
        return False
    await wait_settle(page, 2500)
    try:
        # ProjectLoginPage tem estado inicial 'loading' — espera o input aparecer
        email_input = page.locator('input[type="email"]').first
        await email_input.wait_for(state="visible", timeout=15000)
        await email_input.fill(email)
        pwd = page.locator('input[type="password"]').first
        await pwd.fill(password)
        await pwd.press("Enter")
        # Espera navegar fora de /login ou /p/{slug}
        await page.wait_for_url(
            lambda u: "/login" not in u and f"/p/{via_project_slug or ''}" not in u,
            timeout=NAV_TIMEOUT_MS,
        )
        await wait_settle(page, 1500)
        print(f"  [login] OK → {page.url}")
        return True
    except Exception as e:
        print(f"  [login] FALHOU: {e}")
        return False


async def snap(page: Page, out: Path, full_page: bool = True) -> bool:
    try:
        await page.screenshot(path=str(out), full_page=full_page)
        return True
    except Exception as e:
        print(f"  [!] screenshot falhou: {e}")
        return False


# ─── Pré-actions (modais) ─────────────────────────────────────────────────

async def open_new_admin_modal(page: Page) -> None:
    await wait_settle(page, 1200)
    btn = page.get_by_role("button", name="Convidar Administrador")
    if await btn.count() > 0:
        await btn.first.click()
        await wait_settle(page, 700)


async def open_new_incident_modal(page: Page) -> None:
    await wait_settle(page, 1200)
    btn = page.get_by_role("button", name="Abrir ticket")
    if await btn.count() > 0:
        await btn.first.click()
        await wait_settle(page, 700)


async def open_first_release_detail(page: Page) -> None:
    await wait_settle(page, 1500)
    first = page.locator('a[href*="/admin/releases/"]').first
    if await first.count() > 0:
        await first.click()
        await wait_settle(page, 1200)


# ─── Pré-actions MVP 8/9/10 ──────────────────────────────────────────────

async def expand_first_ingestion_report(page: Page) -> None:
    """MVP 8.5 — Extraction Report card (toggle) na Ingestão."""
    await wait_settle(page, 1800)
    toggle = page.locator('button:has-text("Relatório de extração")').first
    if await toggle.count() > 0:
        try:
            await toggle.click()
            await wait_settle(page, 1000)
        except Exception:
            pass


async def open_first_module_details(page: Page) -> None:
    """MVP 9.2 — Modal de detalhamento de módulo do Roadmap.

    Cada chip de módulo é um <button> com ícone GitCommit + nome +
    badge de categoria. Clicar abre o ModuleDetailsModal.
    """
    await wait_settle(page, 2000)
    # Clip até o primeiro chip de módulo com categoria (elimina botões da UI)
    chip = page.locator('main button:has(svg.lucide-git-commit-horizontal)').first
    if await chip.count() > 0:
        try:
            await chip.click()
            await wait_settle(page, 1500)
        except Exception:
            pass


async def open_deploy_plan_modal(page: Page) -> None:
    """MVP 9.4 — Modal Plano de Deploy no Roadmap."""
    await wait_settle(page, 1500)
    btn = page.get_by_role("button", name="Plano de Deploy").first
    if await btn.count() > 0:
        try:
            await btn.click()
            await wait_settle(page, 1500)
        except Exception:
            pass


async def open_first_test_spec_modal(page: Page) -> None:
    """MVP 10.5 — Modal TestSpec com provenance (aba QA/Plano de Testes)."""
    await wait_settle(page, 1800)
    # Primeiro item clicável da seção de specs
    card = page.locator('button:has(span:text-is("Unitários")), button:has(span:text-is("Integração")), button:has(span:text-is("Segurança")), button:has(span:text-is("Compliance")), button:has(span:text-is("E2E"))').first
    if await card.count() > 0:
        try:
            await card.click()
            await wait_settle(page, 1200)
        except Exception:
            pass


async def open_first_live_doc_modal(page: Page) -> None:
    """MVP 10.7 — Modal LiveDoc com provenance.

    Os items de doc estão em <section> dentro do main (agrupados por tipo).
    Clicar em qualquer um abre o modal.
    """
    await wait_settle(page, 2000)
    card = page.locator('main section button').first
    if await card.count() > 0:
        try:
            await card.click()
            await wait_settle(page, 1500)
        except Exception:
            pass


# ─── Expansão da sidebar do projeto ───────────────────────────────────────

async def expand_project_sidebar(page: Page) -> None:
    """Garante que a seção 'MEUS PROJETOS' está expandida e o projeto
    correto aparece com sub-itens. Se já está expandida, no-op."""
    await wait_settle(page, 1000)
    # A sidebar só mostra sub-itens quando está dentro da rota do projeto.
    # Como capturamos no próprio URL /projects/{id}/..., os sub-itens
    # já estão visíveis pelo isInProject. Nada a fazer.


# ─── Listas de capturas ───────────────────────────────────────────────────

def shots_admin_phase() -> list[Shot]:
    """Capturas feitas como Admin puro."""
    return [
        # ─── Pré-login (5) ─────────────────────────────
        Shot(1,  "publica", "login_admin",        "Login Admin",                 url="/login"),
        Shot(2,  "publica", "login_projeto",      "Login via projeto (slug)",    url=f"/p/{PROJECT_SHORT_SLUG}"),
        Shot(3,  "publica", "reset_password",     "Reset de senha",              url="/reset-password"),
        Shot(4,  "publica", "accept_invitation",  "Aceite de convite",           url="/accept-invitation"),
        Shot(5,  "publica", "solicitar_projeto",  "Solicitar projeto externo",   url="/solicitar-projeto"),
        # ─── Admin (12) ───────────────────────────────
        Shot(10, "admin", "dashboard_global",      "Dashboard Global",                  url="/admin"),
        Shot(11, "admin", "gestao_projetos",       "Gestão de Projetos (lifecycle)",    url="/admin/projects"),
        Shot(12, "admin", "projeto_visao_admin",   "Visão Admin do Projeto",            url=f"/admin/projects/{PROJECT_ID}"),
        Shot(13, "admin", "gestao_usuarios",       "Gestão de Usuários",                url="/admin/users"),
        Shot(14, "admin", "convidar_admin_modal",  "Modal Convidar Administrador",
             url="/admin/users", pre_action=open_new_admin_modal),
        Shot(15, "admin", "auditoria_global",      "Auditoria Global",                  url="/admin/audit"),
        Shot(16, "admin", "metricas",              "Métricas (global + por projeto)",   url="/admin/metrics"),
        Shot(17, "admin", "backups",               "Backups agregados",                 url="/admin/backups"),
        Shot(18, "admin", "incidents",             "Tickets escalados a Admin",         url="/admin/incidents"),
        Shot(19, "admin", "equipe_sustentacao",    "Equipe Sustentação",                url="/admin/support"),
        Shot(20, "admin", "releases",              "Releases — visão admin",            url="/admin/releases"),
        Shot(21, "admin", "release_detail",        "Detalhe de release",
             url="/admin/releases", pre_action=open_first_release_detail),
        # ─── Changelog (1) ────────────────────────────
        Shot(25, "global", "changelog_user_admin", "Novidades e entregas (visto por Admin)", url="/releases"),
    ]


def shots_gp_phase() -> list[Shot]:
    """Capturas feitas como GP puro (sidebar do projeto com todos os
    sub-itens: Dashboard, Equipe, OCG, Ingestão, Gatekeeper, Arguidor,
    CodeGen, QA, Revisão, Backlog, Roadmap, Docs, Readiness, Settings,
    Audit, Backups, Incidentes, Métricas)."""
    pid = PROJECT_ID
    return [
        # Lista de projetos (como GP vê: sidebar sem admin)
        Shot(30, "projeto", "gp_lista_projetos",   "Lista de projetos (visão do GP)",     url="/projects"),
        # Dentro do projeto
        Shot(31, "projeto", "gp_dashboard",        "Dashboard do projeto (sidebar GP)",   url=f"/projects/{pid}"),
        Shot(32, "projeto", "gp_team",             "Equipe (sidebar GP)",                 url=f"/projects/{pid}/team"),
        Shot(33, "projeto", "gp_ocg",              "OCG (sidebar GP)",                    url=f"/projects/{pid}/ocg"),
        Shot(34, "projeto", "gp_external_repos",   "Repositórios externos",               url=f"/projects/{pid}/external-repos"),
        Shot(35, "projeto", "gp_ingestion",        "Ingestão",                            url=f"/projects/{pid}/ingestion"),
        Shot(36, "projeto", "gp_gatekeeper",       "Gatekeeper",                          url=f"/projects/{pid}/gatekeeper"),
        Shot(37, "projeto", "gp_arguider",         "Arguidor",                            url=f"/projects/{pid}/arguider"),
        Shot(38, "projeto", "gp_codegen",          "Geração de Código",                   url=f"/projects/{pid}/codegen"),
        Shot(39, "projeto", "gp_qa_readiness",     "QA Readiness",                        url=f"/projects/{pid}/qa"),
        Shot(40, "projeto", "gp_tester_review",    "Revisão de Testes",                   url=f"/projects/{pid}/tester-review"),
        Shot(41, "projeto", "gp_backlog",          "Backlog",                             url=f"/projects/{pid}/backlog"),
        Shot(42, "projeto", "gp_roadmap",          "Roadmap",                             url=f"/projects/{pid}/roadmap"),
        Shot(43, "projeto", "gp_docs",             "Documentação Viva",                   url=f"/projects/{pid}/docs"),
        Shot(44, "projeto", "gp_readiness",        "Definition of Done",                  url=f"/projects/{pid}/readiness"),
        Shot(45, "projeto", "gp_settings",         "Configurações (tabs)",                url=f"/projects/{pid}/settings"),
        Shot(46, "projeto", "gp_audit",            "Pipeline Audit",                      url=f"/projects/{pid}/audit"),
        Shot(47, "projeto", "gp_backups",          "Backups do Projeto",                  url=f"/projects/{pid}/backups"),
        Shot(48, "projeto", "gp_incidents",        "Incidentes do Projeto",               url=f"/projects/{pid}/incidents"),
        Shot(49, "projeto", "gp_abrir_ticket_modal","Modal Abrir Ticket",
             url=f"/projects/{pid}/incidents", pre_action=open_new_incident_modal),
        Shot(50, "projeto", "gp_metrics",          "Métricas do Projeto",                 url=f"/projects/{pid}/metrics"),
        # ─── MVP 8/9/10 — Modais e novas telas ────────────────────
        Shot(60, "projeto", "gp_ingestion_report",  "Ingestão com relatório de extração (MVP 8.5)",
             url=f"/projects/{pid}/ingestion", pre_action=expand_first_ingestion_report),
        Shot(61, "projeto", "gp_module_details",    "Modal Detalhamento de Módulo (MVP 9.2)",
             url=f"/projects/{pid}/roadmap", pre_action=open_first_module_details),
        Shot(62, "projeto", "gp_deploy_plan",       "Modal Plano de Deploy (MVP 9.4)",
             url=f"/projects/{pid}/roadmap", pre_action=open_deploy_plan_modal),
        Shot(63, "projeto", "gp_test_spec_modal",   "Modal Plano de Testes com provenance (MVP 10.5)",
             url=f"/projects/{pid}/qa", pre_action=open_first_test_spec_modal),
        Shot(64, "projeto", "gp_live_doc_modal",    "Modal Doc Viva com provenance (MVP 10.7)",
             url=f"/projects/{pid}/docs", pre_action=open_first_live_doc_modal),
        # GP também vê /releases (mas segmentado por papel)
        Shot(55, "global",  "gp_changelog_user",   "Novidades e entregas (visto por GP)", url="/releases"),
    ]


async def capture_one(page: Page, shot: Shot) -> dict:
    out = OUTPUT_DIR / f"{shot.n:02d}_{shot.category}_{shot.slug}.png"
    result = {
        "n": shot.n,
        "category": shot.category,
        "slug": shot.slug,
        "description": shot.description,
        "url": shot.url,
        "file": out.name,
        "ok": False,
        "error": None,
    }
    try:
        if shot.url:
            if not await safe_goto(page, shot.url):
                result["error"] = "navigation timeout"
                return result
        await wait_settle(page, shot.settle_ms)
        if shot.pre_action:
            try:
                await shot.pre_action(page)
            except Exception as e:
                print(f"  [!] pre_action falhou: {e}")
        ok = await snap(page, out, shot.full_page)
        result["ok"] = ok
        if not ok:
            result["error"] = "screenshot failed"
    except Exception as e:
        result["error"] = str(e)
    return result


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "started_at": datetime.now().isoformat(),
        "base_url": BASE_URL,
        "viewport": VIEWPORT,
        "project_slug": PROJECT_SLUG,
        "phases": [],
    }

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        # ═══ FASE 1: Admin puro ═══════════════════════════════════
        print("\n══════════════════════════════════════════════════════")
        print("  FASE 1: Admin puro (pielak.ctba@gmail.com)")
        print("══════════════════════════════════════════════════════\n")
        context = await browser.new_context(viewport=VIEWPORT, locale="pt-BR")
        page = await context.new_page()

        admin_results = []
        # Capturas públicas primeiro (sem login)
        print("── Telas públicas ──")
        for s in shots_admin_phase():
            if s.category != "publica":
                continue
            print(f"  [{s.n:02d}] {s.description}")
            r = await capture_one(page, s)
            admin_results.append(r)
            print(f"     → {'OK' if r['ok'] else 'FAIL'}  {r.get('error') or ''}")

        # Login admin
        if not await login_as(page, ADMIN_EMAIL, ADMIN_PASSWORD):
            print("  [FATAL] login admin falhou")
        else:
            print("── Telas admin + changelog ──")
            for s in shots_admin_phase():
                if s.category == "publica":
                    continue
                print(f"  [{s.n:02d}] {s.description}")
                r = await capture_one(page, s)
                admin_results.append(r)
                print(f"     → {'OK' if r['ok'] else 'FAIL'}  {r.get('error') or ''}")

        await context.close()
        manifest["phases"].append({"phase": "admin", "results": admin_results})

        # ═══ FASE 2: GP puro (Fernando) ════════════════════════════
        print("\n══════════════════════════════════════════════════════")
        print(f"  FASE 2: GP puro ({GP_EMAIL})")
        print("══════════════════════════════════════════════════════\n")
        context2 = await browser.new_context(viewport=VIEWPORT, locale="pt-BR")
        page2 = await context2.new_page()

        gp_results = []
        if not await login_as(page2, GP_EMAIL, GP_PASSWORD, via_project_slug=PROJECT_SHORT_SLUG):
            print("  [FATAL] login GP falhou")
        else:
            print("── Telas projeto (GP) ──")
            for s in shots_gp_phase():
                print(f"  [{s.n:02d}] {s.description}")
                r = await capture_one(page2, s)
                gp_results.append(r)
                print(f"     → {'OK' if r['ok'] else 'FAIL'}  {r.get('error') or ''}")

        await context2.close()
        manifest["phases"].append({"phase": "gp", "results": gp_results})

        await browser.close()

    manifest["finished_at"] = datetime.now().isoformat()
    total = sum(len(p["results"]) for p in manifest["phases"])
    ok = sum(sum(1 for r in p["results"] if r["ok"]) for p in manifest["phases"])
    manifest["total"] = total
    manifest["ok"] = ok
    manifest["failed"] = total - ok

    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n✓ Concluído: {ok}/{total} OK ({total-ok} falhas)")
    print(f"  Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
