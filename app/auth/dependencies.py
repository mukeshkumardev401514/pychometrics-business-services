from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from app.core.security import (
    InvalidAccessTokenError,
    TokenExpiredError,
    decode_access_token,
)
from app.db.tenant import get_tenant_connection
from app.db.tenant_resolver import (
    TenantDatabaseConfig,
    TenantDatabaseConfigNotFoundError,
    TenantInactiveError,
    TenantNotFoundError,
    resolve_tenant_by_id,
)


bearer_scheme = HTTPBearer(
    auto_error=False,
)


@dataclass(frozen=True)
class CurrentUser:
    user_id: UUID
    tenant_id: UUID
    tenant_code: str
    email: str
    first_name: str
    last_name: str | None
    role: str
    tenant: TenantDatabaseConfig



def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
) -> CurrentUser:

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    try:
        payload = decode_access_token(
            credentials.credentials
        )

    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token expired.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    except InvalidAccessTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    user_id = UUID(payload["sub"])
    tenant_id = UUID(payload["tenant_id"])
    token_role = payload["role"]

    try:
        tenant = resolve_tenant_by_id(
            tenant_id
        )

    except (
        TenantNotFoundError,
        TenantInactiveError,
        TenantDatabaseConfigNotFoundError,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access denied.",
        )

    with get_tenant_connection(tenant) as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    u.id,
                    u.email,
                    u.first_name,
                    u.last_name,
                    u.status,
                    r.code
                FROM users u
                JOIN user_roles ur
                    ON ur.user_id = u.id
                JOIN roles r
                    ON r.id = ur.role_id
                WHERE u.id = %s
                  AND r.code = %s
                """,
                (
                    user_id,
                    token_role,
                ),
            )

            row = cur.fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User authentication is no longer valid.",
        )

    if row[4] != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active.",
        )

    return CurrentUser(
        user_id=row[0],
        tenant_id=tenant.tenant_id,
        tenant_code=tenant.tenant_code,
        email=row[1],
        first_name=row[2],
        last_name=row[3],
        role=row[5],
        tenant=tenant,
    )


def require_permission(permission_code: str):

    def permission_dependency(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:

        with get_tenant_connection(current_user.tenant) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM user_roles ur
                    JOIN roles r ON r.id = ur.role_id
                    JOIN role_permissions rp
                        ON rp.role_id = ur.role_id
                    JOIN permissions p
                        ON p.id = rp.permission_id
                    WHERE ur.user_id = %s
                      AND p.code = %s
                      AND r.code = %s
                    LIMIT 1
                    """,
                    (
                        current_user.user_id,
                        permission_code,
                        current_user.role,
                    ),
                )

                permission_exists = cur.fetchone()

        if permission_exists is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied.",
            )

        return current_user

    return permission_dependency
