-- Migration 007: Audit chain completo + role Stakeholder
-- Data: 2026-04-09

-- 1. Adicionar current_hash e correlation_id ao audit_log_global
ALTER TABLE audit_log_global ADD COLUMN IF NOT EXISTS current_hash VARCHAR(64);
ALTER TABLE audit_log_global ADD COLUMN IF NOT EXISTS correlation_id UUID;

-- Preencher current_hash para registros existentes (hash do conteúdo)
UPDATE audit_log_global
SET current_hash = encode(sha256(
    (COALESCE(event_type, '') || '|' || COALESCE(resource_type, '') || '|' ||
     COALESCE(actor_id::text, '') || '|' || COALESCE(resource_id::text, '') || '|' ||
     COALESCE(details, '') || '|' || COALESCE(previous_hash, ''))::bytea
), 'hex')
WHERE current_hash IS NULL;

-- Tornar NOT NULL após preencher
ALTER TABLE audit_log_global ALTER COLUMN current_hash SET NOT NULL;

-- Índice para correlation_id
CREATE INDEX IF NOT EXISTS idx_audit_log_correlation ON audit_log_global(correlation_id);

-- 2. Adicionar campo quarantine_status e pii_detected ao ingested_documents
ALTER TABLE ingested_documents ADD COLUMN IF NOT EXISTS quarantine_status VARCHAR(20) DEFAULT 'none';
ALTER TABLE ingested_documents ADD COLUMN IF NOT EXISTS pii_detected BOOLEAN DEFAULT FALSE;
ALTER TABLE ingested_documents ADD COLUMN IF NOT EXISTS pii_fields TEXT;

-- 3. Adicionar version e schema_version ao OCG
ALTER TABLE ocg ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1;
ALTER TABLE ocg ADD COLUMN IF NOT EXISTS schema_version VARCHAR(20) DEFAULT '1.0.0';
