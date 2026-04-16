-- 013 — Soft-delete de docs sem bytes recuperáveis
-- Problema: docs ingeridos antes da feature de persistência (Sessão 20) não
-- têm bytes em disco. O endpoint /content retorna 404 e a UI tenta abrir um
-- arquivo que nunca vai existir.
--
-- Solução: nova coluna content_status para distinguir bytes disponíveis
-- (ou recuperáveis) de bytes definitivamente perdidos. O script
-- backend/scripts/inventory_lost_ingested.py popula esta coluna varrendo
-- IngestedDocument vs filesystem vs RepoAnalysisResult.

BEGIN;

ALTER TABLE ingested_documents
    ADD COLUMN IF NOT EXISTS content_status VARCHAR(20) NOT NULL DEFAULT 'available';

COMMENT ON COLUMN ingested_documents.content_status IS
    'available: bytes em disco ou recuperáveis via backfill; lost: bytes perdidos permanentemente — endpoint /content retorna 410 Gone';

COMMIT;
