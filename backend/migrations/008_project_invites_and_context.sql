-- Migration 008: Tabelas project_invites e user_project_context (spec seção 11)
-- Data: 2026-04-09

-- 1. Tabela de convites por projeto
CREATE TABLE IF NOT EXISTS project_invites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) NOT NULL,
    invited_by_user_id UUID NOT NULL REFERENCES users(id),
    invite_token VARCHAR(255) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    accepted_at TIMESTAMP WITH TIME ZONE,
    accepted_by_user_id UUID REFERENCES users(id),
    revoked_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_project_invites_project ON project_invites(project_id);
CREATE INDEX IF NOT EXISTS idx_project_invites_email ON project_invites(email);
CREATE INDEX IF NOT EXISTS idx_project_invites_token ON project_invites(invite_token);
CREATE INDEX IF NOT EXISTS idx_project_invites_status ON project_invites(status);

-- 2. Contexto ativo do usuário (um projeto por vez)
CREATE TABLE IF NOT EXISTS user_project_context (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    active_project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    last_selected_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_project_context_user ON user_project_context(user_id);
