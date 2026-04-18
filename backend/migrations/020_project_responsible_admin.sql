-- DT-038: compartimentalização de notificações (contrato §2.2).
-- Projetos ganham `responsible_admin_id` — o admin que aprovou a
-- criação e passa a ser o único destinatário de notificações
-- relacionadas ao projeto (questionário submetido, OCG gerado etc).
--
-- Nullable: retrocompat com 3 projetos reais existentes (FinanceHub Pro,
-- Automação Jurídica Assistida, e qualquer novo). Backfill abaixo só é
-- seguro porque a instância atual tem 1 admin único.
--
-- ON DELETE SET NULL: se o admin responsável for removido (caso raro,
-- instância em transição), notificação cai no fallback "todos admins
-- ativos" com warning log — nenhum projeto fica órfão.

BEGIN;

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS responsible_admin_id UUID REFERENCES users(id) ON DELETE SET NULL;

-- Backfill: na instância atual há um único admin real. Qualquer projeto
-- pré-existente fica sob responsabilidade dele. Novos projetos vão
-- receber o admin que aprovou a criação (admin_service.py).
UPDATE projects
SET responsible_admin_id = (
    SELECT id FROM users
    WHERE is_admin = true AND is_active = true
    ORDER BY created_at ASC
    LIMIT 1
)
WHERE responsible_admin_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_projects_responsible_admin ON projects(responsible_admin_id);

COMMIT;
