-- MVP 6 Emenda 2026-04-19 — Sustentação + anexos + contexto obrigatório

BEGIN;

-- (1) Flag Sustentação cross-instância. Admin herda (checado em código,
-- não no schema). Default false.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_support BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_users_is_support
    ON users (is_support) WHERE is_support = TRUE;

-- (2) Contexto obrigatório do incidente. Em tickets já existentes fica
-- NULL; constraint NOT NULL só aplicada pra novas linhas via validação
-- no service (retrocompat).
ALTER TABLE incident_tickets
    ADD COLUMN IF NOT EXISTS section_reference VARCHAR(300),
    ADD COLUMN IF NOT EXISTS flow_description TEXT;

-- (3) Anexos. Até 5 por ticket (enforcement no service pra não violar
-- uploads parciais); 10 MB cada (checado no router ao receber bytes).
CREATE TABLE IF NOT EXISTS incident_ticket_attachments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id UUID NOT NULL REFERENCES incident_tickets(id) ON DELETE CASCADE,
    uploader_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    filename VARCHAR(255) NOT NULL,
    mime VARCHAR(120) NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
    sha256 VARCHAR(64) NOT NULL,
    storage_path VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_incident_attachments_ticket
    ON incident_ticket_attachments (ticket_id, created_at ASC);

COMMIT;
