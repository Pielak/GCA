# Arquivo — Ingestão inteligente de documentos

MVP 8. Extraído de `GCA_CANONICAL_CONTRACT.md` em 2026-04-22 como parte da reforma documental.

---

### MVP 8 — Ingestão inteligente de documentos

**Motivação:** o dogfood 2026-04-19 expôs dois problemas operacionais que travam o usuário final:

1. **Documentos em formato técnico inadequado não alimentam o OCG.** O Arguidor usa `python-docx` lendo apenas `Document.paragraphs[].text`; tabelas de `.docx` ficam invisíveis. Na prática, cliente sobe documento aparentemente rico (RFs em tabela, diagramas, anexos), o pipeline não vê nada, OCG não evolui, backlog fica vazio, roadmap não é gerado. Cliente ficou sem saber por que "nada aconteceu". O protocolo atual (DT-064 + fallback automático) só resolve erro de provedor; não resolve a qualidade do conteúdo extraído.

2. **Ausência de feedback visível de progresso no processamento.** Frontend mostra apenas "Processando" estático. Pipelines de OCG + Gatekeeper + Arguidor podem levar minutos em IA local. Usuário comum interpreta como travado e abandona ou fica reiniciando.

Este MVP resolve ambos de forma definitiva. Pré-processamento interno é invisível ao usuário — ele sobe qualquer formato esperado (`.docx`, `.pdf`, `.md`, `.txt`) e o GCA normaliza antes de entregar ao Arguidor.

#### Em escopo

- **Fase 1 — Feedback de progresso (urgente):** colunas `arguider_stage` e `arguider_progress_percent` em `ingested_documents`; backend atualiza em cada marco (extração, análise por pilar, consolidação, backlog/roadmap); frontend com barra de progresso real, texto do estágio atual e tempo decorrido; polling adaptativo (2s enquanto processando, para ao concluir).
- **Fase 2 — Extração rica de `.docx`:** pré-parser que percorre o `Document` inteiro e transforma **tabelas em parágrafos estruturados** no formato `[Coluna1: valor] [Coluna2: valor]` legível pelo Arguidor; extrai também `<w:sdt>`, listas aninhadas, caixas de texto, notas de rodapé.
- **Fase 3 — Extração rica de `.pdf`:** pipeline em camadas — tentar AcroForm → tentar texto pesquisável → OCR (Tesseract ou provedor IA) como fallback. Deduplicar conteúdo entre camadas.
- **Fase 4 — Normalização com heurísticas:** detector automático de seções "entregáveis", "módulos", "fases", "requisitos funcionais" por sinais textuais (prefixos "RF-", "Fase N", listas numeradas). Quando o documento não declara explicitamente, o pré-processador infere e anota.
- **Fase 5 — Relatório de extração ao usuário:** ao final da extração (antes do Arguidor), a UI mostra o que foi entendido (quantos RFs, módulos, entregáveis, fases) e permite o usuário confirmar ou rejeitar antes de prosseguir com o Arguidor.
- **Fase 6 — Testes de regressão com documentos reais:** suite de fixtures com `.docx` problemáticos conhecidos (v1.0 da Automação Jurídica, PDFs escaneados, docs mistos) validando extração mínima esperada.

#### Fora de escopo

- edição in-loco do documento pelo usuário dentro do GCA (MVP futuro);
- formatos proprietários fora de `.docx/.pdf/.md/.txt` (Pages, Keynote, RTF binário antigo);
- OCR com modelo de layout (LayoutLM, Donut) — nesta fase, Tesseract ou LLM genérico bastam;
- rewrite automático de trechos ambíguos — o pré-processador **extrai e estrutura**, mas **não reescreve conteúdo do usuário**;
- tradução automática de documentos em outro idioma;
- análise de qualidade semântica do documento (isso continua no Arguidor).

---
