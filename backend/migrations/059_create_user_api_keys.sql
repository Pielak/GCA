-- MVP: Canonical IA_* Personas - API Keys armazenadas criptografadas

-- Tabela: user_api_keys (armazena chaves de API para usuários, especialmente engines IA_*)
CREATE TABLE IF NOT EXISTS user_api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    api_key_hash VARCHAR(255) NOT NULL UNIQUE, -- SHA256(api_key) para lookup
    api_key_encrypted TEXT NOT NULL, -- pgp_sym_encrypt(api_key, master_key)
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_used_at TIMESTAMP WITH TIME ZONE,
    rotated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_user_api_keys_user ON user_api_keys(user_id);
CREATE INDEX idx_user_api_keys_hash ON user_api_keys(api_key_hash);
