-- Migration 009: OCG reativo + billing
CREATE TABLE IF NOT EXISTS ai_usage_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    provider VARCHAR(30) NOT NULL,
    model VARCHAR(50) NOT NULL,
    operation VARCHAR(50) NOT NULL,
    tokens_input INTEGER NOT NULL DEFAULT 0,
    tokens_output INTEGER NOT NULL DEFAULT 0,
    cost_usd DECIMAL(10,6) NOT NULL DEFAULT 0,
    actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
    metadata TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_project ON ai_usage_log(project_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_operation ON ai_usage_log(project_id, operation);
CREATE INDEX IF NOT EXISTS idx_ai_usage_created ON ai_usage_log(created_at);

ALTER TABLE ocg ADD COLUMN IF NOT EXISTS context_health TEXT DEFAULT '{}';
ALTER TABLE ocg ADD COLUMN IF NOT EXISTS change_type VARCHAR(20) DEFAULT 'INITIAL';
