-- 2026-04-26: MVP-K — regenerate-by-error.
-- Coluna `build_errors` em scaffold_run_items guarda erros que o owner
-- reportou ao endpoint /scaffold/runs/{id}/fix-build-errors. O scaffold
-- executor lê esse campo ao gerar o item e injeta no prompt como seção
-- "ERROS DE BUILD A CORRIGIR" pra LLM consertar consciente do problema
-- exato (tipos, imports, paths, etc).
--
-- TEXT NULL: vazio quando item está OK ou ainda não foi reportado.

BEGIN;

ALTER TABLE scaffold_run_items
    ADD COLUMN IF NOT EXISTS build_errors TEXT;

COMMIT;
