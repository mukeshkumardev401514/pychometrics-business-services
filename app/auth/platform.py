"""Platform operators authenticate independently of tenant users."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from psycopg.rows import dict_row
from pydantic import BaseModel, EmailStr, Field, SecretStr

from app.auth.dependencies import bearer_scheme
from app.core.config import settings
from app.core.security import verify_password
from app.db.platform import get_platform_connection

router = APIRouter(prefix='/platform/auth', tags=['Platform authentication'])
AUDIENCE = 'psychometrics-platform'


@dataclass(frozen=True)
class PlatformUser:
    user_id: UUID
    email: str
    role: str = 'PLATFORM_ADMIN'


class PlatformLogin(BaseModel):
    email: EmailStr
    password: SecretStr = Field(min_length=8, max_length=128)


def get_platform_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)):
    denied = HTTPException(401, 'Valid platform authentication required.', headers={'WWW-Authenticate': 'Bearer'})
    if credentials is None or credentials.scheme.lower() != 'bearer':
        raise denied
    try:
        claims = jwt.decode(credentials.credentials, settings.jwt_secret,
                            algorithms=[settings.jwt_algorithm], audience=AUDIENCE,
                            options={'require': ['sub', 'aud', 'exp', 'iat', 'type']})
        if claims['type'] != 'platform_access':
            raise denied
        user_id = UUID(claims['sub'])
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError):
        raise denied from None
    with get_platform_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('SELECT id, email, status FROM platform_users WHERE id = %s', (user_id,))
            user = cur.fetchone()
    if not user or user['status'] != 'ACTIVE':
        raise denied
    return PlatformUser(user['id'], user['email'])


@router.post('/login')
def login(request: PlatformLogin):
    with get_platform_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('SELECT id, email, password_hash, status FROM platform_users WHERE LOWER(email) = %s',
                        (str(request.email).lower(),))
            user = cur.fetchone()
            if not user or user['status'] != 'ACTIVE' or not verify_password(request.password.get_secret_value(), user['password_hash']):
                raise HTTPException(401, 'Invalid credentials.')
            cur.execute('UPDATE platform_users SET last_login_at = NOW(), updated_at = NOW() WHERE id = %s', (user['id'],))
    now = datetime.now(timezone.utc)
    expires = settings.jwt_access_token_expire_minutes * 60
    token = jwt.encode({'sub': str(user['id']), 'aud': AUDIENCE, 'type': 'platform_access',
                        'iat': now, 'exp': now + timedelta(seconds=expires), 'jti': str(uuid4())},
                       settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {'access_token': token, 'token_type': 'bearer', 'expires_in': expires, 'role': 'PLATFORM_ADMIN', 'user_id': user['id']}


@router.get('/me')
def me(user: PlatformUser = Depends(get_platform_user)):
    return user
