from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models.user import Role, User
from app.services.auth import AuthError, decode_token


class ApiError(HTTPException):
    """HTTPException carrying the machine-readable `code` from SPEC 3.3."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(status_code=status_code, detail={"code": code, "message": message})
        self.code = code


def bad_request(code: str, message: str) -> ApiError:
    return ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, code, message)


def not_found(code: str, message: str) -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, code, message)


def forbidden(code: str = "FORBIDDEN", message: str = "Insufficient permissions.") -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, code, message)


def unauthorized(code: str = "UNAUTHENTICATED", message: str = "Not authenticated.") -> ApiError:
    return ApiError(status.HTTP_401_UNAUTHORIZED, code, message)


def conflict(code: str, message: str) -> ApiError:
    return ApiError(status.HTTP_409_CONFLICT, code, message)


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_session),
) -> User:
    """Resolve the bearer token to a User.

    Uses the raw header rather than HTTPBearer so a missing header produces our
    uniform error envelope instead of a bare 403.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise unauthorized("MISSING_TOKEN", "Authorization header must be 'Bearer <token>'.")

    token = authorization.split(" ", 1)[1].strip()
    try:
        user_id = decode_token(token)
    except AuthError as exc:
        raise unauthorized(exc.code, exc.message) from exc

    user = db.get(User, user_id)
    if user is None:
        raise unauthorized("USER_NOT_FOUND", "Token subject no longer exists.")
    return user


def require_role(*roles: Role) -> Callable[..., User]:
    """Dependency factory guarding an endpoint by role (SPEC 2)."""

    allowed = ", ".join(r.value for r in roles)

    def _guard(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise forbidden("ROLE_REQUIRED", f"This action requires role: {allowed}.")
        return current_user

    return _guard


require_customer = require_role(Role.customer)
require_staff = require_role(Role.staff)
require_any = require_role(Role.customer, Role.staff)
