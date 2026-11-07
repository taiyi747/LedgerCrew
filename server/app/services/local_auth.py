"""Database backed local identities and revocable server sessions."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.security import AuthenticatedIdentity, AuthSession
from app.db.types import utc_now
from app.models import AuditLog, User, UserSession

SCHEME = "LocalSession"
_HASH_PARAMS = "scrypt:16384:8:1"


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return f"{_HASH_PARAMS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        params, salt_hex, digest_hex = stored.split("$", 2)
        if params != _HASH_PARAMS:
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=16384, r=8, p=1)
        return hmac.compare_digest(actual, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class LocalIdentityProvider:
    scheme = SCHEME

    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self.sessions = sessions
        self.settings = settings

    async def login(self, username: str, password: SecretStr) -> AuthSession | None:
        name = username.strip().lower()
        async with self.sessions() as db:
            user = await db.scalar(select(User).where(User.username == name))
            now = utc_now()
            if user is None or not user.is_active or (user.locked_until is not None and user.locked_until > now):
                return None
            if not verify_password(password.get_secret_value(), user.password_hash):
                user.failed_attempts += 1
                if user.failed_attempts >= self.settings.auth_max_failed_attempts:
                    user.locked_until = now + timedelta(seconds=self.settings.auth_lock_seconds)
                db.add(AuditLog(actor_type="security", actor_id=user.id, action="auth.login_failed",
                                entity_type="user", entity_id=user.id))
                await db.commit()
                return None
            user.failed_attempts = 0
            user.locked_until = None
            token = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(32)
            expiry = now + timedelta(seconds=self.settings.auth_session_ttl_seconds)
            db.add(UserSession(token_hash=_digest(token), csrf_hash=_digest(csrf), user_id=user.id,
                               expires_at=expiry))
            db.add(AuditLog(actor_type="security", actor_id=user.id, action="auth.login",
                            entity_type="user", entity_id=user.id))
            await db.commit()
            identity = AuthenticatedIdentity(user_id=user.id, email="", username=user.username, role=user.role)
            return AuthSession(scheme=SCHEME, credential=token, expires_at=expiry, identity=identity,
                               csrf_token=csrf)

    async def resolve(self, scheme: str, credential: str) -> AuthenticatedIdentity | None:
        if scheme != SCHEME or not credential:
            return None
        async with self.sessions() as db:
            auth = await db.get(UserSession, _digest(credential))
            if auth is None or auth.revoked_at is not None or auth.expires_at <= utc_now():
                return None
            user = await db.get(User, auth.user_id)
            if user is None or not user.is_active:
                return None
            return AuthenticatedIdentity(user_id=user.id, email="", username=user.username, role=user.role)

    async def validate_csrf(self, credential: str, token: str) -> bool:
        async with self.sessions() as db:
            auth = await db.get(UserSession, _digest(credential))
            return bool(auth and auth.revoked_at is None and auth.expires_at > utc_now()
                        and hmac.compare_digest(auth.csrf_hash, _digest(token)))

    async def logout(self, scheme: str, credential: str) -> bool:
        if scheme != SCHEME or not credential:
            return False
        async with self.sessions() as db:
            auth = await db.get(UserSession, _digest(credential))
            if auth is None or auth.revoked_at is not None or auth.expires_at <= utc_now():
                return False
            auth.revoked_at = utc_now()
            db.add(AuditLog(actor_type="security", actor_id=auth.user_id, action="auth.logout",
                            entity_type="user", entity_id=auth.user_id))
            await db.commit()
            return True


async def create_user(db: AsyncSession, username: str, password: str, role: str = "customer") -> User:
    name = username.strip().lower()
    if not name or len(name) > 100 or role not in {"customer", "owner"}:
        raise ValueError("Invalid username or role")
    if await db.scalar(select(User.id).where(User.username == name)):
        raise ValueError("Username already exists")
    user = User(username=name, password_hash=hash_password(password), role=role, is_active=True,
                failed_attempts=0, created_at=datetime.now(UTC))
    db.add(user)
    await db.flush()
    db.add(AuditLog(actor_type="security", actor_id=user.id, action="auth.user_created",
                    entity_type="user", entity_id=user.id, details={"role": role}))
    await db.commit()
    return user
