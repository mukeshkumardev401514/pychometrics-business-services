from psycopg_pool import ConnectionPool

from app.core.config import settings


PLATFORM_DB_DSN = (
    f"host={settings.platform_db_host} "
    f"port={settings.platform_db_port} "
    f"dbname={settings.platform_db_name} "
    f"user={settings.platform_db_user} "
    f"password={settings.platform_db_password}"
)


platform_pool = ConnectionPool(
    conninfo=PLATFORM_DB_DSN,
    min_size=1,
    max_size=5,
    open=True,
)


def get_platform_connection():
    return platform_pool.connection()