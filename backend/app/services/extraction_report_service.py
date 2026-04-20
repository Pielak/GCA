"""MVP 8 Fase 5 — Relatório de extração.

Calcula estatísticas sobre o que os extratores (rich_docx + pdf_layered
+ vision OCR) entenderam do documento ingerido. Serve pra UI exibir ao
GP **antes** dele decidir se a análise do Arguidor faz sentido — se o
relatório mostra "0 tabelas detectadas" num doc cheio de tabelas, o GP
sabe que o extractor falhou e pode reenviar o doc em outro formato,
sem gastar tokens em LLM em cima de texto quebrado.

Contrato §7 MVP 8 Fase 5:
  - nº de parágrafos, tabelas convertidas, caixas de texto,
    headers/footers;
  - camadas de PDF usadas (acroform / text / ocr);
  - primeiros N RFs e módulos detectados por heurística simples;
  - warnings do extractor.

Propriedades:
  - Puro: recebe bytes + file_type, retorna dict. Sem I/O de DB,
    sem LLM, sem side effects.
  - Rápido: usa os mesmos extratores já em memória (não duplica
    trabalho do pipeline de análise).
"""
from __future__ import annotations

import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# Heurísticas simples — Fase 5 só reporta, não consolida.
RF_PATTERN = re.compile(r"\bRF[-\s]?\d{2,4}\b", re.IGNORECASE)
RNF_PATTERN = re.compile(r"\bRNF[-\s]?\d{2,4}\b", re.IGNORECASE)
MODULE_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:m[oó]dulo|serviço|componente)\s+[^\n\.,;]{3,80}",
    re.IGNORECASE | re.MULTILINE,
)

# MVP 8 Fase 4 — detectores de seções implícitas.
# Afirmações normativas sem prefixo RF- mas com estrutura de requisito.
# Aceita frase começando por "o/a/os/as sujeito deve/pode/poderá/...".
IMPLICIT_REQ_PATTERN = re.compile(
    r"(?:^|(?<=[\.\n]))\s*"
    r"(?:O|A|Os|As)\s+[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s_-]{1,40}?\s+"
    r"(?:deve[rá]{0,2}|pode[rá]{0,2}|precisa|tem que|não pode|é obrigat[óo]ri[oa])"
    r"[^\.\n]{10,200}",
    re.MULTILINE,
)

# Entregáveis/deliverables — frases com verbo de produção/entrega explícito.
DELIVERABLE_PATTERNS = [
    re.compile(
        r"(?:ser[áã]o?|deve[mr]?\s+ser)\s+"
        r"(?:entregue|produzid|gerad|elaborad|disponibilizad|document[ao]d|implementad|test[ao]d)"
        r"[ao]s?\s+[^\.\n]{5,150}",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:^|\n)\s*(?:entreg[áa]vel|deliverable|artefato)\s*[:\-]\s*[^\.\n]{5,150}",
        re.IGNORECASE | re.MULTILINE,
    ),
]

# Fases/marcos temporais — ordenação cronológica explícita.
PHASE_PATTERNS = [
    re.compile(r"(?:^|\n)\s*(?:fase|sprint|etapa|mês|marco|milestone)\s+\d+"
               r"[:\-\s]+[^\.\n]{3,150}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"(?:\d+)\s*(?:º|ª)\s+(?:fase|sprint|etapa)"
               r"[^\.\n]{0,120}", re.IGNORECASE),
]


def build_extraction_report(
    file_bytes: bytes,
    file_type: str,
    *,
    max_preview_items: int = 10,
) -> dict[str, Any]:
    """Gera relatório estruturado do que o pipeline entende do documento.

    Retorna dict com chaves fixas pra UI consumir direto:

        {
          "ok": bool,             # True se algum texto foi extraído
          "file_type": str,
          "chars": int,           # total de chars no texto final
          "paragraphs": int,
          "tables_detected": int,
          "text_boxes": int,
          "headers_footers": int,
          "pdf_layers": list[str],# ["acroform", "text", "ocr"]
          "pdf_pages_with_text": int,
          "acroform_fields": int,
          "requirements_functional": list[str],    # primeiros N "RF-..."
          "requirements_non_functional": list[str],# primeiros N "RNF-..."
          "module_hints": list[str],               # primeiros N "Módulo X"
          "warnings": list[str],
          "text_sample": str,     # primeiros 500 chars (preview)
        }
    """
    report: dict[str, Any] = {
        "ok": False,
        "file_type": file_type,
        "chars": 0,
        "paragraphs": 0,
        "tables_detected": 0,
        "text_boxes": 0,
        "headers_footers": 0,
        "pdf_layers": [],
        "pdf_pages_with_text": 0,
        "acroform_fields": 0,
        "requirements_functional": [],
        "requirements_non_functional": [],
        "module_hints": [],
        # MVP 8 Fase 4 — seções implícitas (heurísticas). Sempre listas,
        # vazias quando doc não ativa a heurística. UI mostra chips só
        # quando populado.
        "implicit_requirements": [],
        "deliverables_hints": [],
        "phases_hints": [],
        "warnings": [],
        "text_sample": "",
    }

    if not file_bytes:
        report["warnings"].append("Arquivo vazio — 0 bytes.")
        return report

    text = ""
    try:
        if file_type in ("docx", "doc"):
            from app.services.rich_docx_extractor import extract_rich_text
            text = extract_rich_text(file_bytes) or ""
        elif file_type == "pdf":
            from app.services.pdf_layered_extractor import extract_pdf_layered
            pdf = extract_pdf_layered(file_bytes)
            text = pdf.text
            report["pdf_layers"] = list(pdf.layers_used)
            report["acroform_fields"] = len(pdf.acroform_fields or {})
            report["pdf_pages_with_text"] = sum(
                1 for p in (pdf.pages_text or []) if p and p.strip()
            )
            report["warnings"].extend(pdf.warnings or [])
        elif file_type in ("markdown", "md", "txt"):
            text = file_bytes.decode("utf-8", errors="replace")
        else:
            report["warnings"].append(
                f"Tipo '{file_type}' não tem extractor rico — relatório limitado."
            )
            try:
                text = file_bytes.decode("utf-8", errors="replace")
            except Exception:
                text = ""
    except Exception as exc:
        logger.warning("extraction_report.extract_failed", error=str(exc), file_type=file_type)
        report["warnings"].append(f"Falha na extração: {exc}")
        return report

    if not text or not text.strip():
        report["warnings"].append(
            "Nenhum texto foi extraído. Documento pode estar em formato "
            "não suportado, vazio, ou totalmente imagem (sem OCR)."
        )
        return report

    report["ok"] = True
    report["chars"] = len(text)
    report["text_sample"] = text[:500]

    # Parágrafos: blocos separados por \n\n que contenham algo
    report["paragraphs"] = sum(
        1 for block in text.split("\n\n") if block.strip()
    )

    # Tabelas: pareia [TABELA] ... [/TABELA] emitido pelo rich_docx
    report["tables_detected"] = text.count("[TABELA]")

    # Caixas de texto e headers/footers: tags emitidas pelo rich_docx
    report["text_boxes"] = text.count("[CAIXA DE TEXTO]")
    report["headers_footers"] = text.count("[HEADER ") + text.count("[FOOTER ")

    # Heurísticas de RFs / RNFs / módulos — primeiros N únicos
    def _unique_preserving_order(items, limit):
        seen = set()
        out = []
        for item in items:
            normalized = item.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                out.append(normalized)
                if len(out) >= limit:
                    break
        return out

    rf_matches = RF_PATTERN.findall(text)
    report["requirements_functional"] = _unique_preserving_order(rf_matches, max_preview_items)

    rnf_matches = RNF_PATTERN.findall(text)
    report["requirements_non_functional"] = _unique_preserving_order(rnf_matches, max_preview_items)

    module_matches = [m.strip().rstrip(".,;") for m in MODULE_PATTERN.findall(text)]
    report["module_hints"] = _unique_preserving_order(module_matches, max_preview_items)

    # MVP 8 Fase 4 — heurísticas de seções implícitas.
    # Requisitos sem prefixo RF-/RNF- mas com estrutura normativa.
    implicit_matches = [
        _normalize_match(m) for m in IMPLICIT_REQ_PATTERN.findall(text)
    ]
    report["implicit_requirements"] = _unique_preserving_order(
        implicit_matches, max_preview_items,
    )

    # Entregáveis/deliverables via verbos de produção.
    deliverable_matches: list[str] = []
    for pat in DELIVERABLE_PATTERNS:
        deliverable_matches.extend(_normalize_match(m) for m in pat.findall(text))
    report["deliverables_hints"] = _unique_preserving_order(
        deliverable_matches, max_preview_items,
    )

    # Fases/sprints/etapas com número explícito.
    phase_matches: list[str] = []
    for pat in PHASE_PATTERNS:
        phase_matches.extend(_normalize_match(m) for m in pat.findall(text))
    report["phases_hints"] = _unique_preserving_order(
        phase_matches, max_preview_items,
    )

    return report


def _normalize_match(s: str) -> str:
    """Compacta whitespace e trima pontuação solta das pontas."""
    if not s:
        return ""
    compact = re.sub(r"\s+", " ", s).strip()
    return compact.strip(".,;:-— \t")
