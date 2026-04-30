-- Migration 065: Create PilaresVivosJob table for async regeneration
-- Tracks background jobs para regeneração de Pilares Vivos

BEGIN;

CREATE TABLE pilares_vivos_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'queued', -- queued, processing, completed, failed

    -- Resultado da regeneração
    resultado_json JSONB,

    -- Metadados de execução
    iniciado_em TIMESTAMP WITH TIME ZONE,
    concluido_em TIMESTAMP WITH TIME ZONE,
    tempo_total_segundos NUMERIC(8, 2),

    -- Rastreamento
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    criado_por UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Celery task tracking
    celery_task_id VARCHAR(255),
    erro_mensagem TEXT
);

-- Índices
CREATE INDEX idx_pilares_vivos_jobs_project ON pilares_vivos_jobs(project_id);
CREATE INDEX idx_pilares_vivos_jobs_status ON pilares_vivos_jobs(status);
CREATE INDEX idx_pilares_vivos_jobs_created ON pilares_vivos_jobs(criado_em DESC);

COMMIT;
