-- MVP 8 Fase 1 — Feedback de progresso na ingestão.
-- Adiciona colunas para rastrear estágio atual e porcentagem do pipeline
-- do Arguidor em cada documento, permitindo ao frontend renderizar
-- barra de progresso real em vez de "Processando" estático.
--
-- Estágios canônicos:
--   queued              — aguardando análise (status=pending)
--   extracting_text     — Arguidor extraindo texto do arquivo
--   analyzing           — Arguidor rodando análise LLM (ida+volta com provider)
--   updating_ocg        — OCGUpdater aplicando deltas ao OCG
--   regenerating_backlog — propagação: backlog/roadmap/gatekeeper
--   completed           — pipeline terminou com sucesso
--   failed              — alguma etapa falhou (ver arguider_error_message)
--
-- Porcentagens-alvo (bucket por estágio, ajuste a gosto do frontend):
--   queued              →   0
--   extracting_text     →  10
--   analyzing           →  40
--   updating_ocg        →  70
--   regenerating_backlog → 90
--   completed           → 100
--   failed              → valor do último estágio atingido

BEGIN;

ALTER TABLE ingested_documents
    ADD COLUMN IF NOT EXISTS arguider_stage VARCHAR(40)
        NOT NULL DEFAULT 'queued';

ALTER TABLE ingested_documents
    ADD COLUMN IF NOT EXISTS arguider_progress_percent SMALLINT
        NOT NULL DEFAULT 0
        CHECK (arguider_progress_percent BETWEEN 0 AND 100);

ALTER TABLE ingested_documents
    ADD COLUMN IF NOT EXISTS arguider_stage_updated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_ingested_docs_progress
    ON ingested_documents (project_id, arguider_stage, arguider_progress_percent);

COMMIT;
