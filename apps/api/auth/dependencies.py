from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from apps.api.auth.jwt import decode_access_token
from apps.api.models.user import UserRole

security = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    user_id: str
    org_id: str
    role: UserRole


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser:
    if credentials is None:
        # HTTPBearer's default auto_error raises 403 for a missing token,
        # not 401 — auto_error=False + this check keeps missing/expired/
        # invalid tokens all consistently 401.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from None

    try:
        role = UserRole(payload["role"])
        return CurrentUser(
            user_id=payload["sub"], org_id=payload["org_id"], role=role
        )
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from None
