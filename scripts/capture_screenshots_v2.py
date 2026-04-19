#!/usr/bin/env python3
"""
Captura screenshots full-page de TODAS as 38 telas do GCA (pós MVP 7).

Evolução do scripts/capturar_telas_gca.py. Difere em:
- Cobre telas novas pós-MVP 7: Incidents, Equipe Sustentação, Releases,
  Métricas por projeto, Backups por projeto, Admin/Support.
- Usa projeto "Automação Jurídica Assistida" como referência (onde o
  admin pielak.ctba@gmail.com foi temporariamente adicionado como GP
  pra capturar o escopo de projeto).
- Tenta capturar modais relevantes (Convidar Admin, Abrir Ticket).
- Viewport 1600x1000 (mais espaço pra screenshots legíveis em docx).

Uso:
    export GCA_ADMIN_PASSWORD='Topazio01#'
    python3 scripts/capture_screenshots_v2.py
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
    print("ERRO: playwright não instalado. Execute:", file=sys.stderr)
    print("  source /home/luiz/GCA/.venv-screenshots/bin/activate", file=sys.stderr)
    print("  pip install playwright && playwright install chromium", file=sys.stderr)
    sys.exit(1)


# ─── Config ───────────────────────────────────────────────────────────────

ADMIN_EMAIL = "pielak.ctba@gmail.com"
ADMIN_PASSWORD = os.environ.get("GCA_ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    print("ERRO: exporte GCA_ADMIN_PASSWORD antes de rodar.", file=sys.stderr)
    sys.exit(2)

# Automação Jurídica Assistida (dogfood) — Luiz é GP temporário.
PROJECT_SLUG = "automacao-juridica-assistida"
PROJECT_ID = "65cab180-e00d-4eec-aaf2-fb4b5d0f4057"

OUTPUT_DIR = Path("/home/luiz/GCA/screenshots_v2")
BASE_URL = os.environ.get("GCA_BASE_URL", "http://localhost:5173")
VIEWPORT = {"width": 1600, "height": 1000}
NAV_TIMEOUT_MS = 30_000
SETTLE_MS = 2000


@dataclass
class Shot:
    n: int
    category: str  # "publica" | "admin" | "projeto" | "global"
    slug: str
    description: str
    url: Optional[str] = None
    pre_action: Optional[Callable[[Page], Awaitable[None]]] = None
    full_page: bool = True
    settle_ms: int = SETTLE_MS


# ─── Helpers ──────────────────────────────────────────────────────────────

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


async def login_admin(page: Page) -> bool:
    """Login via UI como admin."""
    print(f"  [login] {ADMIN_EMAIL} @ {BASE_URL}/login")
    if not await safe_goto(page, "/login"):
        return False
    await wait_settle(page, 1200)
    try:
        # Campo email
        email_input = page.locator('input[type="email"], input[name="email"]').first
        await email_input.fill(ADMIN_EMAIL)
        pwd_input = page.locator('input[type="password"]').first
        await pwd_input.fill(ADMIN_PASSWORD)
        # Submit (Enter ou botão)
        await pwd_input.press("Enter")
        await page.wait_for_url(lambda u: "/login" not in u, timeout=NAV_TIMEOUT_MS)
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


# ─── Lista de capturas ────────────────────────────────────────────────────

async def open_new_admin_modal(page: Page) -> None:
    """Abre modal 'Convidar Administrador' na AdminUsersPage."""
    await wait_settle(page, 1200)
    btn = page.get_by_role("button", name="Convidar Administrador")
    if await btn.count() > 0:
        await btn.first.click()
        await wait_settle(page, 600)


async def open_new_incident_modal(page: Page) -> None:
    """Abre modal 'Abrir ticket' na IncidentListPage."""
    await wait_settle(page, 1200)
    btn = page.get_by_role("button", name="Abrir ticket")
    if await btn.count() > 0:
        await btn.first.click()
        await wait_settle(page, 600)


async def open_first_release_detail(page: Page) -> None:
    """Clica na primeira release da lista admin."""
    await wait_settle(page, 1500)
    first = page.locator('a[href*="/admin/releases/"]').first
    if await first.count() > 0:
        await first.click()
        await wait_settle(page, 1200)


def build_shots() -> list[Shot]:
    pid = PROJECT_ID
    slug = PROJECT_SLUG
    return [
        # ─── A. Pré-login (5 capturáveis — /setup é pulado) ────────────
        Shot(1,  "publica", "login_admin",        "Login Admin", url="/login"),
        Shot(2,  "publica", "login_projeto",      "Login via projeto (slug)", url=f"/p/{slug}"),
        Shot(3,  "publica", "reset_password",     "Reset de senha", url="/reset-password"),
        Shot(4,  "publica", "accept_invitation",  "Aceite de convite", url="/accept-invitation"),
        Shot(5,  "publica", "solicitar_projeto",  "Solicitar projeto externo", url="/solicitar-projeto"),

        # ─── B. Área Administrativa (12) ──────────────────────────────
        Shot(10, "admin", "dashboard_global",      "Dashboard Global",                 url="/admin"),
        Shot(11, "admin", "gestao_projetos",       "Gestão de Projetos (lifecycle)",   url="/admin/projects"),
        Shot(12, "admin", "projeto_visao_admin",   "Visão Admin do Projeto",           url=f"/admin/projects/{pid}"),
        Shot(13, "admin", "gestao_usuarios",       "Gestão de Usuários",               url="/admin/users"),
        Shot(14, "admin", "convidar_admin_modal",  "Modal Convidar Administrador",
             url="/admin/users", pre_action=open_new_admin_modal),
        Shot(15, "admin", "auditoria_global",      "Auditoria Global",                 url="/admin/audit"),
        Shot(16, "admin", "metricas",              "Métricas (global + por projeto)",  url="/admin/metrics"),
        Shot(17, "admin", "backups",               "Backups agregados",                url="/admin/backups"),
        Shot(18, "admin", "incidents",             "Tickets escalados a Admin",        url="/admin/incidents"),
        Shot(19, "admin", "equipe_sustentacao",    "Equipe Sustentação",               url="/admin/support"),
        Shot(20, "admin", "releases",              "Releases — visão admin",           url="/admin/releases"),
        Shot(21, "admin", "release_detail",        "Detalhe de release",
             url="/admin/releases", pre_action=open_first_release_detail),

        # ─── C. Changelog user-facing (1) ─────────────────────────────
        Shot(25, "global", "changelog_user",       "Novidades e entregas (user)",      url="/releases"),

        # ─── D. Área de Projeto (21) ──────────────────────────────────
        Shot(30, "projeto", "lista_projetos",         "Meus Projetos",              url="/projects"),
        Shot(31, "projeto", "dashboard",              "Dashboard do projeto",       url=f"/projects/{pid}"),
        Shot(32, "projeto", "team",                   "Equipe",                     url=f"/projects/{pid}/team"),
        Shot(33, "projeto", "ocg",                    "OCG",                        url=f"/projects/{pid}/ocg"),
        Shot(34, "projeto", "external_repos",         "Repositórios externos",      url=f"/projects/{pid}/external-repos"),
        Shot(35, "projeto", "ingestion",              "Ingestão",                   url=f"/projects/{pid}/ingestion"),
        Shot(36, "projeto", "gatekeeper",             "Gatekeeper",                 url=f"/projects/{pid}/gatekeeper"),
        Shot(37, "projeto", "arguider",               "Arguidor",                   url=f"/projects/{pid}/arguider"),
        Shot(38, "projeto", "codegen",                "Geração de Código",          url=f"/projects/{pid}/codegen"),
        Shot(39, "projeto", "qa_readiness",           "QA Readiness",               url=f"/projects/{pid}/qa"),
        Shot(40, "projeto", "tester_review",          "Revisão de Testes",          url=f"/projects/{pid}/tester-review"),
        Shot(41, "projeto", "backlog",                "Backlog",                    url=f"/projects/{pid}/backlog"),
        Shot(42, "projeto", "roadmap",                "Roadmap",                    url=f"/projects/{pid}/roadmap"),
        Shot(43, "projeto", "docs",                   "Documentação Viva",          url=f"/projects/{pid}/docs"),
        Shot(44, "projeto", "readiness",              "Definition of Done",         url=f"/projects/{pid}/readiness"),
        Shot(45, "projeto", "settings",               "Configurações (tabs)",       url=f"/projects/{pid}/settings"),
        Shot(46, "projeto", "audit",                  "Pipeline Audit",             url=f"/projects/{pid}/audit"),
        Shot(47, "projeto", "backups",                "Backups do Projeto",         url=f"/projects/{pid}/backups"),
        Shot(48, "projeto", "incidents",              "Incidentes do Projeto",      url=f"/projects/{pid}/incidents"),
        Shot(49, "projeto", "abrir_ticket_modal",     "Modal Abrir Ticket",
             url=f"/projects/{pid}/incidents", pre_action=open_new_incident_modal),
        Shot(50, "projeto", "metrics",                "Métricas do Projeto",        url=f"/projects/{pid}/metrics"),
    ]


# ─── Runner ───────────────────────────────────────────────────────────────

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
        "shots": [],
    }

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport=VIEWPORT, locale="pt-BR")
        page = await context.new_page()

        shots = build_shots()
        total = len(shots)
        print(f"\n► Iniciando captura de {total} telas em {OUTPUT_DIR}\n")

        # Primeiro: capturas públicas (sem login)
        print("── Fase 1: Telas públicas (sem login) ──────────────────")
        for s in shots:
            if s.category != "publica":
                continue
            print(f"  [{s.n:02d}] {s.description} ({s.url})")
            res = await capture_one(page, s)
            manifest["shots"].append(res)
            print(f"     → {'OK' if res['ok'] else 'FAIL'}  {res.get('error') or ''}")

        # Depois: login + capturas admin + projeto
        print("\n── Fase 2: Login admin + telas autenticadas ───────────")
        if not await login_admin(page):
            print("  [FATAL] login admin falhou — encerrando")
            manifest["fatal_login"] = True
        else:
            for s in shots:
                if s.category == "publica":
                    continue
                print(f"  [{s.n:02d}] {s.description} ({s.url})")
                res = await capture_one(page, s)
                manifest["shots"].append(res)
                print(f"     → {'OK' if res['ok'] else 'FAIL'}  {res.get('error') or ''}")

        await browser.close()

    manifest["finished_at"] = datetime.now().isoformat()
    manifest["total"] = len(manifest["shots"])
    manifest["ok"] = sum(1 for s in manifest["shots"] if s["ok"])
    manifest["failed"] = manifest["total"] - manifest["ok"]

    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n✓ Concluído: {manifest['ok']}/{manifest['total']} OK  ({manifest['failed']} falhas)")
    print(f"  Arquivos: {OUTPUT_DIR}")
    print(f"  Manifest: {manifest_path}")


if __name__ == "__main__":
    asyncio.run(main())
