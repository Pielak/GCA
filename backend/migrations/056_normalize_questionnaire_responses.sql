-- Migration 056: Normalize Technical Questionnaire Response Keys
--
-- Converte chaves JSONB de formato numérico ("1", "2", "3")
-- para formato canônico com prefixo ("Q1", "Q2", "Q3").
--
-- Motivo: PDF extrator retornava chaves numéricas, mas TechnicalQuestionnaireForm
-- esperava chaves com prefixo "Q". Essa migração unifica o armazenamento.

BEGIN;

-- Função auxiliar para normalizar chaves JSONB
CREATE OR REPLACE FUNCTION normalize_questionnaire_responses()
RETURNS void AS $$
DECLARE
    v_record RECORD;
    v_old_responses JSONB;
    v_new_responses JSONB;
    v_key TEXT;
    v_q_key TEXT;
BEGIN
    FOR v_record IN SELECT id, responses FROM technical_questionnaires WHERE responses IS NOT NULL AND responses != '{}'::JSONB LOOP
        v_old_responses := v_record.responses;
        v_new_responses := '{}'::JSONB;

        -- Itera sobre cada chave do JSONB
        FOR v_key IN SELECT jsonb_object_keys(v_old_responses) LOOP
            -- Se a chave é numérica (p.ex., "1", "42"), converte para "Q1", "Q42"
            IF v_key ~ '^[0-9]+$' THEN
                v_q_key := 'Q' || v_key;
            ELSE
                -- Se já tem prefixo, mantém como está
                v_q_key := v_key;
            END IF;

            -- Copia o valor para a nova chave
            v_new_responses := v_new_responses || jsonb_build_object(v_q_key, v_old_responses->v_key);
        END LOOP;

        -- Atualiza a linha se houve mudança
        IF v_new_responses != v_old_responses THEN
            UPDATE technical_questionnaires
            SET responses = v_new_responses, updated_at = CURRENT_TIMESTAMP
            WHERE id = v_record.id;
        END IF;
    END LOOP;

    RAISE NOTICE 'Normalização de respostas de questionários concluída';
END;
$$ LANGUAGE plpgsql;

-- Executa a normalização
SELECT normalize_questionnaire_responses();

-- Remove função auxiliar
DROP FUNCTION normalize_questionnaire_responses();

COMMIT;
