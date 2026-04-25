-- Reforma Arguidor #1 (2026-04-25): documento canônico tem precedência.
-- Quando o owner ingere uma Ata de Decisões Canônicas, RFC formal, charter,
-- ou qualquer doc marcado is_canonical_decision=TRUE, suas declarações
-- substituem valores antigos no OCG (não geram gap punitivo).
--
-- Auto-detecção: category contém 'canonica'/'canonical' OU filename
-- bate em DECISOES_CANONICAS / CANONICAL_DECISION / ATA_DECISOES.

ALTER TABLE ingested_documents
    ADD COLUMN is_canonical_decision BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX ix_ingested_canonical
    ON ingested_documents (project_id, created_at DESC)
    WHERE is_canonical_decision IS TRUE;

COMMENT ON COLUMN ingested_documents.is_canonical_decision IS
    'Decisão soberana do owner. Substitui valores antigos no OCG; conflitos posteriores não punem score.';

-- Backfill retroativo: docs já ingeridos com indícios óbvios de decisão canônica
-- (filename contém DECISOES_CANONICAS, ATA_DECISOES, etc) ganham a flag.
UPDATE ingested_documents
SET is_canonical_decision = TRUE
WHERE is_canonical_decision IS FALSE
  AND (
        original_filename ILIKE '%DECISOES_CANONICAS%'
     OR original_filename ILIKE '%CANONICAL_DECISION%'
     OR original_filename ILIKE '%ATA_DECISOES%'
     OR original_filename ILIKE '%DECISION_RECORD%'
     OR document_category ILIKE '%decisoes_canonicas%'
     OR document_category ILIKE '%canonical_decision%'
  );
