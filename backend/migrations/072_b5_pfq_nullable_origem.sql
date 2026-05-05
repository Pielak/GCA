-- Migration 072 — B5 (Roadmap clarification, Decisão GP 3)
-- Permite PersonaFollowUpQuestion com document_id/ocg_individual_id NULL
-- pra origem 'roadmap_clarification' (item do roadmap sem módulo concreto).
--
-- ANTES: ambos NOT NULL → INSERT só com pipeline n8n produzindo PFQ vinculada
-- a ingested_document + ocg_individual. Bloqueia uso novo (UX construtivo).
--
-- DEPOIS: ambos NULL OK. PFQs vindas de pipeline continuam preenchendo
-- (não muda comportamento). PFQs vindas de roadmap clarification deixam
-- NULL e usam `context` pra rastrear (módulo+motivo).
--
-- Não há perda de integridade: ON DELETE CASCADE em ambas FKs continua
-- válido — quando doc/individual existir, deleta junto. NULL não casca
-- (é o comportamento desejado pra origens externas ao pipeline).

BEGIN;

ALTER TABLE persona_follow_up_questions
  ALTER COLUMN document_id DROP NOT NULL;

ALTER TABLE persona_follow_up_questions
  ALTER COLUMN ocg_individual_id DROP NOT NULL;

COMMIT;
