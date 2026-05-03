-- Migration 066: Add display_order column for drag-and-drop reordering in Backlog

BEGIN;

ALTER TABLE backlog_items ADD COLUMN display_order INTEGER NOT NULL DEFAULT 0;

-- Index para ordenação eficiente
CREATE INDEX idx_backlog_display_order ON backlog_items(project_id, display_order);

COMMIT;
