-- Migration 071 — F5.1/F5.2 ingestão assíncrona OCG
-- Pós-Gatekeeper (GP + Arquiteto + DBA aprovados em 2026-05-04 BRT).
--
-- Contexto: callback /ingestion-complete do n8n Consolidador era síncrono
-- com chamada LLM de 30-60s+ (causava timeout 300s no nó Callback GCA).
-- Workaround f12e234 elevou pra 900s. F5.1 corrige arquiteturalmente:
-- handler retorna 202 imediato, processamento OCG move pra Celery task.
-- F5.2 adiciona polling REST no frontend pra UX feedback.
--
-- 3 mudanças schema-only:
--
-- 1. celery_task_id em ingested_documents (Arq RC: depuração via Flower).
--    VARCHAR(64) cobre UUIDs Celery padrão. Sem índice — lookup ocasional
--    para debug humano, não caminho crítico (DBA aprovado).
--
-- 2. ocg_update_duration_ms em ocg_delta_log (Arq RC-4: telemetria).
--    INTEGER millisegundos. Populado pelo OCGUpdaterService.
--    Custo: 4 bytes/row em log de baixo volume.
--
-- 3. COMMENT ON COLUMN canônico de arguider_status (DBA CO-2).
--    Inventário completo dos 7 valores em uso (pending, processing,
--    ocg_updating NOVO, ocg_pending, completed, partial, error).
--    arguider_status é VARCHAR(20) sem CHECK constraint — confirmado
--    pelo DBA via pg_constraint. Adicionar ocg_updating não exige ALTER.

BEGIN;

ALTER TABLE ingested_documents
  ADD COLUMN IF NOT EXISTS celery_task_id VARCHAR(64);

ALTER TABLE ocg_delta_log
  ADD COLUMN IF NOT EXISTS ocg_update_duration_ms INTEGER;

COMMENT ON COLUMN ingested_documents.arguider_status IS
  'pending | processing | ocg_updating | ocg_pending | completed | partial | error';

COMMIT;
