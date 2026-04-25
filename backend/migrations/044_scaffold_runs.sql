-- Cascata canônica Scaffold server-side persistido (2026-04-25).
-- Antes desta migration, a orquestração do scaffold MVP 30 ficava no
-- FRONTEND: o navegador chamava /scaffold/plan, recebia a lista de
-- arquivos, e iterava /scaffold/item síncrono pra cada um. Qualquer
-- desconexão de rede ou refresh de aba descartava todo o progresso.
--
-- Agora há um Celery task server-side que persiste o plano + items + content
-- gerado por arquivo em duas tabelas. Frontend vira observador (poll de
-- status). Falha de 1 item não invalida os demais. Apply ao Git commita
-- só os items com status=done. Topologia de dependências e enlaces de
-- conteúdo entre peers virão nas etapas B e C.

CREATE TABLE scaffold_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    triggered_by UUID REFERENCES users(id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending: criada, aguardando worker
    -- planning: rodando build_plan_prompt
    -- generating: iterando items
    -- completed: todos items terminaram (com sucesso ou falha individual)
    -- failed: erro na fase plan (não chegou nem a criar items)
    -- applied: items done foram commitados no Git
    plan_summary TEXT,
    plan_tokens_used INTEGER,
    total_items INTEGER NOT NULL DEFAULT 0,
    completed_items INTEGER NOT NULL DEFAULT 0,
    failed_items INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    applied_at TIMESTAMPTZ,
    apply_committed INTEGER,
    apply_failed INTEGER,
    CONSTRAINT scaffold_runs_status_check CHECK (
        status IN ('pending', 'planning', 'generating', 'completed', 'failed', 'applied')
    )
);

CREATE INDEX ix_scaffold_runs_project_started
    ON scaffold_runs (project_id, started_at DESC);
CREATE INDEX ix_scaffold_runs_status
    ON scaffold_runs (status)
    WHERE status IN ('pending', 'planning', 'generating');

CREATE TABLE scaffold_run_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES scaffold_runs(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    path VARCHAR(500) NOT NULL,
    file_type VARCHAR(40),
    purpose VARCHAR(500),
    est_lines INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending: aguarda worker chegar
    -- generating: LLM rodando agora
    -- done: content gerado com sucesso
    -- failed: LLM ou parse quebrou
    -- skipped: usuário rejeitou no apply (futuro)
    content TEXT,
    error TEXT,
    tokens_used INTEGER,
    notes TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    UNIQUE (run_id, ordinal),
    UNIQUE (run_id, path),
    CONSTRAINT scaffold_run_items_status_check CHECK (
        status IN ('pending', 'generating', 'done', 'failed', 'skipped')
    )
);

CREATE INDEX ix_scaffold_run_items_run_ordinal
    ON scaffold_run_items (run_id, ordinal);
CREATE INDEX ix_scaffold_run_items_run_status
    ON scaffold_run_items (run_id, status);

COMMENT ON TABLE scaffold_runs IS
    'Run de scaffold server-side (Celery). Sobrevive a desconexão do frontend; frontend é só observador via GET /scaffold/runs/{id}.';
COMMENT ON TABLE scaffold_run_items IS
    'Cada arquivo do plano vira uma row aqui; content é preenchido pelo Celery task ao gerar.';
