-- 012 — Notificações de usuário (in-app)
BEGIN;

CREATE TABLE IF NOT EXISTS user_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    event_type VARCHAR(80) NOT NULL,  -- invite_received, questionnaire_approved, ocg_updated, critical_error, etc.
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    resource_type VARCHAR(50),
    resource_id UUID,
    link VARCHAR(500),  -- URL interna para navegar ao clicar
    severity VARCHAR(20) NOT NULL DEFAULT 'info',  -- info | success | warning | error
    read_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_notif_user_unread ON user_notifications(user_id, read_at);
CREATE INDEX IF NOT EXISTS idx_user_notif_user_created ON user_notifications(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_notif_project ON user_notifications(project_id);

COMMIT;
