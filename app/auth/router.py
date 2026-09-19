from fastapi import APIRouter, Depends, HTTPException, Request, status
from app.auth.tenant_host import login_tenant

from app.auth.dependencies import CurrentUser, get_current_user
from app.auth.schemas import (
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
)
from app.auth.service import (
    InvalidCredentialsError,
    UserInactiveError,
    UserRoleNotFoundError,
    authenticate_user,
)
from app.db.tenant_resolver import (
    TenantDatabaseConfigNotFoundError,
    TenantInactiveError,
    TenantNotFoundError,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/login",
    response_model=LoginResponse,
)
def login(request: LoginRequest, http_request: Request):
    tenant_code = login_tenant(http_request, request.tenant_code)
    try:
        return authenticate_user(
            tenant_code=tenant_code,
            email=request.email,
            password=request.password,
        )

    except (
        InvalidCredentialsError,
        TenantNotFoundError,
    ):
        # Do not expose whether tenant/user exists.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    except TenantInactiveError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is not active.",
        )

    except UserInactiveError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active.",
        )

    except UserRoleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not authorized.",
        )

    except TenantDatabaseConfigNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tenant service unavailable.",
        )


@router.get(
    "/me",
    response_model=CurrentUserResponse,
)
def get_me(
    current_user: CurrentUser = Depends(get_current_user),
):
    return {
        "user_id": str(current_user.user_id),
        "tenant_id": str(current_user.tenant_id),
        "tenant_code": current_user.tenant_code,
        "email": current_user.email,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "role": current_user.role,
    }
