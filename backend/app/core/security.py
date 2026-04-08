"""
GCA Security Module
Handles JWT, password hashing, and encryption/decryption
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from uuid import UUID
import base64

from jose import JWTError, jwt
import bcrypt
from cryptography.fernet import Fernet
import structlog
import secrets

from app.core.config import settings

logger = structlog.get_logger(__name__)


# ============================================================================
# PASSWORD UTILITIES
# ============================================================================
def hash_password(password: str) -> str:
    """Hash a password using bcrypt. Passwords longer than 72 bytes are truncated."""
    # bcrypt has a 72-byte limit, so we truncate if necessary
    pwd_bytes = password.encode('utf-8')[:72]
    hashed = bcrypt.hashpw(pwd_bytes, bcrypt.gensalt(rounds=12))
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash. Passwords longer than 72 bytes are truncated."""
    # bcrypt has a 72-byte limit, so we truncate if necessary (must match hash_password)
    pwd_bytes = plain_password.encode('utf-8')[:72]
    hashed_bytes = hashed_password.encode('utf-8') if isinstance(hashed_password, str) else hashed_password
    return bcrypt.checkpw(pwd_bytes, hashed_bytes)


def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
    """
    Validate password strength according to settings.
    Returns (is_valid, error_message)
    """
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters"

    if settings.PASSWORD_REQUIRE_UPPERCASE and not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"

    if settings.PASSWORD_REQUIRE_LOWERCASE and not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"

    if settings.PASSWORD_REQUIRE_DIGITS and not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"

    if settings.PASSWORD_REQUIRE_SYMBOLS and not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        return False, "Password must contain at least one special character"

    return True, None


# ============================================================================
# JWT UTILITIES
# ============================================================================
def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


def create_refresh_token(
    user_id: UUID,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT refresh token"""
    if expires_delta is None:
        expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    data = {
        "sub": str(user_id),
        "type": "refresh",
    }
    return create_access_token(data, expires_delta)


def verify_token(token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
    """
    Verify a JWT token and return payload.
    Returns None if token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )

        if token_type == "refresh" and payload.get("type") != "refresh":
            logger.warning("token.type_mismatch", expected="refresh", got=payload.get("type"))
            return None

        return payload

    except JWTError as e:
        logger.warning("token.verification_failed", error=str(e))
        return None


# ============================================================================
# ENCRYPTION UTILITIES (AES-256)
# ============================================================================
def get_cipher_suite() -> Fernet:
    """Get Fernet cipher suite from encryption key"""
    key = settings.ENCRYPTION_KEY.encode() if isinstance(settings.ENCRYPTION_KEY, str) else settings.ENCRYPTION_KEY
    # Ensure key is proper base64 encoded 32 bytes (44 chars in base64)
    if len(key) != 44:
        logger.warning("encryption.key_size_mismatch", expected=44, got=len(key))
    return Fernet(key)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string value"""
    try:
        cipher = get_cipher_suite()
        encrypted = cipher.encrypt(plaintext.encode())
        return encrypted.decode()
    except Exception as e:
        logger.error("encryption.failed", error=str(e))
        raise


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a string value"""
    try:
        cipher = get_cipher_suite()
        decrypted = cipher.decrypt(ciphertext.encode())
        return decrypted.decode()
    except Exception as e:
        logger.error("decryption.failed", error=str(e))
        raise


# ============================================================================
# SENSITIVE DATA ENCRYPTION (For API keys, tokens, credentials)
# ============================================================================
def encrypt_token(token: str, master_key = None) -> str:
    """Encrypt sensitive tokens (API keys, SMTP password, etc)"""
    try:
        cipher = get_cipher_suite()
        encrypted = cipher.encrypt(token.encode())
        return encrypted.decode()
    except Exception as e:
        logger.error("token.encryption.failed", error=str(e))
        raise


def decrypt_token(encrypted_token: str, master_key = None) -> str:
    """Decrypt sensitive tokens"""
    try:
        cipher = get_cipher_suite()
        decrypted = cipher.decrypt(encrypted_token.encode())
        return decrypted.decode()
    except Exception as e:
        logger.error("token.decryption.failed", error=str(e))
        raise


# ============================================================================
# TOKEN DATA MODELS
# ============================================================================
class TokenPayload:
    """JWT token payload structure"""

    def __init__(
        self,
        user_id: UUID,
        email: str,
        is_admin: bool,
        organizations: list[UUID],
        projects: Dict[UUID, list[str]],
        exp: datetime,
    ):
        self.user_id = user_id
        self.email = email
        self.is_admin = is_admin
        self.organizations = organizations
        self.projects = projects
        self.exp = exp

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JWT encoding"""
        return {
            "sub": str(self.user_id),
            "email": self.email,
            "is_admin": self.is_admin,
            "organizations": [str(org_id) for org_id in self.organizations],
            "projects": {str(k): v for k, v in self.projects.items()},
            "exp": self.exp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenPayload":
        """Create from JWT payload dictionary"""
        return cls(
            user_id=UUID(data["sub"]),
            email=data["email"],
            is_admin=data["is_admin"],
            organizations=[UUID(org_id) for org_id in data.get("organizations", [])],
            projects={UUID(k): v for k, v in data.get("projects", {}).items()},
            exp=datetime.fromtimestamp(data["exp"], tz=timezone.utc),
        )
