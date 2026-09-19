"""Create the first platform account: python -m scripts.bootstrap_platform_admin."""

from getpass import getpass

import psycopg
from pydantic import EmailStr, TypeAdapter

from app.core.config import settings
from app.core.security import hash_password


def main():
    email = str(TypeAdapter(EmailStr).validate_python(
        input('Platform admin email: ').strip().lower()
    ))
    if len(email) > 255:
        raise SystemExit('Email must contain at most 255 characters.')
    first_name = input('First name: ').strip()
    if not first_name or len(first_name) > 100:
        raise SystemExit('First name must contain 1–100 characters.')
    password = getpass('Password (8–128 characters): ')
    if not 8 <= len(password) <= 128:
        raise SystemExit('Password must contain 8–128 characters.')
    if password != getpass('Confirm password: '):
        raise SystemExit('Passwords do not match.')
    password_hash = hash_password(password)
    with psycopg.connect(
        host=settings.platform_db_host,
        port=settings.platform_db_port,
        dbname=settings.platform_db_name,
        user=settings.platform_db_user,
        password=settings.platform_db_password,
        connect_timeout=10,
    ) as conn:
        # Serialize bootstrap attempts and avoid replacing an existing account.
        conn.execute('LOCK TABLE platform_users IN EXCLUSIVE MODE')
        if conn.execute('SELECT 1 FROM platform_users LIMIT 1').fetchone():
            raise SystemExit('A platform account already exists. Use platform login.')
        conn.execute(
            "INSERT INTO platform_users (email, password_hash, first_name, status) "
            "VALUES (%s, %s, %s, 'ACTIVE')",
            (email.lower(), password_hash, first_name),
        )
    print('Platform admin created. Log in using /platform/auth/login.')


if __name__ == '__main__':
    main()
