# MVP 8 Fase 6 — Fixtures reais de regressão

Arquivos usados no pipeline de ingestão do projeto Automação Jurídica
durante o dogfood 2026-04-19. Servem como baseline de regressão pro
extractor (rich_docx + pdf_layered + extraction_report).

Total: ~400 KB. Fixtures sob 1 MB — fácil versionar.

## Inventário

| Arquivo | Tamanho | Tipo | Origem | Propósito |
|---|---|---|---|---|
| `automacao_juridica_v2.docx` | 50 KB | .docx | Versão 2.0 consolidada do documento de requisitos | Doc rico: ~32k chars, 94 RFs (RF-01..RF-94), 9 RNFs, paragraphs only |
| `gca_template_ingestao.docx` | 41 KB | .docx | Template padrão GCA distribuído a clientes | Doc simples: ~8k chars, paragraphs only, sem tabelas |
| `datajud_documento_tecnico.pdf` | 312 KB | .pdf | Documento Técnico de Integração DataJud | PDF com texto pesquisável real — exercita camadas 1+2 do pdf_layered_extractor |

## Política

- Sem dados de cliente externo. Tudo dogfood do GCA.
- Asserts dos testes são "mínimo esperado" (ex: `>= 50 RFs` em vez de `== 94`)
  — permite que o LLM/regex evoluam sem quebrar testes.
- Se um fixture precisar ser atualizado, documentar motivo no commit.

Fixtures maiores (docs de clientes reais, PDFs escaneados de milhões de
páginas, anexos MMS) devem ficar fora do repo — usar fixture sintético
in-memory (já existente em `test_mvp8_rich_docx.py` etc) ou path absoluto
via env var.
