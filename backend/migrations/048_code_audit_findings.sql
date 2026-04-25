-- Arguidor #2 (2026-04-25): auditor ativo pós-CodeGen.
-- Após /scaffold/runs/{id}/apply commitar arquivos no Git, o auditor roda
-- 1 LLM call por arquivo de código verificando aderência ao OCG, RNFs,
-- stack canônica, docstrings PT-BR, e práticas de segurança. Cada
-- divergência vira um finding aqui — owner decide dismiss ou accept.
-- accept gera BacklogItem tipo "fix" pra próximo CodeGen tratar.

CREATE TABLE code_audit_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    run_id UUID NOT NULL REFERENCES scaffold_runs(id) ON DELETE CASCADE,
    run_item_id UUID REFERENCES scaffold_run_items(id) ON DELETE SET NULL,
    file_path VARCHAR(500) NOT NULL,
    severity VARCHAR(10) NOT NULL,
    -- info: nota informacional, sem ação obrigatória
    -- warn: divergência relevante, recomenda correção
    -- critical: bloqueador (RNF violado, security issue grave, stack divergente)
    category VARCHAR(20) NOT NULL,
    -- rnf: viola contrato RNF do OCG
    -- stack: usa lib/feature fora da stack declarada
    -- security: padrão OWASP relevante (injection, auth, secrets em código)
    -- ptbr: docstring/comentário/erro user-facing em EN onde devia PT-BR
    -- scope: arquivo não cumpre o purpose declarado no plano
    -- doc: docstring ausente/incompleta
    finding TEXT NOT NULL,
    suggested_fix TEXT,
    owner_action VARCHAR(20),
    -- null: aguarda decisão do owner
    -- dismissed: owner descartou (justificativa em owner_note)
    -- accepted: owner concordou (sem ação automática)
    -- fix_created: owner aceitou e gerou BacklogItem fix
    owner_note TEXT,
    owner_acted_by UUID REFERENCES users(id) ON DELETE SET NULL,
    owner_acted_at TIMESTAMPTZ,
    backlog_fix_item_id UUID REFERENCES backlog_items(id) ON DELETE SET NULL,
    tokens_used INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT code_audit_findings_severity_check
        CHECK (severity IN ('info', 'warn', 'critical')),
    CONSTRAINT code_audit_findings_category_check
        CHECK (category IN ('rnf', 'stack', 'security', 'ptbr', 'scope', 'doc')),
    CONSTRAINT code_audit_findings_action_check
        CHECK (owner_action IN ('dismissed', 'accepted', 'fix_created'))
);

CREATE INDEX ix_code_audit_findings_project_severity
    ON code_audit_findings (project_id, severity);
CREATE INDEX ix_code_audit_findings_run
    ON code_audit_findings (run_id, created_at DESC);
CREATE INDEX ix_code_audit_findings_pending
    ON code_audit_findings (project_id, owner_action)
    WHERE owner_action IS NULL;

COMMENT ON TABLE code_audit_findings IS
    'Auditoria ativa pós-CodeGen (Arguidor #2). 1 finding por divergência de arquivo gerado vs OCG/RNFs/stack/PT-BR/security.';
