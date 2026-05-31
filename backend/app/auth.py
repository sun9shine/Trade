"""
Authentication & User Management System
- Bcrypt password hashing
- JWT token issuance and validation
- Role-based access control (admin, operator, viewer)
- Session management with refresh tokens
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

import structlog
from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import app_settings
from app.database import async_session_factory

logger = structlog.get_logger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7


class UserRole(str, Enum):
    """User role levels."""
    ADMIN = "admin"         # Full access: credentials, kill switch, user management
    OPERATOR = "operator"   # Can view metrics, manage webhooks, but no credential access
    VIEWER = "viewer"       # Read-only: metrics and positions only


class TokenPayload(BaseModel):
    """JWT token payload structure."""
    sub: str  # user_id
    username: str
    role: UserRole
    exp: datetime
    iat: datetime
    jti: str  # Unique token ID for revocation


class UserCreate(BaseModel):
    """Schema for creating a new user."""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole = UserRole.VIEWER
    display_name: Optional[str] = None


class UserResponse(BaseModel):
    """User response (no sensitive data)."""
    id: str
    username: str
    role: UserRole
    display_name: Optional[str]
    is_active: bool
    last_login: Optional[str]
    created_at: str


class LoginRequest(BaseModel):
    """Login request body."""
    username: str
    password: str


class TokenResponse(BaseModel):
    """Login response with tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserResponse


# ─── PASSWORD UTILITIES ───────────────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ─── TOKEN UTILITIES ──────────────────────────────────────────────────────────

def create_access_token(user_id: str, username: str, role: UserRole) -> str:
    """Create a short-lived JWT access token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": user_id,
        "username": username,
        "role": role.value,
        "exp": expire,
        "iat": now,
        "jti": str(uuid4()),
        "type": "access",
    }
    return jwt.encode(payload, app_settings.jwt_secret, algorithm=ALGORITHM)


def create_refresh_token(user_id: str, username: str, role: UserRole) -> str:
    """Create a long-lived JWT refresh token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": user_id,
        "username": username,
        "role": role.value,
        "exp": expire,
        "iat": now,
        "jti": str(uuid4()),
        "type": "refresh",
    }
    return jwt.encode(payload, app_settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, app_settings.jwt_secret, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.debug("auth.token_decode_failed", error=str(e))
        return None


# ─── USER REPOSITORY ──────────────────────────────────────────────────────────

# Import the User model (we'll add it to models.py)
# For now, use direct SQL approach compatible with existing schema

class UserRepository:
    """Database operations for user management."""

    @staticmethod
    async def create_user(user: UserCreate) -> Optional[dict]:
        """Create a new user with hashed password."""
        from app.models import User

        try:
            async with async_session_factory() as session:
                # Check if username already exists
                stmt = select(User).where(User.username == user.username)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    logger.warning("auth.user_exists", username=user.username)
                    return None

                hashed = hash_password(user.password)
                new_user = User(
                    username=user.username,
                    password_hash=hashed,
                    role=user.role.value,
                    display_name=user.display_name or user.username,
                    is_active=True,
                )
                session.add(new_user)
                await session.commit()
                await session.refresh(new_user)

                logger.info("auth.user_created", username=user.username, role=user.role.value)
                return {
                    "id": str(new_user.id),
                    "username": new_user.username,
                    "role": new_user.role,
                    "display_name": new_user.display_name,
                    "is_active": new_user.is_active,
                    "created_at": new_user.created_at.isoformat(),
                }
        except Exception as e:
            logger.error("auth.create_user_failed", error=str(e))
            return None

    @staticmethod
    async def authenticate(username: str, password: str) -> Optional[dict]:
        """Authenticate user by username and password."""
        from app.models import User

        try:
            async with async_session_factory() as session:
                stmt = select(User).where(
                    and_(User.username == username, User.is_active == True)
                )
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()

                if not user:
                    logger.warning("auth.user_not_found", username=username)
                    return None

                if not verify_password(password, user.password_hash):
                    logger.warning("auth.invalid_password", username=username)
                    return None

                # Update last login
                user.last_login = datetime.now(timezone.utc)
                await session.commit()

                logger.info("auth.login_success", username=username)
                return {
                    "id": str(user.id),
                    "username": user.username,
                    "role": user.role,
                    "display_name": user.display_name,
                    "is_active": user.is_active,
                    "last_login": user.last_login.isoformat() if user.last_login else None,
                    "created_at": user.created_at.isoformat(),
                }
        except Exception as e:
            logger.error("auth.authenticate_failed", error=str(e))
            return None

    @staticmethod
    async def get_user_by_id(user_id: str) -> Optional[dict]:
        """Get user by ID."""
        from app.models import User
        from uuid import UUID as PyUUID

        try:
            async with async_session_factory() as session:
                stmt = select(User).where(User.id == PyUUID(user_id))
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()

                if not user:
                    return None

                return {
                    "id": str(user.id),
                    "username": user.username,
                    "role": user.role,
                    "display_name": user.display_name,
                    "is_active": user.is_active,
                    "last_login": user.last_login.isoformat() if user.last_login else None,
                    "created_at": user.created_at.isoformat(),
                }
        except Exception as e:
            logger.error("auth.get_user_failed", error=str(e))
            return None

    @staticmethod
    async def list_users() -> list[dict]:
        """List all users (no passwords)."""
        from app.models import User

        try:
            async with async_session_factory() as session:
                stmt = select(User).order_by(User.created_at.desc())
                result = await session.execute(stmt)
                users = result.scalars().all()
                return [
                    {
                        "id": str(u.id),
                        "username": u.username,
                        "role": u.role,
                        "display_name": u.display_name,
                        "is_active": u.is_active,
                        "last_login": u.last_login.isoformat() if u.last_login else None,
                        "created_at": u.created_at.isoformat(),
                    }
                    for u in users
                ]
        except Exception as e:
            logger.error("auth.list_users_failed", error=str(e))
            return []

    @staticmethod
    async def update_password(user_id: str, new_password: str) -> bool:
        """Update user password."""
        from app.models import User
        from uuid import UUID as PyUUID

        try:
            async with async_session_factory() as session:
                hashed = hash_password(new_password)
                stmt = update(User).where(User.id == PyUUID(user_id)).values(
                    password_hash=hashed
                )
                await session.execute(stmt)
                await session.commit()
                return True
        except Exception as e:
            logger.error("auth.update_password_failed", error=str(e))
            return False

    @staticmethod
    async def deactivate_user(user_id: str) -> bool:
        """Deactivate a user account."""
        from app.models import User
        from uuid import UUID as PyUUID

        try:
            async with async_session_factory() as session:
                stmt = update(User).where(User.id == PyUUID(user_id)).values(
                    is_active=False
                )
                await session.execute(stmt)
                await session.commit()
                return True
        except Exception as e:
            logger.error("auth.deactivate_failed", error=str(e))
            return False

    @staticmethod
    async def ensure_admin_exists():
        """Create default admin user if no users exist (first-run setup)."""
        from app.models import User

        try:
            async with async_session_factory() as session:
                stmt = select(User).limit(1)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if not existing:
                    # Create default admin
                    default_password = app_settings.app_secret_key[:16] + "Admin1!"
                    hashed = hash_password(default_password)
                    admin = User(
                        username="admin",
                        password_hash=hashed,
                        role="admin",
                        display_name="System Administrator",
                        is_active=True,
                    )
                    session.add(admin)
                    await session.commit()
                    logger.info(
                        "auth.default_admin_created",
                        username="admin",
                        msg="Change password immediately!",
                    )
        except Exception as e:
            logger.error("auth.ensure_admin_failed", error=str(e))


# ─── RBAC PERMISSION CHECK ───────────────────────────────────────────────────

# Permission matrix: which roles can access which resources
ROLE_PERMISSIONS = {
    UserRole.ADMIN: {
        "credentials:read", "credentials:write",
        "rpc:read", "rpc:write",
        "webhooks:read", "webhooks:write",
        "metrics:read",
        "trades:read",
        "positions:read",
        "kill_switch:activate",
        "users:read", "users:write",
        "market_mapping:write",
    },
    UserRole.OPERATOR: {
        "rpc:read", "rpc:write",
        "webhooks:read", "webhooks:write",
        "metrics:read",
        "trades:read",
        "positions:read",
        "kill_switch:activate",
    },
    UserRole.VIEWER: {
        "metrics:read",
        "trades:read",
        "positions:read",
    },
}


def check_permission(role: UserRole, permission: str) -> bool:
    """Check if a role has a specific permission."""
    allowed = ROLE_PERMISSIONS.get(role, set())
    return permission in allowed
