-- MVP 20 Fase 20.2 — Security Findings consumidos de scanners externos.
-- ============================================================================
-- GCA consome findings de Sonar/Snyk/gitleaks do cliente via adapter pattern.
-- Decisão binária #3 do MVP 20: scanners são CONSUMIDOS, não reimplementados.
-- GCA nunca gera finding próprio em V1.
--
-- P7 do OCG passa a consumir findings reais quando há scanner configurado.
-- Sem config, mantém heurística pré-20 (comportamento preservado).
--
-- Idempotência: UNIQUE (project_id, source_scanner, external_id) — re-sync
-- do mesmo finding do mesmo scanner atualiza a row, não duplica.

CREATE TABLE IF NOT EXISTS security_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Origem: qual scanner reportou.
    source_scanner VARCHAR(20) NOT NULL,
    external_id VARCHAR(200) NOT NULL,

    -- Localização do problema (quando aplicável).
    file_path TEXT NULL,
    line_start INTEGER NULL,
    line_end INTEGER NULL,

    -- Classificação canônica.
    severity VARCHAR(20) NOT NULL,
    cwe_id VARCHAR(20) NULL,
    rule_id VARCHAR(200) NULL,

    -- Descrição.
    title VARCHAR(500) NOT NULL,
    description TEXT NULL,
    url TEXT NULL,

    -- Ciclo de vida canônico:
    --   open              — finding ativo, conta pro score P7
    --   fixed             — scanner confirmou resolução em re-scan
    --   accepted_risk     — GP + Admin aceitaram formalmente (dupla assinatura)
    status VARCHAR(30) NOT NULL DEFAULT 'open',
    accepted_risk_justification TEXT NULL,
    accepted_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    accepted_at TIMESTAMPTZ NULL,
    admin_co_signed_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    admin_co_signed_at TIMESTAMPTZ NULL,

    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fixed_at TIMESTAMPTZ NULL
);

-- Idempotência de re-sync: mesmo finding do mesmo scanner = 1 linha.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_security_finding_scanner_external_id
    ON security_findings (project_id, source_scanner, external_id);

-- Queries comuns.
CREATE INDEX IF NOT EXISTS idx_security_findings_project_status
    ON security_findings (project_id, status);

CREATE INDEX IF NOT EXISTS idx_security_findings_project_severity
    ON security_findings (project_id, severity)
    WHERE status = 'open';

COMMENT ON COLUMN security_findings.source_scanner IS
    'Scanner canônico: sonar | snyk | gitleaks (V1). Novos adapters entram em MVPs futuros.';

COMMENT ON COLUMN security_findings.severity IS
    'Canônico aplicação-level: critical | high | medium | low | info. '
    'Normalização feita pelo adapter (Sonar BLOCKER → critical; Snyk critical → critical; etc).';

COMMENT ON COLUMN security_findings.status IS
    'Ciclo: open (conta pro P7) | fixed (scanner confirmou) | accepted_risk (dupla assinatura GP+Admin).';

COMMENT ON COLUMN security_findings.accepted_risk_justification IS
    'Obrigatório quando status=accepted_risk. GP explica por que o risco é aceito; '
    'Admin co-assina. Auditoria SHA-256 via GlobalAuditLog.';
