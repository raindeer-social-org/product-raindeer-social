from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import CurrentUser, get_current_user
from apps.api.auth.jwt import create_access_token, hash_password, verify_password
from apps.api.config.database import get_db
from apps.api.models.organization import Organization
from apps.api.models.user import User, UserRole

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    password: str


class RegisterResponse(BaseModel):
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


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    """Issue #123: self-serve signup (step 1 of 3 of the new onboarding
    flow). No registration endpoint existed anywhere in this codebase
    before this — users were only ever seeded directly — so this is a new,
    additive capability rather than a rewire of something that already
    worked.

    Creates a brand-new Organization for the signing-up user (there's no
    invite-a-teammate-to-an-existing-org flow yet) and makes them its
    OWNER, matching the highest-privilege role `require_role` gates write
    endpoints with. `first_name`/`last_name` aren't persisted anywhere —
    User has no name column yet — they're used only to seed a human-
    readable Organization name; adding real profile fields is left to a
    dedicated follow-up rather than bundled into this endpoint.
    """
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists"
        )

    org_name = f"{payload.first_name} {payload.last_name}".strip() or payload.email
    organization = Organization(name=org_name)
    db.add(organization)
    db.flush()

    user = User(
        organization_id=organization.id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=UserRole.OWNER,
    )
    db.add(user)
    db.flush()
    db.refresh(user)

    token = create_access_token(
        user_id=str(user.id), org_id=str(organization.id), role=user.role.value
    )
    return RegisterResponse(access_token=token)


@router.get("/me")
def me(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    return {
        "user_id": current_user.user_id,
        "org_id": current_user.org_id,
        "role": current_user.role.value,
    }
