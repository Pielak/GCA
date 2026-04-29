-- MVP B Emenda: personas IA_* são engines, não recebem notificações de email
-- Email deve ser NULL para is_engine=TRUE, UNIQUE+NOT NULL para usuários normais

-- 1. Remover constraint de email única (será recriada como check)
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key;

-- 2. Fazer email nullable
ALTER TABLE users ALTER COLUMN email DROP NOT NULL;

-- 3. Adicionar check: email é obrigatório para usuários normais, opcional para engines
ALTER TABLE users ADD CONSTRAINT check_email_required_for_users
  CHECK (is_engine = TRUE OR email IS NOT NULL);

-- 4. Unique constraint apenas para emails não-null (PostgreSQL ignora NULLs em UNIQUE)
ALTER TABLE users ADD CONSTRAINT users_email_unique_not_null
  UNIQUE NULLS NOT DISTINCT (email);

-- 5. Remover emails existentes das personas (mantém a integridade funcional)
UPDATE users SET email = NULL WHERE is_engine = TRUE;
