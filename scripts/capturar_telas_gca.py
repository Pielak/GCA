#!/usr/bin/env python3
"""
Captura screenshots full-page de todas as telas relevantes do GCA.

Faz duas passadas:
  1. Como ADMIN (pielak.ctba@gmail.com) — captura área administrativa.
  2. Como GP do FinanceHub Pro (pielakluiz@gmail.com) — captura todas as
     páginas do pipeline do projeto.

Saída: /home/luiz/GCA/screenshots/<NN>_<categoria>_<slug>.png + manifest.json

Uso:
    python3 scripts/capturar_telas_gca.py [--base-url http://localhost:5173]
                                          [--headed]
                                          [--slow-mo 0]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Optional

try:
    from playwright.async_api import Page, TimeoutError as PWTimeout, async_playwright
except ImportError:
    print("ERRO: playwright não instalado. Rode primeiro: bash scripts/capturar_telas_gca.sh")
    sys.exit(1)


# ──────────────────────────────────────────────────────────────────
# Configuração
# ──────────────────────────────────────────────────────────────────

ADMIN_EMAIL = "pielak.ctba@gmail.com"
GP_EMAIL = "pielakluiz@gmail.com"

# Senhas ficam em variáveis de ambiente para não entrarem no histórico git.
# Exporte antes de rodar:
#   export GCA_ADMIN_PASSWORD='...'
#   export GCA_GP_PASSWORD='...'   # opcional: se não setado, reusa GCA_ADMIN_PASSWORD
import os as _os
ADMIN_PASSWORD = _os.environ.get("GCA_ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    print("ERRO: exporte GCA_ADMIN_PASSWORD antes de rodar este script.", file=sys.stderr)
    sys.exit(2)
GP_PASSWORD = _os.environ.get("GCA_GP_PASSWORD") or ADMIN_PASSWORD
PROJECT_SLUG = "financehub-pro"
PROJECT_ID = "9220601b-e006-4e10-9310-ab8aa0fb9250"

OUTPUT_DIR = Path("/home/luiz/GCA/screenshots")
VIEWPORT = {"width": 1440, "height": 900}
NAV_TIMEOUT_MS = 30_000
SETTLE_MS = 1500  # tempo para animações/queries assentarem


@dataclass
class Shot:
    """Representa uma captura: identifica a página, o que abrir antes, e como nomear."""
    n: int
    category: str  # "publica" | "admin" | "projeto"
    slug: str  # base do nome de arquivo
    description: str
    url: Optional[str] = None  # URL relativa (None = depende de pre_action)
    pre_action: Optional[Callable[[Page], Awaitable[None]]] = None
    full_page: bool = True
    settle_ms: int = SETTLE_MS


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

async def safe_goto(page: Page, url: str, base_url: str) -> bool:
    """Navega para URL com timeout, retorna True se sucesso."""
    full_url = url if url.startswith("http") else f"{base_url}{url}"
    try:
        await page.goto(full_url, wait_until="networkidle", timeout=NAV_TIMEOUT_MS)
        return True
    except PWTimeout:
        # 'networkidle' falha se há polling — tentamos só esperar DOM.
        try:
            await page.goto(full_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            return True
        except Exception as e:
            print(f"    ⚠ navegação falhou: {full_url} — {e}")
            return False
    except Exception as e:
        print(f"    ⚠ erro: {full_url} — {e}")
        return False


async def login(page: Page, email: str, password: str, project_slug: Optional[str], base_url: str) -> bool:
    """Faz login na unified login page. project_slug=None entra como admin."""
    if not await safe_goto(page, "/login", base_url):
        return False
    await page.wait_for_timeout(800)

    if project_slug:
        # Combo de projetos é populado via /auth/projects — espera carregar
        try:
            await page.wait_for_selector("select", timeout=8000)
            await page.select_option("select", value=project_slug)
        except Exception as e:
            print(f"    ⚠ não conseguiu selecionar projeto '{project_slug}': {e}")

    # Inputs por type
    await page.fill('input[type="email"]', email)
    await page.fill('input[type="password"]', password)
    await page.click('button[type="submit"]')

    # Aguarda redirecionamento — pode ir para /admin ou /projects
    try:
        await page.wait_for_url(lambda url: "/login" not in url, timeout=15_000)
    except PWTimeout:
        # Pode ter dado erro visível na tela — captura mesmo assim para debug
        print(f"    ⚠ login não redirecionou — talvez credencial inválida")
        return False
    await page.wait_for_timeout(1500)
    return True


async def logout(page: Page, base_url: str) -> None:
    """Limpa storage e volta para login."""
    try:
        await page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
    except Exception:
        pass
    await safe_goto(page, "/login", base_url)
    await page.wait_for_timeout(500)


async def capture(page: Page, shot: Shot, base_url: str) -> dict:
    """Executa pre-action (se houver), navega, espera, captura."""
    print(f"  [{shot.n:02d}] {shot.category:<8} {shot.description[:70]}")
    file_path = OUTPUT_DIR / f"{shot.n:02d}_{shot.category}_{shot.slug}.png"
    result = {
        "n": shot.n,
        "category": shot.category,
        "slug": shot.slug,
        "description": shot.description,
        "file": str(file_path.name),
        "ok": False,
        "url": None,
        "error": None,
    }

    try:
        if shot.url:
            ok = await safe_goto(page, shot.url, base_url)
            if not ok:
                result["error"] = "navegação falhou"
                return result

        if shot.pre_action:
            try:
                await shot.pre_action(page)
            except Exception as e:
                result["error"] = f"pre_action: {e}"
                # captura mesmo com erro parcial
        await page.wait_for_timeout(shot.settle_ms)

        await page.screenshot(path=str(file_path), full_page=shot.full_page)
        result["ok"] = True
        result["url"] = page.url
    except Exception as e:
        result["error"] = str(e)
        print(f"    ✗ falha: {e}")

    return result


# ──────────────────────────────────────────────────────────────────
# Lista de capturas
# ──────────────────────────────────────────────────────────────────

# Pre-actions reutilizáveis para abrir modais / preencher formulários
async def fill_solicitar_passo1(page: Page) -> None:
    """Preenche o passo 1 do wizard /solicitar-projeto para mostrar habilitado."""
    await page.fill('input[placeholder="Ex: Maria Silva"]', "Cliente Demo")
    await page.fill('input[placeholder="voce@empresa.com"]', "cliente@example.com")
    await page.fill('input[placeholder*="previsão do tempo"]', "Sistema Demo do GCA")
    await page.fill(
        'textarea[placeholder*="objetivo"]',
        "Sistema completo para demonstrar as capacidades do GCA, com foco em "
        "governança, geração assistida e documentação viva.",
    )


async def open_solicitar_passo2(page: Page) -> None:
    """Vai do passo 1 para o passo 2 do wizard."""
    await fill_solicitar_passo1(page)
    await page.click('button:has-text("Próximo: requisitos")')
    await page.wait_for_timeout(800)


def shots_publicas() -> list[Shot]:
    """Telas públicas (sem autenticação)."""
    return [
        Shot(
            n=1, category="publica", slug="login",
            description="Tela de login unificada (combo de projetos + email + senha)",
            url="/login",
        ),
        Shot(
            n=2, category="publica", slug="solicitar_projeto_passo1",
            description="Wizard de solicitação — passo 1 (dados básicos + tipo)",
            url="/solicitar-projeto",
            pre_action=fill_solicitar_passo1,
        ),
        Shot(
            n=3, category="publica", slug="solicitar_projeto_passo2",
            description="Wizard de solicitação — passo 2 (perguntas obrigatórias do tipo)",
            url="/solicitar-projeto",
            pre_action=open_solicitar_passo2,
        ),
        Shot(
            n=4, category="publica", slug="reset_password",
            description="Tela de redefinição de senha",
            url="/reset-password",
        ),
    ]


def shots_admin() -> list[Shot]:
    """Telas administrativas (após login admin sem projeto selecionado)."""
    return [
        Shot(
            n=10, category="admin", slug="dashboard",
            description="Admin Dashboard — visão geral do sistema",
            url="/admin",
        ),
        Shot(
            n=11, category="admin", slug="gestao_projetos",
            description="Gestão de Projetos — lista de solicitações e projetos ativos",
            url="/admin/projects",
        ),
        Shot(
            n=12, category="admin", slug="gestao_projetos_detalhes_modal",
            description="Modal 'Detalhes da solicitação' — admin avalia antes de aprovar",
            url="/admin/projects",
            pre_action=lambda p: _open_first_details_modal(p),
        ),
        Shot(
            n=13, category="admin", slug="gestao_usuarios",
            description="Gestão de Usuários — papéis por projeto + filtro",
            url="/admin/users",
        ),
        Shot(
            n=14, category="admin", slug="auditoria_global",
            description="Auditoria Global — log de todas as ações sensíveis",
            url="/admin/audit",
        ),
    ]


async def _open_first_details_modal(page: Page) -> None:
    """Tenta abrir o modal de detalhes do primeiro item pendente da tabela."""
    try:
        # Botão FileText no item pendente — title contém 'Ver detalhes'
        await page.wait_for_selector('button[title*="detalhes da solicitação"]', timeout=5000)
        await page.click('button[title*="detalhes da solicitação"]')
        await page.wait_for_timeout(1000)
    except Exception as e:
        print(f"    ⚠ não conseguiu abrir modal de detalhes: {e}")


def shots_projeto(pid: str) -> list[Shot]:
    """Telas do projeto (após login GP no FinanceHub Pro). Usa UUID do projeto."""
    base = f"/projects/{pid}"
    return [
        Shot(n=20, category="projeto", slug="lista_projetos",
             description="Lista de projetos do GP", url="/projects"),
        Shot(n=21, category="projeto", slug="dashboard",
             description="Dashboard do projeto — visão geral, status, próximos passos",
             url=base),
        Shot(n=22, category="projeto", slug="team",
             description="Equipe — membros, papéis, convites",
             url=f"{base}/team"),
        Shot(n=23, category="projeto", slug="questionnaire",
             description="Questionário inicial (read-only após submissão)",
             url=f"{base}/questionnaire"),
        Shot(n=24, category="projeto", slug="repository",
             description="Repositório do projeto (Git config + verificação)",
             url=f"{base}/repository"),
        Shot(n=25, category="projeto", slug="external_repos",
             description="Repos Externos — referências/legado para análise",
             url=f"{base}/external-repos"),
        Shot(n=26, category="projeto", slug="ingestion",
             description="Ingestão — upload de documentos para o OCG",
             url=f"{base}/ingestion"),
        Shot(n=27, category="projeto", slug="gatekeeper",
             description="Gatekeeper — score dos 7 pilares e bloqueios",
             url=f"{base}/gatekeeper"),
        Shot(n=28, category="projeto", slug="ocg",
             description="OCG — visualização do contexto global do projeto",
             url=f"{base}/ocg"),
        Shot(n=29, category="projeto", slug="arguider",
             description="Arguidor — ajustes de stack e arquitetura",
             url=f"{base}/arguider"),
        Shot(n=30, category="projeto", slug="backlog",
             description="Backlog — itens derivados do OCG",
             url=f"{base}/backlog"),
        Shot(n=31, category="projeto", slug="roadmap",
             description="Roadmap — sequenciamento dos itens em sprints/marcos",
             url=f"{base}/roadmap"),
        Shot(n=32, category="projeto", slug="codegen",
             description="CodeGen — geração de código com editor Monaco",
             url=f"{base}/codegen"),
        Shot(n=33, category="projeto", slug="qa_readiness",
             description="QA Readiness — planos de teste gerados",
             url=f"{base}/qa"),
        Shot(n=34, category="projeto", slug="tester_review",
             description="Revisão do Tester — execução e evidências de testes",
             url=f"{base}/tester-review"),
        Shot(n=35, category="projeto", slug="docs",
             description="Documentação Viva — markdown atualizado a cada commit",
             url=f"{base}/docs"),
        Shot(n=36, category="projeto", slug="readiness",
             description="Readiness — status dos deliverables + Release Bundle",
             url=f"{base}/readiness"),
        Shot(n=37, category="projeto", slug="settings",
             description="Configurações do projeto",
             url=f"{base}/settings"),
        Shot(n=38, category="projeto", slug="audit",
             description="Auditoria do projeto — log local",
             url=f"{base}/audit"),
    ]


# ──────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────

async def main(base_url: str, headed: bool, slow_mo: int) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now().isoformat()
    results: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed, slow_mo=slow_mo)
        context = await browser.new_context(viewport=VIEWPORT, locale="pt-BR")
        page = await context.new_page()

        # ── 1) Telas públicas ──
        print("\n=== TELAS PÚBLICAS ===")
        for shot in shots_publicas():
            results.append(await capture(page, shot, base_url))

        # ── 2) Login admin → telas admin ──
        print("\n=== LOGIN ADMIN ===")
        if await login(page, ADMIN_EMAIL, ADMIN_PASSWORD, project_slug=None, base_url=base_url):
            print("  ✓ admin logado")
            print("\n=== TELAS ADMIN ===")
            for shot in shots_admin():
                results.append(await capture(page, shot, base_url))
        else:
            print("  ✗ login admin falhou — pulando bloco admin")

        # ── 3) Logout → login GP → telas projeto ──
        await logout(page, base_url)
        print("\n=== LOGIN GP ===")
        if await login(page, GP_EMAIL, GP_PASSWORD, project_slug=PROJECT_SLUG, base_url=base_url):
            print(f"  ✓ GP logado em '{PROJECT_SLUG}'")
            print("\n=== TELAS DO PROJETO ===")
            for shot in shots_projeto(PROJECT_ID):
                results.append(await capture(page, shot, base_url))
        else:
            print("  ✗ login GP falhou — pulando bloco projeto")

        await context.close()
        await browser.close()

    # ── Manifest ──
    manifest = {
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(),
        "base_url": base_url,
        "viewport": VIEWPORT,
        "total": len(results),
        "ok": sum(1 for r in results if r["ok"]),
        "failed": sum(1 for r in results if not r["ok"]),
        "shots": results,
    }
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)
    print(f"✓ {manifest['ok']}/{manifest['total']} capturadas com sucesso")
    if manifest["failed"]:
        print(f"✗ {manifest['failed']} falhas (ver manifest.json)")
    print(f"📁 {OUTPUT_DIR}")
    print(f"📋 {manifest_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:5173",
                        help="URL base do frontend (default: http://localhost:5173)")
    parser.add_argument("--headed", action="store_true",
                        help="Mostra o browser durante a captura (debug)")
    parser.add_argument("--slow-mo", type=int, default=0,
                        help="Delay em ms entre ações (debug; default 0)")
    args = parser.parse_args()
    asyncio.run(main(args.base_url, args.headed, args.slow_mo))
