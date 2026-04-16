-- 017 — Solicitação de projeto: requisitos iniciais por tipo
--
-- Adiciona campos para o wizard de solicitação capturar:
--   - custom_deliverable_type: nome livre quando user escolhe "Outro" no combo
--     (ex: "Web Application", "Browser Extension"). Default NULL = usa
--     deliverable_type padrão.
--   - requirements_json: respostas das perguntas obrigatórias específicas
--     do tipo escolhido (ex: web_application pergunta sobre páginas, auth,
--     deploy). JSON aberto para evolução sem migration.
--
-- Estes dados alimentam o seed inicial do OCG após admin aprovar a
-- solicitação — viram "documento de requisitos zero" para o Arguidor
-- analisar.

BEGIN;

ALTER TABLE project_requests
    ADD COLUMN IF NOT EXISTS custom_deliverable_type VARCHAR(100),
    ADD COLUMN IF NOT EXISTS requirements_json TEXT;

COMMENT ON COLUMN project_requests.custom_deliverable_type IS
    'Nome livre do tipo quando user escolheu "Outro" no combo. NULL = usa deliverable_type.';
COMMENT ON COLUMN project_requests.requirements_json IS
    'JSON com respostas das perguntas obrigatórias do tipo (passo 2 do wizard). Alimenta seed do OCG.';

COMMIT;
