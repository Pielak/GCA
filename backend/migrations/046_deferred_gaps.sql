-- Reforma do Arguidor #1 (2026-04-25): aging de gaps em solo_owner.
-- Quando um gap aparece em N+ ingestões consecutivas sem o owner ter agido
-- (sem virar applied_default, sem ter resposta no M01, sem ser ignorado
-- ativamente), ele vira owner-deferred — sai do cálculo de score e não
-- volta a punir até o owner ressuscitar manualmente.
--
-- gap_signature é hash determinístico do (pilar + texto normalizado) pra
-- agrupar gaps idênticos cruzando ingestões. Score 5+ ocorrências =
-- defer automático em solo_owner.

CREATE TABLE deferred_gaps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    gap_signature VARCHAR(64) NOT NULL,
    pillar VARCHAR(40),
    sample_text TEXT,
    sightings_count INTEGER NOT NULL DEFAULT 1,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deferred_at TIMESTAMPTZ,
    revived_at TIMESTAMPTZ,
    revived_by UUID REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE (project_id, gap_signature)
);

CREATE INDEX ix_deferred_gaps_project_active
    ON deferred_gaps (project_id)
    WHERE deferred_at IS NOT NULL AND revived_at IS NULL;

COMMENT ON TABLE deferred_gaps IS
    'Aging de gaps recorrentes em solo_owner. Após 5 ocorrências sem ação, vira owner-deferred e sai do impacto no score.';
COMMENT ON COLUMN deferred_gaps.gap_signature IS
    'sha256(pilar + texto normalizado) — agrupa gaps idênticos entre ingestões.';
