from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from apps.api.auth.dependencies import CurrentUser, get_current_user
from apps.api.models.user import UserRole


def require_role(*allowed_roles: UserRole) -> Callable[..., CurrentUser]:
    """FastAPI dependency factory: Depends(require_role(UserRole.EDITOR, UserRole.ADMIN, UserRole.OWNER))
    rejects any role not in allowed_roles with 403; a missing/expired/invalid
    token is rejected with 401 by get_current_user before role is even checked."""

    def dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role.value}' is not permitted to perform this action",
            )
        return current_user

    return dependency
