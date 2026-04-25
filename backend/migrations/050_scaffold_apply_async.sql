-- 2026-04-25: scaffold_runs ganha status 'applying' pra fluxo de apply
-- assíncrono via Celery. Antes, apply era síncrono no handler HTTP e
-- estourava timeout do Cloudflare (~100s) com 164 commits do AJA. Agora
-- o handler enfileira `scaffold_apply_executor` e retorna 202 imediato;
-- contadores apply_committed/apply_failed atualizam incrementalmente
-- conforme cada commit termina (heartbeat last_progress_at compatível
-- com watchdog_scaffold_zombies que detecta runs travadas em 'applying').
--
-- Idempotente: se 'applying' já estiver no CHECK (re-run da migration),
-- DROP+ADD reconstrói com o conjunto canônico atual.

BEGIN;

ALTER TABLE scaffold_runs DROP CONSTRAINT IF EXISTS scaffold_runs_status_check;

ALTER TABLE scaffold_runs ADD CONSTRAINT scaffold_runs_status_check
    CHECK (status IN ('pending', 'planning', 'generating', 'completed', 'failed', 'applied', 'applying'));

COMMIT;
