-- Migration 070 — Saneamento de schema por recomendações DBA pós-Gatekeeper
-- (sessão dogfood AJA 2026-05-04 BRT).
--
-- Três mudanças independentes, todas baixo risco e reversíveis:
--
-- 1. DROP INDEX redundantes em audit_log_global
--    Origem: DBA F1 R1. Tabela tem 4 índices onde 2 são suficientes
--    (`idx_audit_log_created_at` + `ix_audit_log_global_created_at`,
--    `idx_audit_log_event_type` + `ix_audit_log_global_event_type`).
--    Cada INSERT pagava custo de manter os 4. Mantemos os `ix_*`
--    (gerados pelo ORM Alembic, padrão convencional).
--
-- 2. ADD INDEX composto em persona_follow_up_questions
--    Origem: DBA F2 R1. UPDATE do _process_followup_upload filtra
--    em loop por (id, project_id, persona_id, status='pending').
--    Volume baixo hoje (1-5 HITLs/dia/projeto) mas o índice composto
--    elimina seq-scan em projetos com muitas PFQs históricas.
--
-- 3. ALTER trigger_source para String(50) em project_backups
--    Origem: DBA F2 R2. ocg_delta_log.trigger_source é VARCHAR(50);
--    project_backups.trigger_source é VARCHAR(40). Inconsistência
--    causa surpresa em código que assume largura uniforme.
--
-- CONCURRENTLY em DROP/CREATE INDEX evita travar writes durante
-- a operação. Não cabe em transação — cada CONCURRENTLY é auto-commit.

DROP INDEX CONCURRENTLY IF EXISTS idx_audit_log_created_at;
DROP INDEX CONCURRENTLY IF EXISTS idx_audit_log_event_type;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pfq_project_persona_status
  ON persona_follow_up_questions (project_id, persona_id, status);

-- ALTER COLUMN cabe em transação (não é CONCURRENTLY).
-- VARCHAR widening é metadata-only no Postgres ≥ 9.2 — não reescreve
-- linhas, não trava writes além de um lock breve.
ALTER TABLE project_backups
  ALTER COLUMN trigger_source TYPE VARCHAR(50);
