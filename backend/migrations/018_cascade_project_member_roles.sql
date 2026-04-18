-- DT-027: project_member_roles.member_id não era ON DELETE CASCADE.
-- Descoberto ao deletar FinanceHub Pro em 2026-04-17 — a constraint
-- bloqueava o DELETE do projeto porque members CASCADE apagavam mas
-- project_member_roles referenciavam sem CASCADE, exigindo cleanup manual.
--
-- Fix: recriar o FK com ON DELETE CASCADE. Assim apagar um member
-- (que por sua vez cai em cascata quando o projeto é apagado) remove
-- todos os roles atribuídos automaticamente.
--
-- Idempotente: drop condicional, add do FK novo.

BEGIN;

-- Descobre o nome real do constraint (pode variar entre deployments)
DO $$
DECLARE
    constraint_name_var text;
BEGIN
    SELECT tc.constraint_name INTO constraint_name_var
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
    WHERE tc.table_name = 'project_member_roles'
      AND tc.constraint_type = 'FOREIGN KEY'
      AND kcu.column_name = 'member_id'
    LIMIT 1;

    IF constraint_name_var IS NOT NULL THEN
        EXECUTE format('ALTER TABLE project_member_roles DROP CONSTRAINT %I', constraint_name_var);
    END IF;
END $$;

ALTER TABLE project_member_roles
ADD CONSTRAINT project_member_roles_member_id_fkey
    FOREIGN KEY (member_id)
    REFERENCES project_members(id)
    ON DELETE CASCADE;

COMMIT;
