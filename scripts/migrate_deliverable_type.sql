-- Migration: Adicionar deliverable_type (Gate Bloqueante)
-- Data: 2026-04-12
-- Descrição: Tipo de entregável é obrigatório na criação do projeto.
--            Sem ele, o sistema não avança para escolha de stack, agentes ou backlog.

-- 1. Adicionar coluna na tabela projects (com default para projetos existentes)
ALTER TABLE public.projects
ADD COLUMN IF NOT EXISTS deliverable_type VARCHAR(50) NOT NULL DEFAULT 'new_system';

-- 2. Adicionar coluna na tabela project_requests
ALTER TABLE public.project_requests
ADD COLUMN IF NOT EXISTS deliverable_type VARCHAR(50) NOT NULL DEFAULT 'new_system';

-- 3. Criar índice para consultas por tipo
CREATE INDEX IF NOT EXISTS idx_projects_deliverable_type ON public.projects(deliverable_type);

-- 4. Constraint para valores válidos
ALTER TABLE public.projects
ADD CONSTRAINT chk_deliverable_type CHECK (
    deliverable_type IN (
        'new_system', 'mobile_app', 'module', 'enhancement',
        'integration', 'modernization', 'etl', 'maintenance'
    )
);

ALTER TABLE public.project_requests
ADD CONSTRAINT chk_request_deliverable_type CHECK (
    deliverable_type IN (
        'new_system', 'mobile_app', 'module', 'enhancement',
        'integration', 'modernization', 'etl', 'maintenance'
    )
);

-- Verificação
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name IN ('projects', 'project_requests')
  AND column_name = 'deliverable_type';
