-- MVP 6 — Validação assistida em campo (tickets de incidente)
-- Contrato §7 MVP 6. Roteamento por papel:
--   Dev/Tester/QA abre → target_scope='gp'    (GPs do projeto recebem)
--   GP abre           → target_scope='admin'  (Admins da instância recebem)
--   Admin abre        → target_scope='admin'  (demais Admins recebem)

BEGIN;

CREATE TABLE IF NOT EXISTS incident_tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    author_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    target_scope VARCHAR(10) NOT NULL CHECK (target_scope IN ('gp', 'admin')),
    category VARCHAR(40) NOT NULL CHECK (category IN ('bug', 'duvida', 'pedido_feature', 'incidente_pipeline')),
    priority VARCHAR(10) NOT NULL CHECK (priority IN ('baixa', 'media', 'alta', 'critica')),
    status VARCHAR(20) NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    resolved_by UUID REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT chk_resolved_coherent CHECK (
        (status IN ('resolved', 'closed') AND resolved_at IS NOT NULL)
        OR (status IN ('open', 'in_progress') AND resolved_at IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_incident_tickets_project_created
    ON incident_tickets (project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_incident_tickets_target_status
    ON incident_tickets (target_scope, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_incident_tickets_author
    ON incident_tickets (author_id, created_at DESC);

CREATE TABLE IF NOT EXISTS incident_ticket_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id UUID NOT NULL REFERENCES incident_tickets(id) ON DELETE CASCADE,
    author_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_incident_comments_ticket
    ON incident_ticket_comments (ticket_id, created_at ASC);

COMMIT;
