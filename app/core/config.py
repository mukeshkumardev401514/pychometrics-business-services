import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    tenant_base_domains: str = os.getenv('TENANT_BASE_DOMAINS', 'localhost')

    app_name: str = os.getenv(
        "APP_NAME",
        "Psychometric Evaluation Platform",
    )

    app_env: str = os.getenv(
        "APP_ENV",
        "development",
    )

    platform_db_host: str = os.getenv(
        "PLATFORM_DB_HOST",
        "localhost",
    )

    platform_db_port: int = int(
        os.getenv("PLATFORM_DB_PORT", "5432")
    )

    platform_db_name: str = os.getenv(
        "PLATFORM_DB_NAME",
        "psychometric_platform",
    )

    platform_db_user: str = os.getenv(
        "PLATFORM_DB_USER",
        "psych_platform_app",
    )

    platform_db_password: str = os.getenv(
        "PLATFORM_DB_PASSWORD",
        "",
    )

    tenant_db_password: str = os.getenv(
        "TENANT_DB_PASSWORD",
        "",
    )

    jwt_secret: str = os.getenv(
        "JWT_SECRET",
        "",
    )

    jwt_algorithm: str = os.getenv(
        "JWT_ALGORITHM",
        "HS256",
    )

    jwt_access_token_expire_minutes: int = int(
        os.getenv(
            "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
            "30",
        )
    )


settings = Settings()


if not settings.jwt_secret:
    raise RuntimeError(
        "JWT_SECRET environment variable is required."
    )

if len(settings.jwt_secret) < 32:
    raise RuntimeError(
        "JWT_SECRET must be at least 32 characters."
    )
