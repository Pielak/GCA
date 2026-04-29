-- MVP: Canonical IA_* Personas - marcar usuários como engines

ALTER TABLE users ADD COLUMN IF NOT EXISTS is_engine BOOLEAN DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_users_is_engine ON users(is_engine);

-- Usuários engines (IA_*) nunca recebem notificações por email
CREATE OR REPLACE FUNCTION skip_notifications_for_engines()
RETURNS TRIGGER AS $$
BEGIN
    IF (SELECT is_engine FROM users WHERE id = NEW.user_id LIMIT 1) THEN
        RETURN NULL;  -- Cancela insert da notificação
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trig_skip_notifications_for_engines ON user_notifications;
CREATE TRIGGER trig_skip_notifications_for_engines
BEFORE INSERT ON user_notifications
FOR EACH ROW
EXECUTE FUNCTION skip_notifications_for_engines();
