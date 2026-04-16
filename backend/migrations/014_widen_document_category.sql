-- 014 — Aumentar coluna document_category para acomodar categorias verbosas do LLM
--
-- Contexto: Arguidor armazena `classification.category` (texto livre do LLM)
-- em ingested_documents.document_category VARCHAR(30). LLMs (especialmente
-- DeepSeek e Claude com prompts em PT-BR) retornam categorias como
-- "Artefato de Ingestão Externa" (32 chars) ou "external_repository_analysis"
-- (28 chars). Resultado: StringDataRightTruncationError → análise inteira
-- do Arguidor é abortada e o documento fica preso em status='processing'.
--
-- Solução: aumentar para VARCHAR(120) — folga suficiente para qualquer
-- categoria razoável sem desperdiçar espaço.

BEGIN;

ALTER TABLE ingested_documents
    ALTER COLUMN document_category TYPE VARCHAR(120);

COMMENT ON COLUMN ingested_documents.document_category IS
    'Categoria classificada pelo Arguidor (texto livre do LLM, até 120 chars)';

COMMIT;
