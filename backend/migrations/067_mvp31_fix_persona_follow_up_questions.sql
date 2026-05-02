-- 067_mvp31_fix_persona_follow_up_questions.sql
-- MVP 31 Fase 31.1 — fix omissão da migration 066
-- Aplica mesma correção feita em ocg_individual.persona_id, agora em
-- persona_follow_up_questions.persona_id (gap detectado pelo Gate 5/QA).
--
-- Problema: persona_id era uuid FK para users.id — errado.
--           Deve armazenar tag canônica da persona LLM ("AUD", "GP", etc.).
-- Solução:  Drop FK + índice antigo, alterar tipo para VARCHAR(20), recriar índice.

BEGIN;

-- 1. Drop FK uuid → users e índices associados
ALTER TABLE persona_follow_up_questions
    DROP CONSTRAINT IF EXISTS persona_follow_up_questions_persona_id_fkey;

DROP INDEX IF EXISTS idx_follow_up_persona;
DROP INDEX IF EXISTS idx_persona_follow_up_questions_persona;
DROP INDEX IF EXISTS ix_persona_follow_up_questions_persona_id;

-- 2. Alterar tipo: uuid → VARCHAR(20) com tag canônica
ALTER TABLE persona_follow_up_questions
    ALTER COLUMN persona_id TYPE VARCHAR(20) USING persona_id::text;

-- 3. Recriar índice (não-único, busca por persona)
CREATE INDEX IF NOT EXISTS idx_persona_follow_up_questions_persona
    ON persona_follow_up_questions(persona_id);

COMMIT;
