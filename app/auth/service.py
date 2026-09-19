from datetime import datetime, timezone

from app.core.config import settings

from app.core.security import (
    create_access_token,
    verify_password,
)
from app.db.tenant import get_tenant_connection
from app.db.tenant_resolver import resolve_tenant


class InvalidCredentialsError(Exception):
    pass


class UserInactiveError(Exception):
    pass


class UserRoleNotFoundError(Exception):
    pass


def authenticate_user(
    *,
    tenant_code: str,
    email: str,
    password: str,
):
    tenant = resolve_tenant(tenant_code)

    normalized_email = email.strip().lower()

    with get_tenant_connection(tenant) as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    u.id,
                    u.email,
                    u.password_hash,
                    u.first_name,
                    u.last_name,
                    u.status,
                    r.code
                FROM users u
                LEFT JOIN user_roles ur
                    ON ur.user_id = u.id
                LEFT JOIN roles r
                    ON r.id = ur.role_id
                WHERE LOWER(u.email) = %s
                """,
                (normalized_email,),
            )

            rows = cur.fetchall()

            if not rows:
                raise InvalidCredentialsError(
                    "Invalid email or password."
                )

            user = rows[0]

            user_id = user[0]
            user_email = user[1]
            password_hash = user[2]
            first_name = user[3]
            last_name = user[4]
            status = user[5]

            if status != "ACTIVE":
                raise UserInactiveError(
                    "User account is not active."
                )

            if not password_hash:
                raise InvalidCredentialsError(
                    "Invalid email or password."
                )

            if not verify_password(
                password,
                password_hash,
            ):
                raise InvalidCredentialsError(
                    "Invalid email or password."
                )

            roles = [
                row[6]
                for row in rows
                if row[6] is not None
            ]

            if not roles:
                raise UserRoleNotFoundError(
                    "No role assigned to user."
                )

            # Current authentication model:
            # one effective role in the JWT.
            role = roles[0]

            cur.execute(
                """
                UPDATE users
                SET
                    last_login_at = %s,
                    updated_at = %s
                WHERE id = %s
                """,
                (
                    datetime.now(timezone.utc),
                    datetime.now(timezone.utc),
                    user_id,
                ),
            )

        conn.commit()

    token = create_access_token(
        user_id=user_id,
        tenant_id=tenant.tenant_id,
        role=role,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in":
            60 * settings.jwt_access_token_expire_minutes,
        "user_id": str(user_id),
        "tenant_id": str(tenant.tenant_id),
        "tenant_code": tenant.tenant_code,
        "role": role,
        "email": user_email,
        "first_name": first_name,
        "last_name": last_name,
    }
