-- Add missing columns to users table
-- GCA User model expects: first_access_completed, password_changed_at

ALTER TABLE users ADD COLUMN IF NOT EXISTS first_access_completed BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMP WITH TIME ZONE;

-- Add index for first_access_completed
CREATE INDEX IF NOT EXISTS ix_users_first_access_completed ON users(first_access_completed);

-- Update existing users to mark first access as completed
UPDATE users SET first_access_completed = TRUE WHERE first_access_completed IS NULL;
