-- Migration 053: OCG Delta Tracking Fields for M01 + Personas validation
--
-- Adiciona campos para rastrear:
-- - source: origem da mudança (questionnaire_response, persona_validation, document_ingestion, etc)
-- - persona_id: qual persona validou (gp, arquiteto, dba, dev_sr, qa)
-- - decision: decisão da persona (approved, needs_clarification)
-- - hash_chain: hash para garantir integridade
--
-- Também adiciona função para garantir que OCG nunca contrai (só expande)

BEGIN;

-- Adicionar colunas de rastreamento à tabela ocg_delta_log
ALTER TABLE ocg_delta_log
ADD COLUMN source VARCHAR(50) DEFAULT 'document_ingestion',
ADD COLUMN persona_id VARCHAR(20),
ADD COLUMN decision VARCHAR(30),
ADD COLUMN hash_chain VARCHAR(64);

-- Criar índice para buscar rápido by source e persona
CREATE INDEX idx_ocg_delta_source ON ocg_delta_log(project_id, source);
CREATE INDEX idx_ocg_delta_persona ON ocg_delta_log(project_id, persona_id) WHERE persona_id IS NOT NULL;

-- Função PL/pgSQL para garantir que OCG nunca contrai
-- Validação: campos do novo OCG ⊇ campos do OCG anterior (expansão apenas)
CREATE OR REPLACE FUNCTION validate_ocg_expansion()
RETURNS TRIGGER AS $$
DECLARE
    old_ocg JSONB;
    new_ocg JSONB;
    old_score NUMERIC;
    new_score NUMERIC;
BEGIN
    -- Se não temos OCG anterior, sempre aceita (primeira mudança é expansão)
    IF OLD IS NULL THEN
        RETURN NEW;
    END IF;

    -- Parse OCG snapshots
    old_ocg := (OLD.ocg_snapshot)::JSONB;
    new_ocg := (NEW.ocg_snapshot)::JSONB;

    -- Se algum é NULL, aceita (não conseguimos validar)
    IF old_ocg IS NULL OR new_ocg IS NULL THEN
        RETURN NEW;
    END IF;

    -- Validação: score do novo ≥ score do antigo (nunca contrai)
    old_score := COALESCE((old_ocg -> 'overall_score')::NUMERIC, 0);
    new_score := COALESCE((new_ocg -> 'overall_score')::NUMERIC, 0);

    IF new_score < old_score THEN
        RAISE EXCEPTION
            'OCG contraction blocked: score went from % to % (only expansion allowed)',
            old_score, new_score;
    END IF;

    -- Contrato: se decision='rejected' ou decision='needs_clarification', não é uma agregação
    -- (retorna para clarificação, não é erro, apenas não agrega ainda)
    IF NEW.decision IN ('needs_clarification', 'rejected') THEN
        -- Aceita: é loop de clarificação, não contração
        RETURN NEW;
    END IF;

    -- Se decision='approved' e score diminuiu, bloqueia
    IF NEW.decision = 'approved' AND new_score < old_score THEN
        RAISE EXCEPTION
            'Approved delta must expand OCG: score went from % to % — approval invalid',
            old_score, new_score;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Disparador para validar expansão do OCG
DROP TRIGGER IF EXISTS ocg_expansion_check ON ocg_delta_log;
CREATE TRIGGER ocg_expansion_check
BEFORE UPDATE ON ocg_delta_log
FOR EACH ROW
EXECUTE FUNCTION validate_ocg_expansion();

-- Comentário nas colunas para documentação
COMMENT ON COLUMN ocg_delta_log.source IS 'Origem da mudança: questionnaire_response, persona_validation, document_ingestion, manual_edit';
COMMENT ON COLUMN ocg_delta_log.persona_id IS 'Persona que validou (gp, arquiteto, dba, dev_sr, qa) — NULL se não persona';
COMMENT ON COLUMN ocg_delta_log.decision IS 'Decisão: approved, needs_clarification, rejected';
COMMENT ON COLUMN ocg_delta_log.hash_chain IS 'SHA256 da sequência de deltas — para auditoria/integridade';

COMMIT;
