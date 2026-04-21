"""MVP 18 Fase 18.4 — testes de busca full-text via SQLite FTS5.

Valida:
- Busca por termo canônico presente nos MDs retorna resultados ordenados.
- Snippet destaca o termo com <mark>...</mark>.
- Termo ausente retorna lista vazia.
- Query vazia retorna lista vazia (curto-circuito).
- Sanitização remove aspas que quebrariam MATCH.
- Acentuação é transparente (tokenize unicode61 remove_diacritics).
- Índice reconstrói automaticamente quando um .md muda (mtime tracking).
- Limit clamp [1, 100] respeitado.
"""
import time
from pathlib import Path

import pytest

from app.services import help_service
from app.services.help_service import search_content


@pytest.fixture(autouse=True)
def _reset_index_between_tests():
    """Garante cache limpo entre testes (evita vazamento de mtime fake)."""
    help_service._reset_index()
    yield
    help_service._reset_index()


# ===========================================================================
# Busca básica contra o corpus canônico (10 capítulos do GCA)
# ===========================================================================

def test_busca_termo_canonico_retorna_resultados():
    """Buscar 'OCG' (acrônimo core do produto) retorna múltiplos capítulos."""
    result = search_content("OCG")
    assert result["backend"] == "fts5"
    assert len(result["results"]) > 0
    # OCG é mencionado em praticamente todos os capítulos — espera >= 5 hits.
    assert len(result["results"]) >= 5
    # Cada hit tem shape canônico.
    for hit in result["results"]:
        assert "section_id" in hit
        assert "title" in hit
        assert "snippet" in hit
        assert "rank" in hit


def test_busca_termo_especifico_retorna_capitulo_certo():
    """'Gatekeeper' tem mais peso em 04-pipeline + 05-ocg."""
    result = search_content("Gatekeeper")
    ids = [h["section_id"] for h in result["results"]]
    assert "04-pipeline" in ids or "05-ocg" in ids or "06-admin" in ids


def test_busca_acronimo_rbac():
    result = search_content("RBAC")
    ids = [h["section_id"] for h in result["results"]]
    assert "03-rbac" in ids, f"RBAC deveria achar cap. 03; achou {ids}"


def test_busca_termo_ausente_retorna_vazio():
    result = search_content("xyzquuxfoobar")
    assert result["results"] == []
    assert result["backend"] == "fts5"


def test_busca_query_vazia_retorna_vazio():
    result = search_content("")
    assert result["results"] == []


def test_busca_query_so_whitespace_retorna_vazio():
    result = search_content("   \t\n  ")
    assert result["results"] == []


# ===========================================================================
# Snippet
# ===========================================================================

def test_snippet_destaca_termo_com_mark():
    result = search_content("OCG")
    assert len(result["results"]) > 0
    first = result["results"][0]
    # FTS5 snippet() envolve o termo no marcador <mark>...</mark>.
    assert "<mark>" in first["snippet"]
    assert "</mark>" in first["snippet"]


def test_snippet_tem_elipses_quando_truncado():
    """snippet() usa ellipsis char '…' quando corta no meio."""
    result = search_content("pipeline")
    assert len(result["results"]) > 0
    # Pelo menos um snippet deve ser parcial (trecho do meio).
    has_ellipsis = any("…" in h["snippet"] for h in result["results"])
    assert has_ellipsis


# ===========================================================================
# Sanitização
# ===========================================================================

def test_sanitize_query_com_aspas_nao_quebra():
    """Aspas na query são removidas pela sanitização — não levantam
    sqlite3.OperationalError."""
    result = search_content('OCG "com aspas"')
    # Não deve levantar; retorna fts5 com ou sem resultados.
    assert result["backend"] == "fts5"


def test_sanitize_query_com_operadores_fts_nao_quebra():
    """Operadores nativos do FTS5 (AND, OR, NEAR, *) são tratados como
    tokens quotados na sanitização, não como operadores."""
    result = search_content("AND OR NEAR")
    assert result["backend"] == "fts5"
    # Tudo ok — sem 500.


def test_sanitize_query_com_caracteres_especiais():
    """Caracteres que o FTS5 poderia interpretar como sintaxe."""
    result = search_content("pipeline!! && *wild")
    assert result["backend"] == "fts5"
    # Ainda retorna results válidos.
    assert isinstance(result["results"], list)


# ===========================================================================
# Acentuação (unicode61 remove_diacritics 2)
# ===========================================================================

def test_busca_com_acento_casa_com_sem_acento_no_corpus():
    """'Codigo' (sem acento) deve achar 'Código' (com acento) e vice-versa."""
    # 'documentação' existe no corpus; 'documentacao' (sem ç) deve casar.
    result_sem = search_content("documentacao")
    assert len(result_sem["results"]) > 0
    result_com = search_content("documentação")
    assert len(result_com["results"]) > 0


def test_busca_case_insensitive():
    lower = search_content("ocg")
    upper = search_content("OCG")
    # Mesmo número de hits.
    assert len(lower["results"]) == len(upper["results"])


# ===========================================================================
# Rebuild automático
# ===========================================================================

def test_index_reconstroi_quando_md_muda(tmp_path, monkeypatch):
    """Criar um .md novo depois da primeira busca deve aparecer na busca
    seguinte (mtime tracking)."""
    # Monta corpus fake isolado.
    (tmp_path / "toc.json").write_text(
        '{"chapters": [{"id": "a", "title": "Alpha", "order": 1}]}',
        encoding="utf-8",
    )
    (tmp_path / "a.md").write_text(
        "# Alpha\n\nconteudo inicial do capitulo alpha.",
        encoding="utf-8",
    )
    monkeypatch.setattr(help_service, "_content_root", lambda: tmp_path)
    help_service._reset_index()

    # 1ª busca — só deve achar "alpha".
    r1 = search_content("alpha")
    ids1 = {h["section_id"] for h in r1["results"]}
    assert "a" in ids1

    # Adiciona novo capítulo.
    time.sleep(0.02)  # garante mtime diferente
    (tmp_path / "b.md").write_text(
        "# Beta\n\nnovo capitulo beta aparece aqui.",
        encoding="utf-8",
    )
    # Precisa atualizar toc também (load_toc lê de lá).
    (tmp_path / "toc.json").write_text(
        '{"chapters": [{"id": "a", "title": "Alpha", "order": 1}, '
        '{"id": "b", "title": "Beta", "order": 2}]}',
        encoding="utf-8",
    )

    # 2ª busca — índice deve ter reconstruído sozinho.
    r2 = search_content("beta")
    ids2 = {h["section_id"] for h in r2["results"]}
    assert "b" in ids2


def test_index_nao_reconstroi_se_nada_mudou():
    """Chamar search_content repetidamente sem mexer nos .md não deve
    invalidar o index (cache hit)."""
    # Força build inicial.
    search_content("OCG")
    # Guarda referência ao conn atual (não deve mudar).
    import app.services.help_service as hs
    conn_before = hs._index_conn

    # Segunda busca — deve reusar o mesmo conn.
    search_content("Gatekeeper")
    conn_after = hs._index_conn
    assert conn_before is conn_after


# ===========================================================================
# Limit
# ===========================================================================

def test_limit_clamp_em_busca_real():
    assert search_content("OCG", limit=0)["limit"] == 1
    assert search_content("OCG", limit=500)["limit"] == 100
    # Valor válido preservado.
    r = search_content("OCG", limit=3)
    assert r["limit"] == 3
    # Respeitado no retorno — no máx 3 results.
    assert len(r["results"]) <= 3


def test_limit_reduz_resultados_efetivamente():
    all_hits = search_content("OCG", limit=100)
    top2 = search_content("OCG", limit=2)
    assert len(top2["results"]) <= 2
    # Top-2 devem ser os 2 primeiros do ranking completo.
    if len(all_hits["results"]) >= 2:
        assert top2["results"][0]["section_id"] == all_hits["results"][0]["section_id"]
        assert top2["results"][1]["section_id"] == all_hits["results"][1]["section_id"]


# ===========================================================================
# Ordenação por rank
# ===========================================================================

def test_resultados_ordenados_por_rank():
    """FTS5 rank é crescente (menor = mais relevante)."""
    result = search_content("OCG")
    ranks = [h["rank"] for h in result["results"]]
    assert ranks == sorted(ranks), f"Resultados não ordenados: {ranks}"
