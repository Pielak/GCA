-- 066_mvp31_consolidate_ocg_tables.sql
-- MVP 31 Fase 31.1 — consolidação de schema + integridade + performance
-- Aprovado pelos Gates 1+2+3 (2026-05-02)
--
-- ADAPTAÇÃO ao mandato original (Gate 3):
-- ix_ocg_questionnaire_id NÃO é dropado pois é UNIQUE (garante integridade
-- referencial em questionnaires.id). Em seu lugar, dropa-se idx_ocg_questionnaire_id
-- (índice não-único redundante, gerado manualmente em __table_args__).
-- Registrado como ressalva para o Gate 3.

BEGIN;

-- =============================================================================
-- 1. ocg_individual.persona_id: uuid REFERENCES users(id) → VARCHAR(20) (tag canônica)
-- =============================================================================
ALTER TABLE ocg_individual DROP CONSTRAINT ocg_individual_persona_id_fkey;
DROP INDEX IF EXISTS idx_ocg_individual_persona;
ALTER TABLE ocg_individual
    ALTER COLUMN persona_id TYPE VARCHAR(20) USING persona_id::text;
CREATE INDEX idx_ocg_individual_persona ON ocg_individual(persona_id);

-- =============================================================================
-- 2. Drop índices duplicados (ORM autogen + manual)
--    ocg_individual: 3 índices ix_ redundantes com os idx_ manuais
--    ocg: 6 índices ix_ redundantes (ix_ocg_questionnaire_id mantido — é UNIQUE)
-- =============================================================================

-- ocg_individual
DROP INDEX IF EXISTS ix_ocg_individual_project_id;
DROP INDEX IF EXISTS ix_ocg_individual_document_id;
DROP INDEX IF EXISTS ix_ocg_individual_persona_id;

-- ocg (ix_ocg_questionnaire_id é UNIQUE — mantido; dropa-se idx_ redundante não-único)
DROP INDEX IF EXISTS idx_ocg_questionnaire_id;
DROP INDEX IF EXISTS ix_ocg_project_id;
DROP INDEX IF EXISTS ix_ocg_status;
DROP INDEX IF EXISTS ix_ocg_is_blocking;
DROP INDEX IF EXISTS ix_ocg_overall_score;
DROP INDEX IF EXISTS ix_ocg_generated_at;
DROP INDEX IF EXISTS ix_ocg_created_at;

-- =============================================================================
-- 3. Integridade do version do OCG (CO-DB-02)
--    Garante NOT NULL e valor positivo (version=0 inválido por regra de negócio)
-- =============================================================================
UPDATE ocg SET version = 1 WHERE version IS NULL;
ALTER TABLE ocg ALTER COLUMN version SET NOT NULL;
ALTER TABLE ocg ALTER COLUMN version SET DEFAULT 1;
ALTER TABLE ocg ADD CONSTRAINT chk_ocg_version_positive CHECK (version > 0);

-- =============================================================================
-- 4. ON DELETE explícito em persona_follow_up_questions.answered_by (CO-DB-03)
--    Comportamento atual: RESTRICT (padrão PostgreSQL sem ON DELETE)
--    Comportamento novo: SET NULL (usuário deletado não bloqueia resposta)
-- =============================================================================
ALTER TABLE persona_follow_up_questions
    DROP CONSTRAINT persona_follow_up_questions_answered_by_fkey,
    ADD CONSTRAINT persona_follow_up_questions_answered_by_fkey
        FOREIGN KEY (answered_by) REFERENCES users(id) ON DELETE SET NULL;

-- =============================================================================
-- 5. Índice composto para gate de CodeGen (CR-DB-03 — index-only scan)
--    Usado pelo gate OCG na Fase 31.4 para lookup por project_id + version DESC
-- =============================================================================
CREATE INDEX idx_ocg_project_version ON ocg(project_id, version DESC);

COMMIT;
