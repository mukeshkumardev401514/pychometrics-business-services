from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    return password_hash.verify(
        plain_password,
        hashed_password,
    )


def create_access_token(
    *,
    user_id: UUID,
    tenant_id: UUID,
    role: str,
    email: str | None = None,
    doctor_id: UUID | None = None,
) -> str:

    now = datetime.now(timezone.utc)

    expires_at = now + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )

    payload = {
        "jti": str(uuid4()),
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": expires_at,
    }

    if email is not None:
        payload['email'] = email
    if role == 'DOCTOR':
        payload['doctor_id'] = str(doctor_id) if doctor_id is not None else None

    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


class TokenExpiredError(Exception):
    pass


class InvalidAccessTokenError(Exception):
    pass


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={
                "require": [
                    "sub",
                    "tenant_id",
                    "role",
                    "type",
                    "iat",
                    "exp",
                ]
            },
        )

    except ExpiredSignatureError as exc:
        raise TokenExpiredError(
            "Access token has expired."
        ) from exc

    except InvalidTokenError as exc:
        raise InvalidAccessTokenError(
            "Invalid access token."
        ) from exc

    if payload.get("type") != "access":
        raise InvalidAccessTokenError(
            "Invalid token type."
        )

    if payload.get("role") not in ("HOSPITAL_ADMIN", "DOCTOR", "PATIENT"):
        raise InvalidAccessTokenError("Invalid token role.")

    try:
        UUID(payload["sub"])
        UUID(payload["tenant_id"])
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise InvalidAccessTokenError(
            "Invalid token claims."
        ) from exc

    return payload
