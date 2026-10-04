"""Shared FastAPI dependencies.

Kept import-light on purpose: `app.utils.deps` is imported by every router, and
pulling in the service layer here would create an import cycle.
"""

from app.utils.deps import (
    ApiError,
    bad_request,
    conflict,
    forbidden,
    get_current_user,
    not_found,
    require_any,
    require_customer,
    require_role,
    require_staff,
    unauthorized,
)

__all__ = [
    "ApiError",
    "bad_request",
    "conflict",
    "forbidden",
    "get_current_user",
    "not_found",
    "require_any",
    "require_customer",
    "require_role",
    "require_staff",
    "unauthorized",
]
