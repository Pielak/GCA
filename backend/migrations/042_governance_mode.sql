-- MVP governance_mode — separa core (gerador de código) de módulos opt-in (PM corporativo).
-- Quando solo_owner, o pipeline (Arguidor/M01/Backlog) suprime cobranças de governança
-- (cronograma absoluto, EAP, RACI, orçamento, KPIs corporativos, go/no-go formal).
-- Quando team/corporate, módulos de PM podem ser ativados (futuros — não implementados ainda).
-- Default solo_owner: respeita owner como decisor único e não baixa score por ausência
-- de artefatos corporativos.

ALTER TABLE projects
    ADD COLUMN governance_mode VARCHAR(20) NOT NULL DEFAULT 'solo_owner';

ALTER TABLE projects
    ADD CONSTRAINT projects_governance_mode_check
    CHECK (governance_mode IN ('solo_owner', 'team', 'corporate'));

CREATE INDEX ix_projects_governance_mode
    ON projects (governance_mode);

COMMENT ON COLUMN projects.governance_mode IS
    'Modo de governança do projeto. solo_owner (default): pipeline suprime gaps de PM corporativo. team: intermediário. corporate: pipeline aceita módulos opt-in de PM.';
