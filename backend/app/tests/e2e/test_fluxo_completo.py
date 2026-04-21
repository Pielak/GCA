"""
Testes E2E do fluxo completo do GCA — pós Fase 6.

Cobre: Login → Dashboard → Projeto → Ingestão → Gatekeeper →
       LiveDocs → Roadmap → Code Generator → Legacy → Merge.

MVP 11 Fase 11.7: arquivo sai do `--ignore` e integra-se à suite via
marker `e2e`. Execução default de `pytest` (caminho canônico do
backend) roda com `-m "not e2e"` — portanto este arquivo é coletado mas
os testes são pulados. Lane dedicada `-m e2e` executa em pipeline
separado com playwright instalado e ambiente gca-frontend/backend up.

Configurável via env vars:
  E2E_BASE_URL (default http://gca-frontend:4173)
  E2E_API_URL  (default http://gca-backend:8000)
  E2E_ADMIN_EMAIL / E2E_ADMIN_PASS
  E2E_PROJECT_ID
"""
import os

import pytest

# playwright é dependência opcional — só instalada na lane e2e dedicada.
# Em ambientes sem playwright, o módulo inteiro é pulado na coleta.
pytest.importorskip("playwright", reason="playwright não instalado (lane e2e dedicada)")
from playwright.async_api import async_playwright, Page, Browser

# MVP 11 Fase 11.7 — marker aplicado no módulo inteiro.
pytestmark = pytest.mark.e2e

BASE_URL = os.environ.get("E2E_BASE_URL", "http://gca-frontend:4173")
API_URL = os.environ.get("E2E_API_URL", "http://gca-backend:8000")
ADMIN_EMAIL = os.environ.get("E2E_ADMIN_EMAIL", "admin@gca-test.com")
ADMIN_PASS = os.environ.get("E2E_ADMIN_PASS", "SenhaAdmin@2026")
PROJECT_ID = os.environ.get("E2E_PROJECT_ID", "1")


# ──── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
async def browser():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        yield b
        await b.close()


@pytest.fixture
async def page(browser: Browser):
    p = await browser.new_page()
    yield p
    await p.close()


async def login(page: Page) -> None:
    """Helper: autentica como admin.

    MVP 14 Fase 14.4: seletores ajustados pro estado atual do
    `LoginPage.tsx` — input usa `type=` sem `name=`; redirect pós-login
    vai para `/` (não `/dashboard`).
    """
    await page.goto(f"{BASE_URL}/login")
    await page.fill('input[type="email"]', ADMIN_EMAIL)
    await page.fill('input[type="password"]', ADMIN_PASS)
    await page.click('button[type="submit"]')
    # Redirect pós-login vai para `/` (landing), não `/dashboard`.
    await page.wait_for_url(f"{BASE_URL}/", timeout=10_000)


# ──── Testes ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_01_setup_status_nao_exige_setup(page: Page):
    """Sistema configurado → needs_setup deve ser false."""
    resp = await page.request.get(f"{API_URL}/api/v1/setup/status")
    data = await resp.json()
    assert data["needs_setup"] is False


@pytest.mark.asyncio
async def test_e2e_02_login_redireciona_dashboard(page: Page):
    """Login com credenciais válidas → redireciona para raiz `/`.

    MVP 14 Fase 14.4: frontend atual redireciona pós-login para `/`
    (landing), não `/dashboard`. Nome do teste mantido por trilha
    histórica.
    """
    await login(page)
    assert page.url.rstrip("/") == BASE_URL.rstrip("/")


# TODO MVP 14.4 (ou fase separada de rewrite e2e): tests 03-14 estão
# defasados contra rotas atuais do frontend. Precisam rewrite contra:
# - /dashboard pode não existir como rota isolada
# - /projects/{id}/... espera UUID, não string "1" do fixture
# - /admin path e conteúdo podem ter mudado
# - Seletores de texto ("Ingestão de Documentos", "Gatekeeper", etc)
#   dependem de literais que podem ter mudado nas refactorings do
#   frontend (MVPs 8/9/10/11/12).
# Decisão: escopo do canário Fase 14.4 já validou infra (rebuild,
# vite allowedHosts, seletor email/password, email admin pydantic-
# válido, redirect /). Tests 03-14 são lane separada.


@pytest.mark.asyncio
async def test_e2e_03_dashboard_carrega_sem_erro_500(page: Page):
    """Dashboard deve carregar com HTTP 200."""
    await login(page)
    resp = await page.goto(f"{BASE_URL}/dashboard")
    assert resp and resp.status < 500


@pytest.mark.asyncio
async def test_e2e_04_ingestion_page_carrega(page: Page):
    """IngestionPage deve carregar e exibir a drop zone."""
    await login(page)
    await page.goto(f"{BASE_URL}/projects/{PROJECT_ID}/ingestion")
    await page.wait_for_selector('text=Ingestão de Documentos', timeout=8_000)
    assert "ingestion" in page.url


@pytest.mark.asyncio
async def test_e2e_05_gatekeeper_page_carrega(page: Page):
    """GatekeeperPage deve carregar e exibir a lista de módulos."""
    await login(page)
    await page.goto(f"{BASE_URL}/projects/{PROJECT_ID}/gatekeeper")
    await page.wait_for_selector('text=Gatekeeper', timeout=8_000)
    assert "gatekeeper" in page.url


@pytest.mark.asyncio
async def test_e2e_06_livedocs_page_carrega(page: Page):
    """LiveDocsPage deve carregar e exibir a sidebar de navegação."""
    await login(page)
    await page.goto(f"{BASE_URL}/projects/{PROJECT_ID}/docs")
    await page.wait_for_selector('text=Documentação', timeout=8_000)
    assert "docs" in page.url


@pytest.mark.asyncio
async def test_e2e_07_roadmap_page_carrega(page: Page):
    """RoadmapPage deve carregar e exibir o progresso geral."""
    await login(page)
    await page.goto(f"{BASE_URL}/projects/{PROJECT_ID}/roadmap")
    await page.wait_for_selector('text=Roadmap', timeout=8_000)
    assert "roadmap" in page.url


@pytest.mark.asyncio
async def test_e2e_08_legacy_page_carrega(page: Page):
    """LegacyPage deve carregar e exibir o seletor de fonte."""
    await login(page)
    await page.goto(f"{BASE_URL}/projects/{PROJECT_ID}/legacy")
    await page.wait_for_selector('text=Legado', timeout=8_000)
    assert "legacy" in page.url


@pytest.mark.asyncio
async def test_e2e_09_merge_page_carrega(page: Page):
    """MergeEnginePage deve carregar e exibir o seletor de módulos."""
    await login(page)
    await page.goto(f"{BASE_URL}/projects/{PROJECT_ID}/merge")
    await page.wait_for_selector('text=Merge', timeout=8_000)
    assert "merge" in page.url


@pytest.mark.asyncio
async def test_e2e_10_code_generator_sidebar_visivel(page: Page):
    """CodeGenerator IDE-like deve ter sidebar Git visível."""
    await login(page)
    await page.goto(f"{BASE_URL}/projects/{PROJECT_ID}/codegen")
    await page.wait_for_selector('text=Repositório', timeout=8_000)
    assert await page.locator('text=Repositório').is_visible()


@pytest.mark.asyncio
async def test_e2e_11_sidebar_colapsavel(page: Page):
    """Sidebar do Code Generator deve alternar ao clicar no toggle."""
    await login(page)
    await page.goto(f"{BASE_URL}/projects/{PROJECT_ID}/codegen")
    await page.wait_for_selector('text=Repositório', timeout=8_000)

    toggle = page.locator('[title*="árvore"], [title*="Fechar"], [title*="Abrir"]').first
    visivel_antes = await page.locator('text=Repositório').is_visible()
    await toggle.click()
    await page.wait_for_timeout(500)
    visivel_depois = await page.locator('text=Repositório').is_visible()

    assert visivel_antes != visivel_depois


@pytest.mark.asyncio
async def test_e2e_12_helptooltip_visivel_em_ingestion(page: Page):
    """HelpTooltip deve aparecer ao hover do ícone '?' na IngestionPage."""
    await login(page)
    await page.goto(f"{BASE_URL}/projects/{PROJECT_ID}/ingestion")
    await page.wait_for_selector('[aria-label="Ajuda sobre este campo"]', timeout=8_000)

    icone = page.locator('[aria-label="Ajuda sobre este campo"]').first
    await icone.hover()
    await page.wait_for_selector('[role="tooltip"]', timeout=2_000)
    tooltip = page.locator('[role="tooltip"]').first

    assert await tooltip.is_visible()
    texto = await tooltip.text_content()
    assert len(texto or '') > 20


@pytest.mark.asyncio
async def test_e2e_13_admin_settings_aba_acessivel(page: Page):
    """Admin deve conseguir acessar a aba de Configurações GCA."""
    await login(page)
    await page.goto(f"{BASE_URL}/admin")
    await page.wait_for_selector('text=Configurações', timeout=8_000)
    await page.click('text=Configurações')
    await page.wait_for_selector('text=Pesos dos Pilares', timeout=5_000)
    assert await page.locator('text=Pesos dos Pilares').is_visible()


@pytest.mark.asyncio
async def test_e2e_14_smoke_todas_as_rotas(page: Page):
    """
    Smoke test: todas as páginas devem responder com HTTP < 500.
    """
    await login(page)
    rotas = [
        "/dashboard",
        f"/projects/{PROJECT_ID}/ingestion",
        f"/projects/{PROJECT_ID}/gatekeeper",
        f"/projects/{PROJECT_ID}/docs",
        f"/projects/{PROJECT_ID}/roadmap",
        f"/projects/{PROJECT_ID}/legacy",
        f"/projects/{PROJECT_ID}/merge",
        f"/projects/{PROJECT_ID}/codegen",
        "/admin",
        "/admin/users",
        "/admin/projects",
        "/admin/audit",
    ]
    erros = []
    for rota in rotas:
        resp = await page.goto(f"{BASE_URL}{rota}")
        if resp and resp.status >= 500:
            erros.append(f"{rota} → HTTP {resp.status}")

    assert erros == [], f"Rotas com erro 5xx: {erros}"
