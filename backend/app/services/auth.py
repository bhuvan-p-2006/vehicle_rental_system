from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.user import Role, User
from app.schemas.auth import Token, UserRegister

ALGORITHM = "HS256"
# bcrypt silently truncates beyond 72 bytes; reject longer input instead.
BCRYPT_MAX_BYTES = 72


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed hash in the database — treat as a failed login, never a 500.
        return False


class AuthError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def register(self, data: UserRegister) -> User:
        """Create a customer account.

        R5 note: registration always yields role=customer. Staff accounts are
        provisioned by seed or staff-only creation, never self-service.
        """
        user = User(
            name=data.name,
            email=data.email.lower(),
            password_hash=hash_password(data.password),
            role=Role.customer,
        )
        self.db.add(user)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AuthError("EMAIL_TAKEN", "Email is already registered.") from exc
        self.db.refresh(user)
        return user

    def authenticate(self, email: str, password: str) -> Token:
        user = self.db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
        if user is None or not verify_password(password, user.password_hash):
            # Same message either way — do not disclose which accounts exist.
            raise AuthError("INVALID_CREDENTIALS", "Invalid email or password.")
        return Token(access_token=self.issue_token(user))

    def issue_token(self, user: User) -> str:
        expire = datetime.now(UTC) + timedelta(minutes=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        return str(
            jwt.encode(
                {"sub": str(user.id), "role": user.role.value, "exp": expire},
                self.settings.SECRET_KEY,
                algorithm=ALGORITHM,
            )
        )


def decode_token(token: str) -> uuid.UUID:
    """Return the user id encoded in ``token`` or raise ``AuthError``."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise AuthError("INVALID_TOKEN", "Invalid or expired token.") from exc
    sub = payload.get("sub")
    if not sub:
        raise AuthError("INVALID_TOKEN", "Token is missing a subject.")
    try:
        return uuid.UUID(sub)
    except ValueError as exc:
        raise AuthError("INVALID_TOKEN", "Token subject is malformed.") from exc
