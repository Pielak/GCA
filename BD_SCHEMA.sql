-- ============================================================================
-- GCA — Database Schema
-- Multi-tenant com isolamento completo por projeto
-- ============================================================================

-- ============================================================================
-- PARTE 1: SCHEMA GLOBAL (public)
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS public;

-- ========== Users (Global) ==========
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,
    CONSTRAINT email_format CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$')
);

CREATE INDEX idx_users_email ON public.users(email);
CREATE INDEX idx_users_is_active ON public.users(is_active);

-- ========== Organizations (Global) ==========
CREATE TABLE IF NOT EXISTS public.organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) UNIQUE NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    owner_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_organizations_slug ON public.organizations(slug);
CREATE INDEX idx_organizations_owner_id ON public.organizations(owner_id);

-- ========== Organization Members ==========
CREATE TABLE IF NOT EXISTS public.organization_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL, -- admin, member, viewer
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(organization_id, user_id)
);

CREATE INDEX idx_org_members_org_id ON public.organization_members(organization_id);
CREATE INDEX idx_org_members_user_id ON public.organization_members(user_id);

-- ========== Projects (Global Metadata) ==========
CREATE TABLE IF NOT EXISTS public.projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL, -- usado para criar schema proj_{slug}_*
    description TEXT,

    -- Gate bloqueante: tipo de entregável (obrigatório na criação)
    deliverable_type VARCHAR(50) NOT NULL DEFAULT 'new_system',
    -- Valores: new_system, mobile_app, module, enhancement, integration, modernization, etl, maintenance

    -- Estados do projeto
    status VARCHAR(50) DEFAULT 'initializing', -- initializing, wizard_step_1, wizard_step_2, wizard_step_3, wizard_step_4, active, archived

    -- Wizard progress
    wizard_completed_at TIMESTAMPTZ,

    -- Provisioning
    provisioning_status VARCHAR(50) DEFAULT 'pending', -- pending, in_progress, completed, failed
    provisioning_error TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(organization_id, slug),
    CONSTRAINT slug_format CHECK (slug ~ '^[a-z0-9_-]+$')
);

CREATE INDEX idx_projects_org_id ON public.projects(organization_id);
CREATE INDEX idx_projects_slug ON public.projects(slug);
CREATE INDEX idx_projects_status ON public.projects(status);

-- ========== Project Members & Roles ==========
CREATE TABLE IF NOT EXISTS public.project_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL, -- gp (gerente projeto), tech_lead, dev, qa, compliance, viewer
    invited_by UUID REFERENCES public.users(id) ON DELETE SET NULL,
    invite_token VARCHAR(255) UNIQUE,
    invite_expires_at TIMESTAMPTZ,
    invited_at TIMESTAMPTZ DEFAULT NOW(),
    accepted_at TIMESTAMPTZ,
    joined_at TIMESTAMPTZ,
    UNIQUE(project_id, user_id)
);

CREATE INDEX idx_project_members_project_id ON public.project_members(project_id);
CREATE INDEX idx_project_members_user_id ON public.project_members(user_id);
CREATE INDEX idx_project_members_invite_token ON public.project_members(invite_token);

-- ========== Invitations (Pending) ==========
CREATE TABLE IF NOT EXISTS public.invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    token VARCHAR(255) UNIQUE NOT NULL,
    token_expires_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(50) DEFAULT 'pending', -- pending, accepted, expired
    created_by UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    accepted_at TIMESTAMPTZ,
    UNIQUE(project_id, email)
);

CREATE INDEX idx_invitations_project_id ON public.invitations(project_id);
CREATE INDEX idx_invitations_email ON public.invitations(email);
CREATE INDEX idx_invitations_token ON public.invitations(token);

-- ========== Global Credentials (SMTP, etc) ==========
CREATE TABLE IF NOT EXISTS public.global_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL, -- smtp, slack, teams, etc
    provider VARCHAR(100),
    encrypted_value TEXT NOT NULL, -- criptografado
    is_active BOOLEAN DEFAULT TRUE,
    last_rotated_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_by UUID NOT NULL REFERENCES public.users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_global_creds_type ON public.global_credentials(type);
CREATE INDEX idx_global_creds_active ON public.global_credentials(is_active);

-- ========== Global Audit Log ==========
CREATE TABLE IF NOT EXISTS public.audit_log_global (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(100) NOT NULL, -- user.created, project.created, cred.rotated, etc
    actor_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
    actor_email VARCHAR(255),
    resource_type VARCHAR(100), -- user, project, organization, credential
    resource_id UUID,
    details JSONB,
    previous_hash UUID, -- hash do evento anterior (chain)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_global_event_type ON public.audit_log_global(event_type);
CREATE INDEX idx_audit_global_actor_id ON public.audit_log_global(actor_id);
CREATE INDEX idx_audit_global_resource ON public.audit_log_global(resource_type, resource_id);
CREATE INDEX idx_audit_global_created_at ON public.audit_log_global(created_at DESC);

-- ========== Sessions ==========
CREATE TABLE IF NOT EXISTS public.sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    refresh_token VARCHAR(500) UNIQUE NOT NULL,
    access_token_hash VARCHAR(255),
    ip_address INET,
    user_agent TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sessions_user_id ON public.sessions(user_id);
CREATE INDEX idx_sessions_refresh_token ON public.sessions(refresh_token);
CREATE INDEX idx_sessions_expires_at ON public.sessions(expires_at);

-- ============================================================================
-- PARTE 2: FUNÇÃO PARA CRIAR SCHEMA POR TENANT
-- ============================================================================

CREATE OR REPLACE FUNCTION create_project_schema(project_slug VARCHAR)
RETURNS VOID AS $$
DECLARE
    schema_name VARCHAR;
BEGIN
    schema_name := 'proj_' || project_slug;

    -- Criar schema
    EXECUTE 'CREATE SCHEMA IF NOT EXISTS ' || schema_name;

    -- Tabelas do tenant
    EXECUTE '
        CREATE TABLE IF NOT EXISTS ' || schema_name || '.ocg (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL UNIQUE,

            -- ProfileS
            project_profile JSONB,
            output_profile JSONB,
            stack_profile JSONB,
            compliance_profile JSONB,

            -- Estados
            status VARCHAR(50) DEFAULT "initializing",

            -- Timestamps
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            propagated_at TIMESTAMPTZ
        )
    ';

    EXECUTE '
        CREATE TABLE IF NOT EXISTS ' || schema_name || '.ocg_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ocg_id UUID NOT NULL,
            changed_by UUID,
            changes JSONB,
            reason VARCHAR(500),
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ';

    EXECUTE '
        CREATE TABLE IF NOT EXISTS ' || schema_name || '.artifacts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,
            filename VARCHAR(500) NOT NULL,
            original_filename VARCHAR(500),
            mime_type VARCHAR(100),
            file_size BIGINT,

            -- Classificação P1-P7
            p1_score NUMERIC(3,2),
            p2_score NUMERIC(3,2),
            p3_score NUMERIC(3,2),
            p4_score NUMERIC(3,2),
            p5_score NUMERIC(3,2),
            p6_score NUMERIC(3,2),
            p7_score NUMERIC(3,2),

            -- LGPD
            status VARCHAR(50) DEFAULT "ingested", -- ingested, classified, quarantined, approved, merged
            pii_detected BOOLEAN DEFAULT FALSE,
            pii_details JSONB,

            -- Hash para deduplicação
            content_hash VARCHAR(255),

            -- Rastreabilidade
            uploaded_by UUID,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    ';

    EXECUTE '
        CREATE TABLE IF NOT EXISTS ' || schema_name || '.merged_artifacts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,
            artifact_ids UUID[] NOT NULL, -- lista de artifacts merged
            consolidated_content TEXT,
            conflict_notes JSONB,
            merged_by UUID,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ';

    EXECUTE '
        CREATE TABLE IF NOT EXISTS ' || schema_name || '.gatekeeper_evaluations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,

            -- Scores por pilar
            p1_score NUMERIC(3,2),
            p2_score NUMERIC(3,2),
            p3_score NUMERIC(3,2),
            p4_score NUMERIC(3,2),
            p5_score NUMERIC(3,2),
            p6_score NUMERIC(3,2),
            p7_score NUMERIC(3,2),
            overall_score NUMERIC(3,2),

            -- Análise
            gaps JSONB,
            recommendations JSONB,
            blocking_status VARCHAR(50), -- none, blocked_p7

            evaluated_by VARCHAR(50), -- system, human
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ';

    EXECUTE '
        CREATE TABLE IF NOT EXISTS ' || schema_name || '.arguidor_responses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,
            evaluation_id UUID NOT NULL,
            pillar VARCHAR(5),
            question TEXT,
            response TEXT,
            evidence_urls TEXT[],
            answered_by UUID,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ';

    EXECUTE '
        CREATE TABLE IF NOT EXISTS ' || schema_name || '.generated_files (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,

            -- Rastreabilidade
            generation_id UUID,
            source_artifact_id UUID,
            source_requirement VARCHAR(100),

            -- Arquivo
            file_path VARCHAR(500),
            file_type VARCHAR(50), -- code, test, doc, config
            language VARCHAR(50),
            content TEXT,
            content_hash VARCHAR(255),

            -- Estados
            status VARCHAR(50) DEFAULT "draft", -- draft, in_review, approved, merged, deployed

            -- VCS
            commit_sha VARCHAR(40),
            pr_url VARCHAR(500),

            created_by UUID,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    ';

    EXECUTE '
        CREATE TABLE IF NOT EXISTS ' || schema_name || '.test_plans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,
            test_type VARCHAR(50) NOT NULL, -- unit, integration, regression
            test_name VARCHAR(255),
            test_code TEXT,
            expected_outcome TEXT,
            status VARCHAR(50) DEFAULT "draft",
            created_by UUID,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ';

    EXECUTE '
        CREATE TABLE IF NOT EXISTS ' || schema_name || '.test_executions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,
            test_plan_id UUID NOT NULL,
            executor_container_id VARCHAR(255),
            status VARCHAR(50), -- running, passed, failed, timeout
            output TEXT,
            logs TEXT,
            coverage_percentage NUMERIC(5,2),
            duration_seconds NUMERIC(8,2),
            executed_at TIMESTAMPTZ DEFAULT NOW()
        )
    ';

    EXECUTE '
        CREATE TABLE IF NOT EXISTS ' || schema_name || '.webhooks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,
            provider VARCHAR(50), -- github, gitlab
            provider_id VARCHAR(255),
            event_types VARCHAR[] DEFAULT ARRAY["push", "pull_request"],
            secret_encrypted VARCHAR(500),
            is_active BOOLEAN DEFAULT FALSE,
            status VARCHAR(50) DEFAULT "pending_validation", -- pending_validation, active, failed
            last_ping_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ';

    EXECUTE '
        CREATE TABLE IF NOT EXISTS ' || schema_name || '.credentials (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,
            name VARCHAR(255),
            type VARCHAR(50), -- vcs_token, docker_registry, api_key, etc
            provider VARCHAR(100),
            encrypted_value TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            expires_at TIMESTAMPTZ,
            last_rotated_at TIMESTAMPTZ,
            created_by UUID,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ';

    EXECUTE '
        CREATE TABLE IF NOT EXISTS ' || schema_name || '.audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_type VARCHAR(100),
            actor_id UUID,
            actor_email VARCHAR(255),
            module VARCHAR(50), -- m4, m5, m6, etc
            resource_type VARCHAR(100),
            resource_id UUID,
            details JSONB,
            previous_hash UUID,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ';

    -- Criar índices
    EXECUTE '
        CREATE INDEX idx_' || schema_name || '_artifacts_status
        ON ' || schema_name || '.artifacts(status)
    ';

    EXECUTE '
        CREATE INDEX idx_' || schema_name || '_generated_files_status
        ON ' || schema_name || '.generated_files(status)
    ';

    EXECUTE '
        CREATE INDEX idx_' || schema_name || '_audit_log_event_type
        ON ' || schema_name || '.audit_log(event_type)
    ';

END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- PARTE 3: FUNCTION PARA DELETAR SCHEMA DO TENANT
-- ============================================================================

CREATE OR REPLACE FUNCTION drop_project_schema(project_slug VARCHAR)
RETURNS VOID AS $$
DECLARE
    schema_name VARCHAR;
BEGIN
    schema_name := 'proj_' || project_slug;
    EXECUTE 'DROP SCHEMA IF EXISTS ' || schema_name || ' CASCADE';
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- PARTE 4: ÍNDICES GLOBAIS IMPORTANTES
-- ============================================================================

CREATE INDEX idx_audit_global_chain ON public.audit_log_global(previous_hash);

-- ============================================================================
-- COMENTÁRIOS
-- ============================================================================

COMMENT ON SCHEMA public IS 'Global GCA tables - Shared across all tenants';
COMMENT ON TABLE public.users IS 'Users globais do GCA';
COMMENT ON TABLE public.organizations IS 'Organizações (container de projetos)';
COMMENT ON TABLE public.projects IS 'Projetos são tenants isolados';
COMMENT ON TABLE public.audit_log_global IS 'Append-only audit trail (chain de eventos)';

-- ============================================================================
-- FIM DO SCHEMA
-- ============================================================================
