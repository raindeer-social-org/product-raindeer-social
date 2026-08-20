from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import CurrentUser, get_current_user
from apps.api.auth.jwt import create_access_token, verify_password
from apps.api.config.database import get_db
from apps.api.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    token = create_access_token(
        user_id=str(user.id), org_id=str(user.organization_id), role=user.role.value
    )
    return LoginResponse(access_token=token)


@router.get("/me")
def me(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    return {
        "user_id": current_user.user_id,
        "org_id": current_user.org_id,
        "role": current_user.role.value,
    }
