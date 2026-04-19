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

    return report
