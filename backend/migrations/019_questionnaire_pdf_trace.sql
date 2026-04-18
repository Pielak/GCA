-- DT-020: trace do PDF submetido via aba Questionário.
-- Antes o GP via "Status: Incompleto 80%" sem saber que arquivo chegou ao
-- backend — causou confusão ("onde foi parar meu PDF?"). Agora a aba
-- Questionário mostra filename + hash + tamanho + contagem de respostas.
--
-- Todas as colunas são nullable: retrocompat com os 2 questionários existentes
-- (já aprovados/gerados) que não passaram pelo novo código.

BEGIN;

ALTER TABLE questionnaires
    ADD COLUMN IF NOT EXISTS uploaded_filename VARCHAR(500),
    ADD COLUMN IF NOT EXISTS file_hash VARCHAR(64),
    ADD COLUMN IF NOT EXISTS file_size_bytes INTEGER,
    ADD COLUMN IF NOT EXISTS answered_questions INTEGER;

COMMIT;
