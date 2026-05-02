"""
GCA Configuration
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """
    Configurações globais do GCA
    """

    # App
    APP_NAME: str = "GCA - Gerenciador Central de Arquiteturas"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "development"  # development, staging, production
    APP_SECRET_KEY: str = "your-secret-key-change-in-production"
    DEBUG: bool = False

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    API_PREFIX: str = "/api/v1"
    FRONTEND_URL: str = "http://localhost:5173"

    # Admin Seed (primeiro boot)
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_TEMP_PASSWORD: str = "ChangeMe@123"

    # PostgreSQL
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "gca"
    POSTGRES_USER: str = "gca"
    POSTGRES_PASSWORD: str = "gca_secret"
    DATABASE_URL: str = "postgresql+asyncpg://gca:gca_secret@localhost:5432/gca"
    DATABASE_BACKUP_URL: Optional[str] = None
    DATABASE_ECHO: bool = False
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_PRE_PING: bool = True

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_DECODE_RESPONSES: bool = True
    N8N_REDIS_DB: int = 2

    # n8n Pipeline v2
    INGESTION_VIA_N8N: bool = False
    N8N_BASE_URL: str = "http://localhost:5678"
    GCA_CALLBACK_BASE_URL: str = "http://localhost:8000"
    GCA_WEBHOOK_SECRET: str = ""
    N8N_CALLBACK_SECRET: str = ""

    # JWT RS256
    JWT_PRIVATE_KEY_PATH: Optional[str] = None
    JWT_PUBLIC_KEY_PATH: Optional[str] = None
    JWT_ALGORITHM: str = "RS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    SESSION_INACTIVITY_HOURS: int = 8

    # JWT Legacy (HS256)
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Security
    ENCRYPTION_KEY: str = "your-encryption-key-change-in-production"  # base64 encoded
    PASSWORD_MIN_LENGTH: int = 10
    PASSWORD_REQUIRE_UPPERCASE: bool = True
    PASSWORD_REQUIRE_LOWERCASE: bool = True
    PASSWORD_REQUIRE_DIGITS: bool = True
    PASSWORD_REQUIRE_SYMBOLS: bool = True

    # SMTP
    SMTP_ENABLED: bool = False
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    SMTP_FROM_NAME: str = "GCA"

    # GitHub Integration
    GITHUB_TOKEN: Optional[str] = None
    GITHUB_REPO_URL: Optional[str] = None
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None

    # GitLab Integration
    GITLAB_CLIENT_ID: Optional[str] = None
    GITLAB_CLIENT_SECRET: Optional[str] = None

    # IA Providers
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None
    GROK_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    QWEN_API_KEY: Optional[str] = None  # Alibaba DashScope (alias: DASHSCOPE_API_KEY)
    DASHSCOPE_API_KEY: Optional[str] = None  # alternativo ao QWEN_API_KEY
    DEFAULT_AI_PROVIDER: str = "grok"  # grok, anthropic, openai, gemini, deepseek, qwen, ollama
    DEFAULT_AI_MODEL: str = "grok-3-mini"
    # DT-023: Ollama (local) — admin pode configurar Ollama como camada GCA
    # apontando pra `host.docker.internal:11434` (Docker) ou IP da máquina.
    # Sem chave por default; OLLAMA_API_KEY opcional pra reverse proxy com Bearer.
    OLLAMA_BASE_URL: Optional[str] = None  # ex: http://host.docker.internal:11434
    OLLAMA_API_KEY: Optional[str] = None
    OLLAMA_MODEL: Optional[str] = None  # default no _default_models

    # Slack
    SLACK_BOT_TOKEN: Optional[str] = None
    SLACK_SIGNING_SECRET: Optional[str] = None

    # Microsoft Teams
    TEAMS_BOT_ID: Optional[str] = None
    TEAMS_BOT_PASSWORD: Optional[str] = None

    # Storage
    STORAGE_TYPE: str = "local"  # local, s3, gcs
    STORAGE_PATH: str = "/tmp/gca-storage"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_S3_BUCKET: Optional[str] = None

    # Docker
    DOCKER_ENABLED: bool = False
    DOCKER_HOST: str = "unix:///var/run/docker.sock"
    DOCKER_EXECUTOR_IMAGE: str = "gca-executor:latest"

    # Kafka
    KAFKA_ENABLED: bool = False
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_GROUP_ID: str = "gca"
    KAFKA_TOPIC_CODEGEN: str = "gca.codegen.jobs"
    KAFKA_TOPIC_LEGACY: str = "gca.legacy.analysis"
    KAFKA_TOPIC_ARTIFACT: str = "gca.artifact.ingest"
    KAFKA_TOPIC_GATEKEEPER: str = "gca.gatekeeper.evaluate"

    # Limits
    MAX_UPLOAD_SIZE_MB: int = 100
    MAX_ARTIFACT_TEXT_LENGTH: int = 1_000_000
    ARTIFACT_EXTRACTION_TIMEOUT: int = 30  # seconds

    # Audit
    AUDIT_LOG_RETENTION_DAYS: int = 365
    AUDIT_LOG_BATCH_SIZE: int = 100

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json or text

    # CORS
    CORS_ORIGINS: list = [
        # Development
        "http://localhost:3000",
        "http://localhost:5173",
        # Production
        "https://gca.code-auditor.com.br",
        "https://api.code-auditor.com.br",
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list = ["*"]
    CORS_ALLOW_HEADERS: list = ["*"]

    # Piloter API
    PILOTER_API_KEY: Optional[str] = None
    PILOTER_API_ENDPOINT: str = "https://api.piloterr.com/v2"

    # Vault — Chave mestra para criptografia de secrets (min 32 chars)
    GCA_MASTER_KEY: str = "gca-default-master-key-change-in-production-32chars!"
    GCA_MASTER_KEY_SALT: str = "gca-salt-default"

    # N8N Integration (usar 'n8n' como hostname dentro do Docker, 'localhost' fora)
    N8N_WEBHOOK_URL: str = "http://n8n:5678/webhook"
    N8N_API_URL: str = "http://n8n:5678/api"
    N8N_API_KEY: Optional[str] = None

    # MVP-C (2026-04-25): paralelismo do scaffold dentro de cada wave
    # topológica. Items sem dep entre si rodam em paralelo até este cap.
    # 5 é equilíbrio: rate limit seguro (Anthropic = 50 RPM, DeepSeek varia)
    # e ganho real de tempo (5x speedup em projetos com baixo acoplamento).
    # Operador pode subir até ~10 com Sonnet/DeepSeek (cap mais alto de RPM)
    # ou cair pra 1-2 com Opus em horário de pico.
    SCAFFOLD_PARALLELISM: int = 5

    # Anthropic API (Claude)
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-opus-4-6"
    ANTHROPIC_TEMPERATURE: float = 0.3
    # Histórico: DT-069 subiu 4096→8192 pra acomodar Arguidor com 60+ RFs.
    # Sessão 30 (2026-04-23): 8192 ainda trunca em docs grandes (questionários
    # detalhados + respostas técnicas extensas). Sobe pra 32768 — Haiku 4.5 e
    # Sonnet 4.6 aceitam até 64K de output sem beta flag; Opus aceita 32K.
    # 32768 é safe pra todos os modelos suportados no GCA e dá 4x de margem
    # sobre o limite anterior. Operador pode override via .env se precisar.
    ANTHROPIC_MAX_TOKENS: int = 32768

    # Onboarding
    ONBOARDING_INVITE_EXPIRES_DAYS: int = 7
    STACK_CACHE_DURATION_DAYS: int = 30

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
