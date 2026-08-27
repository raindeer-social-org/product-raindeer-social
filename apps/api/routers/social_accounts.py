import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import CurrentUser, get_current_user
from apps.api.auth.jwt import ALGORITHM
from apps.api.config import get_settings
from apps.api.config.database import get_db
from apps.api.middleware.rbac import require_role
from apps.api.models import Brand, SocialAccount, SocialAccountStatus, SocialPlatform, UserRole
from apps.api.schemas.social_account import AuthorizeUrlRead, SocialAccountRead
from packages.integrations.registry import get_social_oauth_provider
from packages.integrations.social.encryption import decrypt_token, encrypt_token

router = APIRouter(tags=["social-accounts"])

WRITE_ROLES = (UserRole.OWNER, UserRole.ADMIN, UserRole.EDITOR)

STATE_EXPIRES_MINUTES = 10


def _get_org_brand(db: Session, brand_id: uuid.UUID, org_id: str) -> Brand:
    brand = (
        db.query(Brand)
        .filter(Brand.id == brand_id, Brand.organization_id == uuid.UUID(org_id))
        .first()
    )
    if brand is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    return brand


def _get_account_or_404(
    db: Session, brand_id: uuid.UUID, account_id: uuid.UUID
) -> SocialAccount:
    account = (
        db.query(SocialAccount)
        .filter(SocialAccount.id == account_id, SocialAccount.brand_id == brand_id)
        .first()
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Social account not found"
        )
    return account


def _create_state(brand_id: uuid.UUID, platform: str) -> str:
    # The signed state token IS the authorization credential the callback
    # step relies on — WRITE_ROLES was already checked when /connect issued
    # it, and the platform's redirect back to /callback carries no
    # Authorization header of its own, so this is what proves the callback
    # is legitimate, which brand it's for, and (via `purpose`) which
    # platform it was issued for — a state minted for one platform's
    # connect flow must not be replayable against another's callback.
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "brand_id": str(brand_id),
        "purpose": f"{platform}_oauth_connect",
        "iat": now,
        "exp": now + timedelta(minutes=STATE_EXPIRES_MINUTES),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def _verify_state(state: str, platform: str) -> uuid.UUID:
    settings = get_settings()
    try:
        payload = jwt.decode(state, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state"
        ) from None

    if payload.get("purpose") != f"{platform}_oauth_connect":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")

    try:
        return uuid.UUID(payload["brand_id"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state") from None


@router.get("/brands/{brand_id}/social-accounts", response_model=list[SocialAccountRead])
def list_social_accounts(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[SocialAccount]:
    _get_org_brand(db, brand_id, current_user.org_id)
    return db.query(SocialAccount).filter(SocialAccount.brand_id == brand_id).all()


@router.get("/brands/{brand_id}/social-accounts/{account_id}", response_model=SocialAccountRead)
def get_social_account(
    brand_id: uuid.UUID,
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SocialAccount:
    _get_org_brand(db, brand_id, current_user.org_id)
    return _get_account_or_404(db, brand_id, account_id)


@router.post(
    "/brands/{brand_id}/social-accounts/linkedin/connect",
    response_model=AuthorizeUrlRead,
)
def connect_linkedin(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> AuthorizeUrlRead:
    _get_org_brand(db, brand_id, current_user.org_id)
    settings = get_settings()
    if not settings.linkedin_redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LinkedIn OAuth is not configured",
        )

    provider = get_social_oauth_provider("linkedin")
    state = _create_state(brand_id, "linkedin")
    url = provider.authorize_url(state=state, redirect_uri=settings.linkedin_redirect_uri)
    return AuthorizeUrlRead(authorize_url=url)


@router.get("/oauth/linkedin/callback", response_model=SocialAccountRead)
def linkedin_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> SocialAccount:
    brand_id = _verify_state(state, "linkedin")
    settings = get_settings()
    provider = get_social_oauth_provider("linkedin")
    tokens = provider.exchange_code(code=code, redirect_uri=settings.linkedin_redirect_uri or "")
    return _upsert_social_account(db, brand_id, SocialPlatform.LINKEDIN, tokens)


@router.post(
    "/brands/{brand_id}/social-accounts/x/connect",
    response_model=AuthorizeUrlRead,
)
def connect_x(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> AuthorizeUrlRead:
    _get_org_brand(db, brand_id, current_user.org_id)
    settings = get_settings()
    if not settings.x_redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="X OAuth is not configured",
        )

    provider = get_social_oauth_provider("x")
    state = _create_state(brand_id, "x")
    url = provider.authorize_url(state=state, redirect_uri=settings.x_redirect_uri)
    return AuthorizeUrlRead(authorize_url=url)


@router.get("/oauth/x/callback", response_model=SocialAccountRead)
def x_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> SocialAccount:
    brand_id = _verify_state(state, "x")
    settings = get_settings()
    provider = get_social_oauth_provider("x")
    # XProvider's PKCE ("plain") requires code_verifier == the code_challenge
    # sent at authorize_url time, which is `state` (see XProvider's
    # docstring) — pass it through here rather than at exchange_code's
    # default, which would raise.
    tokens = provider.exchange_code(
        code=code, redirect_uri=settings.x_redirect_uri or "", code_verifier=state
    )
    return _upsert_social_account(db, brand_id, SocialPlatform.X, tokens)


def _upsert_social_account(
    db: Session, brand_id: uuid.UUID, platform: SocialPlatform, tokens
) -> SocialAccount:
    account = (
        db.query(SocialAccount)
        .filter(SocialAccount.brand_id == brand_id, SocialAccount.platform == platform)
        .first()
    )
    if account is None:
        account = SocialAccount(brand_id=brand_id, platform=platform)
        db.add(account)

    account.external_account_id = tokens.external_account_id
    account.access_token_encrypted = encrypt_token(tokens.access_token)
    account.refresh_token_encrypted = (
        encrypt_token(tokens.refresh_token) if tokens.refresh_token else None
    )
    account.token_expires_at = tokens.expires_at
    account.scopes = tokens.scopes
    account.status = SocialAccountStatus.ACTIVE

    db.flush()
    db.refresh(account)
    return account


@router.post(
    "/brands/{brand_id}/social-accounts/{account_id}/verify",
    response_model=SocialAccountRead,
)
def verify_social_account(
    brand_id: uuid.UUID,
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> SocialAccount:
    """Calls the platform to check whether the stored token is still
    accepted, and updates `status` to match — this is what makes
    revocation on the platform's side (which isn't pushed to us) show up
    here.

    Issue #37 RBAC audit: this mutates SocialAccount.status and calls out
    to the external provider, same as every other write in this router —
    it was previously gated by get_current_user only (any authenticated
    role, including viewer), inconsistent with connect/disconnect right
    next to it. Tightened to WRITE_ROLES."""
    _get_org_brand(db, brand_id, current_user.org_id)
    account = _get_account_or_404(db, brand_id, account_id)

    if account.status == SocialAccountStatus.REVOKED or account.access_token_encrypted is None:
        return account

    if account.token_expires_at is not None and account.token_expires_at < datetime.now(timezone.utc):
        account.status = SocialAccountStatus.EXPIRED
    else:
        provider = get_social_oauth_provider(account.platform.value)
        access_token = decrypt_token(account.access_token_encrypted)
        account.status = (
            SocialAccountStatus.ACTIVE
            if provider.is_token_valid(access_token)
            else SocialAccountStatus.REVOKED
        )

    db.flush()
    db.refresh(account)
    return account


@router.delete(
    "/brands/{brand_id}/social-accounts/{account_id}",
    response_model=SocialAccountRead,
)
def disconnect_social_account(
    brand_id: uuid.UUID,
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(*WRITE_ROLES)),
) -> SocialAccount:
    # LinkedIn has no publicly documented token-revocation endpoint to call
    # here — disconnect is local: wipe the stored tokens (nothing usable is
    # left at rest) and mark the connection revoked.
    _get_org_brand(db, brand_id, current_user.org_id)
    account = _get_account_or_404(db, brand_id, account_id)

    account.access_token_encrypted = None
    account.refresh_token_encrypted = None
    account.status = SocialAccountStatus.REVOKED

    db.flush()
    db.refresh(account)
    return account
