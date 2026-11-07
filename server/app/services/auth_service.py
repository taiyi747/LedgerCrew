import calendar
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import AuditLog, Order, Studio, TrialRequest, User, UserSession

SESSION_COOKIE_NAME = "ledgercrew_session"
SESSION_TTL = timedelta(days=30)
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_MIN_PASSWORD_LENGTH = 6


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    try:
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(digest_hex)),
        )
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalize_username(username: str) -> tuple[str, str]:
    display = username.strip()
    if not display:
        raise AppError("invalid_username", "请输入用户名", 422)
    if any(character.isspace() for character in display):
        raise AppError("invalid_username", "用户名不能包含空格", 422)
    if len(display) > 32:
        raise AppError("invalid_username", "用户名不能超过 32 个字符", 422)
    return display, display.casefold()


def _validate_password(password: str) -> None:
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise AppError("invalid_password", f"密码至少需要 {_MIN_PASSWORD_LENGTH} 位", 422)
    if len(password) > 256:
        raise AppError("invalid_password", "密码过长", 422)


async def register(session: AsyncSession, username: str, password: str, confirm_password: str) -> User:
    display, key = _normalize_username(username)
    _validate_password(password)
    if password != confirm_password:
        raise AppError("password_mismatch", "两次输入的密码不一致", 422)
    existing = await session.scalar(select(User.id).where(User.username_key == key))
    if existing:
        raise AppError("username_taken", "该用户名已被注册，请直接登录", 409)
    user = User(username=display, username_key=key, password_hash=_hash_password(password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def login(session: AsyncSession, username: str, password: str) -> User:
    _, key = _normalize_username(username)
    user = await session.scalar(select(User).where(User.username_key == key))
    if user is None or not _verify_password(password, user.password_hash):
        raise AppError("invalid_credentials", "用户名或密码不正确", 401)
    return user


async def create_session(session: AsyncSession, user: User) -> str:
    token = secrets.token_urlsafe(32)
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=token_digest(token),
            expires_at=datetime.now(UTC) + SESSION_TTL,
        )
    )
    await session.commit()
    return token


async def revoke_session(session: AsyncSession, token: str) -> None:
    record = await session.scalar(select(UserSession).where(UserSession.token_hash == token_digest(token)))
    if record is None or record.revoked_at is not None:
        return
    record.revoked_at = datetime.now(UTC)
    await session.commit()


async def user_for_token(session: AsyncSession, token: str) -> User | None:
    record = await session.scalar(select(UserSession).where(UserSession.token_hash == token_digest(token)))
    if record is None or record.revoked_at is not None:
        return None
    if record.expires_at <= datetime.now(UTC):
        return None
    return await session.get(User, record.user_id)


async def ensure_admin(session: AsyncSession, username: str, password: str) -> User:
    """Create the bootstrap administrator, or resync its password from settings.

    The environment is the source of truth for the administrator password, so a
    restart restores it and drops any session opened with the previous value.
    """
    display, key = _normalize_username(username)
    _validate_password(password)
    user = await session.scalar(select(User).where(User.username_key == key))
    if user is None:
        user = User(username=display, username_key=key, password_hash=_hash_password(password))
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
    if not _verify_password(password, user.password_hash):
        user.password_hash = _hash_password(password)
        await session.execute(
            update(UserSession)
            .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        await session.commit()
    return user


async def start_trial(session: AsyncSession, user: User, request_id: str) -> Order:
    """Create (or replay) the free trial order for this account page action."""
    existing = await session.scalar(select(TrialRequest).where(TrialRequest.request_id == request_id))
    if existing is not None:
        if existing.user_id != user.id:
            raise AppError("trial_conflict", "该请求已属于其他账号", 409)
        order = await session.get(Order, existing.order_id)
        if order is None:
            raise AppError("trial_conflict", "体验订单已不存在，请刷新后重试", 409)
        return order

    studio = await session.scalar(
        select(Studio).where(Studio.owner_user_id == user.id).order_by(Studio.created_at)
    )
    if studio is None:
        studio = Studio(name=f"{user.username}的工作室", business_type="digital_services", owner_user_id=user.id)
        session.add(studio)
        await session.flush()

    today = datetime.now(UTC).date()
    period_start = today.replace(day=1)
    period_end = today.replace(day=calendar.monthrange(today.year, today.month)[1])

    order = Order(
        order_no=f"LC-{secrets.token_hex(12)}",
        studio_id=studio.id,
        period_start=period_start,
        period_end=period_end,
        period_year=period_start.year,
        period_month=period_start.month,
        service_scope="monthly_records",
        price_cents=0,
        is_simulated=True,
        status="draft",
    )
    session.add(order)
    await session.flush()
    session.add(
        TrialRequest(request_id=request_id, user_id=user.id, order_id=order.id)
    )
    session.add(
        AuditLog(
            order_id=order.id,
            actor_type="customer",
            actor_id=user.id,
            action="trial.started",
            entity_type="order",
            entity_id=order.id,
        )
    )
    await session.commit()
    await session.refresh(order)
    return order


async def count_users(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(User)) or 0
