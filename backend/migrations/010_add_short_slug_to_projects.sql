-- Migration 010: Adiciona short_slug à tabela projects
-- short_slug é um slug curto (max 15 chars) para URLs amigáveis como /p/financehub-pro

ALTER TABLE projects ADD COLUMN IF NOT EXISTS short_slug VARCHAR(15) UNIQUE;
CREATE INDEX IF NOT EXISTS idx_projects_short_slug ON projects(short_slug);

-- Backfill: copia slug existente truncado em 15 chars como short_slug
UPDATE projects
SET short_slug = LEFT(slug, 15)
WHERE short_slug IS NULL;
