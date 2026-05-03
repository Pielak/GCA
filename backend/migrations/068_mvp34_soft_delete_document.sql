-- 068_mvp34_soft_delete_document.sql
-- MVP 34 Fase 34.1 — soft-delete em ingested_documents + reversao de propagacao OCG
--
-- Contexto: regra canonica §2.4 do CLAUDE.md ("OCG nao contrai") cobre
-- ingestao ruim mas nao cobre delecao legitima da fonte. MVP 34 introduz
-- soft-delete e abre caminho canonico de limpeza (smoke fixtures, erro
-- humano, LGPD), mantendo auditoria intacta.
--
-- Mudancas:
--   1. ocg.change_type: VARCHAR(20) -> VARCHAR(30) (DBA-M4 ANTES das colunas
--      novas para suportar valor 'REVERT_DOCUMENT_DELETE' = 23 chars)
--   2. ingested_documents: 4 colunas novas (deleted_at, deleted_by,
--      deleted_reason, revert_metadata) + CHECK constraints + indice parcial
--
-- Idempotencia: ALTER ... IF NOT EXISTS / DROP CONSTRAINT IF EXISTS / etc.
-- Padrao confirmado nas migrations 066/067.
--
-- ============================================================================
-- DT-086: purge fisico de deleted_reason='lgpd' NAO implementado nesta
--         migration. Campos pii_fields, ocg_individual.parecer (JSONB com
--         trechos do doc) e ocg_global.parecer_consolidated (JSONB derivado)
--         de docs lgpd-deletados PERMANECEM no banco apos soft-delete.
--         Compliance LGPD Art. 17 (esquecimento completo) fica parcial.
--         Endereçar em MVP futuro de "scheduled purge" — job que apos N dias
--         da soft-delecao LGPD remove fisicamente as rows + JSONBs.
-- ============================================================================
-- DT-087: ingested_documents.uploaded_by sem ON DELETE declarado. Com
--         soft-delete (row vivendo indefinidamente), RESTRICT implicito
--         cresce como risco operacional. Migration posterior declara
--         ON DELETE SET NULL.
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. AMPLIAR ocg.change_type DE VARCHAR(20) PARA VARCHAR(30) (DBA-M4)
--    Valor novo 'REVERT_DOCUMENT_DELETE' tem 23 caracteres.
--    Ordem importa: rolling deploy nao pode falhar entre passos. Esta
--    alteracao roda PRIMEIRO para que o Celery worker possa criar OCG
--    com o novo change_type imediatamente apos a migration.
--    PostgreSQL 16: ALTER TYPE para VARCHAR mais largo NAO reescreve a tabela.
-- ============================================================================

ALTER TABLE ocg
    ALTER COLUMN change_type TYPE VARCHAR(30);

-- ============================================================================
-- 2. SOFT-DELETE EM ingested_documents (DBA-M3 idempotencia)
-- ============================================================================

-- 2.1. deleted_at: timestamp da soft-delecao. NULL = doc ativo.
ALTER TABLE ingested_documents
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL;

-- 2.2. deleted_by: usuario que executou a delecao (audit). NULL se sistema.
--      NAO declara FK para users — DT-087 aborda em migration posterior.
ALTER TABLE ingested_documents
    ADD COLUMN IF NOT EXISTS deleted_by UUID NULL;

-- 2.3. deleted_reason: motivo canonico da delecao.
--      'manual' = GP apagou via UI/API
--      'lgpd' = solicitacao de esquecimento (Art. 17 LGPD)
--      'smoke_cleanup' = limpeza de fixture de teste/dogfood
ALTER TABLE ingested_documents
    ADD COLUMN IF NOT EXISTS deleted_reason VARCHAR(50) NULL;

-- CHECK constraint canonica: rejeita valores fora do enum (DBA-M2/S4 do MVP 34)
ALTER TABLE ingested_documents
    DROP CONSTRAINT IF EXISTS chk_ingested_doc_deleted_reason;
ALTER TABLE ingested_documents
    ADD CONSTRAINT chk_ingested_doc_deleted_reason
    CHECK (
        deleted_reason IS NULL
        OR deleted_reason IN ('manual', 'lgpd', 'smoke_cleanup')
    );

-- 2.4. revert_metadata: payload do Celery job de revert.
--      Estrutura minima exigida quando NOT NULL:
--        { "score_before": float, "score_after": float, ... }
--      Campos opcionais comuns:
--        maturity_warning, delta_fields_reverted[], persona_scores_diff
ALTER TABLE ingested_documents
    ADD COLUMN IF NOT EXISTS revert_metadata JSONB NULL;

-- CHECK schema minimo (DBA-S5): garante que job nao escreve JSONB parcial
ALTER TABLE ingested_documents
    DROP CONSTRAINT IF EXISTS chk_ingested_doc_revert_metadata_schema;
ALTER TABLE ingested_documents
    ADD CONSTRAINT chk_ingested_doc_revert_metadata_schema
    CHECK (
        revert_metadata IS NULL
        OR (
            revert_metadata ? 'score_before'
            AND revert_metadata ? 'score_after'
        )
    );

-- ============================================================================
-- 3. INDICE PARCIAL PARA LISTAGEM DE DOCS ATIVOS (DBA-S1)
--    Evita inclusao de docs deletados no plano de execucao independente
--    de estatisticas. Custo minimo (~5KB por 100 docs ativos), beneficio
--    cresce conforme rows soft-deleted acumulam.
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_ingested_docs_active
    ON ingested_documents(project_id, arguider_status)
    WHERE deleted_at IS NULL;

-- ============================================================================
-- 4. COMENTARIOS DE TABELA / COLUNA (operacional)
-- ============================================================================

COMMENT ON COLUMN ingested_documents.deleted_at IS
    'Timestamp da soft-delecao. NULL = doc ativo. Setado pelo endpoint DELETE.';
COMMENT ON COLUMN ingested_documents.deleted_by IS
    'UUID do usuario que executou a delecao (audit). NULL se executado pelo sistema.';
COMMENT ON COLUMN ingested_documents.deleted_reason IS
    'Motivo canonico: manual | lgpd | smoke_cleanup. Constraint chk_ingested_doc_deleted_reason.';
COMMENT ON COLUMN ingested_documents.revert_metadata IS
    'Payload JSONB do Celery job de revert. Estrutura minima: score_before, score_after.';

COMMIT;
