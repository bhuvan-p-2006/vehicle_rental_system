from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models.user import User
from app.schemas.auth import Token, UserLogin, UserOut, UserRegister
from app.services.auth import AuthError, AuthService
from app.utils.deps import ApiError, get_current_user, unauthorized

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: SessionDep) -> User:
    """Self-service registration always creates a customer (SPEC 2, R5)."""
    try:
        return AuthService(db).register(payload)
    except AuthError as exc:
        raise ApiError(status.HTTP_409_CONFLICT, exc.code, exc.message) from exc


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: SessionDep) -> Token:
    try:
        return AuthService(db).authenticate(payload.email, payload.password)
    except AuthError as exc:
        raise unauthorized(exc.code, exc.message) from exc


@router.get("/me", response_model=UserOut)
def me(current_user: UserDep) -> User:
    return current_user
