-- Migration: Add password reset and first access support
-- Date: 2026-04-05

-- Add columns to users table for first access tracking
ALTER TABLE users ADD COLUMN IF NOT EXISTS first_access_completed BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;

-- Create index for first_access_completed
CREATE INDEX IF NOT EXISTS idx_users_first_access_completed ON users(first_access_completed);

-- Create reset_tokens table
CREATE TABLE IF NOT EXISTS reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(255) NOT NULL UNIQUE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    used_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT reset_token_token_key UNIQUE (token)
);

-- Create indexes for reset_tokens
CREATE INDEX IF NOT EXISTS idx_reset_tokens_user_id ON reset_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_reset_tokens_token ON reset_tokens(token);
CREATE INDEX IF NOT EXISTS idx_reset_tokens_expires_at ON reset_tokens(expires_at);
CREATE INDEX IF NOT EXISTS idx_reset_tokens_used ON reset_tokens(used);

-- Add created_at index to users for auditing
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);

-- Comment on tables for documentation
COMMENT ON TABLE reset_tokens IS 'Secure password reset tokens with TTL and single-use enforcement';
COMMENT ON COLUMN reset_tokens.user_id IS 'FK to users table';
COMMENT ON COLUMN reset_tokens.token IS 'Unique secure token (32-byte urlsafe random)';
COMMENT ON COLUMN reset_tokens.expires_at IS 'Token expiration timestamp (1 hour from creation)';
COMMENT ON COLUMN reset_tokens.used IS 'Flag indicating if token has been used';
COMMENT ON COLUMN reset_tokens.used_at IS 'Timestamp when token was used (for audit)';
