-- 069_mvp35_questionnaire_validation.sql
-- MVP 35 Fase 35.2 — Validação canônica do Questionário Técnico
--
-- Mudanças:
--   1. UPDATE preventivo: legacy 'ocg_generated' e 'validated' (semântica
--      antiga = pós-personas) → 'submitted'. ANTES dos CHECKs serem
--      instalados — caso contrário, dados legados violariam constraints.
--   2. CHECK chk_tq_status: enum canônico draft|validated|submitted|archived
--   3. CHECK chk_tq_submitted_at: submitted_at NOT NULL quando status
--      submitted ou archived
--   4. CHECK chk_tq_validated_at: validated_at NOT NULL quando
--      status='validated' (semântica nova MVP 35 = pré-submit)
--
-- Idempotência: DROP CONSTRAINT IF EXISTS antes de cada ADD. Padrão
-- canônico das migrations 066/067/068.
--
-- Sequência de deploy canônica (DBA-M4):
--   1. Código corrigido sem 'ocg_generated' (questionnaire_service.py:717
--      e webhooks.py:259 escrevem em Questionnaire LEGACY, NÃO
--      TechnicalQuestionnaire — verificado falso alarme do gate).
--   2. Esta migration aplicada.
--   3. Frontend redeployed.

BEGIN;

-- 1. UPDATE preventivo de valores legacy ANTES de instalar CHECK.
--    'ocg_generated' (legacy MVP 9) e 'validated' (semântica antiga,
--    pós-personas) ambos viram 'submitted' (estado terminal canônico).
UPDATE technical_questionnaires
   SET status = 'submitted'
 WHERE status IN ('ocg_generated', 'validated');

-- 2. CHECK enum status canônico (DBA-M2)
ALTER TABLE technical_questionnaires
    DROP CONSTRAINT IF EXISTS chk_tq_status;
ALTER TABLE technical_questionnaires
    ADD CONSTRAINT chk_tq_status
    CHECK (status IN ('draft', 'validated', 'submitted', 'archived'));

-- 3. CHECK submitted_at obrigatório quando status terminal
--    (submitted ou archived). archived herda submitted_at do estado
--    submitted anterior — nunca é estado inicial.
ALTER TABLE technical_questionnaires
    DROP CONSTRAINT IF EXISTS chk_tq_submitted_at;
ALTER TABLE technical_questionnaires
    ADD CONSTRAINT chk_tq_submitted_at
    CHECK (
        status NOT IN ('submitted', 'archived')
        OR submitted_at IS NOT NULL
    );

-- 4. CHECK validated_at obrigatório quando status='validated'
--    (semântica MVP 35 = pré-submit). Router de validate-field DEVE
--    populá-lo na transição (DBA-M3).
ALTER TABLE technical_questionnaires
    DROP CONSTRAINT IF EXISTS chk_tq_validated_at;
ALTER TABLE technical_questionnaires
    ADD CONSTRAINT chk_tq_validated_at
    CHECK (
        status != 'validated'
        OR validated_at IS NOT NULL
    );

-- 5. Comentário canônico atualizado (DBA-S2)
COMMENT ON COLUMN technical_questionnaires.status IS
    'Estado canônico do questionário (MVP 35): draft (rascunho/auto-save) | validated (passou Validar Escopo, pré-submit) | submitted (terminal, dispara personas) | archived (deletado via Ingestão, força novo questionário). CHECK chk_tq_status.';

COMMIT;
