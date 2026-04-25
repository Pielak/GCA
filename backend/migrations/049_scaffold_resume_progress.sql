-- 2026-04-25: scaffold runs ganham last_progress_at pra watchdog detectar
-- zombies (runs em 'generating' que não avançam por > N min). Antes, o
-- counter completed_items só atualizava no FINAL do loop, e quando worker
-- restartava no meio, contadores ficavam desatualizados e impossível
-- distinguir progresso real de zombie real.

ALTER TABLE scaffold_runs
    ADD COLUMN last_progress_at TIMESTAMPTZ;

CREATE INDEX ix_scaffold_runs_zombie
    ON scaffold_runs (status, last_progress_at)
    WHERE status IN ('planning', 'generating');

COMMENT ON COLUMN scaffold_runs.last_progress_at IS
    'Timestamp do último item completado/falhado. Usado pelo watchdog: status in (planning, generating) + last_progress_at > 10min = zombie pra re-enfileirar.';

-- Backfill: runs que já têm completed_items > 0 ganham last_progress_at = started_at
-- (aproximação; vale como ponto de partida pro watchdog não acusá-las imediatamente).
UPDATE scaffold_runs SET last_progress_at = started_at
WHERE last_progress_at IS NULL AND status IN ('planning', 'generating', 'completed', 'applied');
