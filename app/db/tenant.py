from threading import Lock

from psycopg_pool import ConnectionPool

from app.core.config import settings
from app.db.tenant_resolver import TenantDatabaseConfig


_tenant_pools: dict[str, ConnectionPool] = {}
_pool_lock = Lock()


def _build_tenant_dsn(
    tenant: TenantDatabaseConfig,
) -> str:
    return (
        f"host={tenant.host} "
        f"port={tenant.port} "
        f"dbname={tenant.database_name} "
        f"user={tenant.username} "
        f"password={settings.tenant_db_password}"
    )


def get_tenant_pool(
    tenant: TenantDatabaseConfig,
) -> ConnectionPool:

    pool_key = str(tenant.tenant_id)

    existing_pool = _tenant_pools.get(pool_key)

    if existing_pool is not None:
        return existing_pool

    with _pool_lock:

        # Double check after acquiring lock
        existing_pool = _tenant_pools.get(pool_key)

        if existing_pool is not None:
            return existing_pool

        pool = ConnectionPool(
            conninfo=_build_tenant_dsn(tenant),
            min_size=1,
            max_size=5,
            open=True,
            name=f"tenant-{tenant.tenant_code.lower()}",
        )

        _tenant_pools[pool_key] = pool

        return pool


def get_tenant_connection(
    tenant: TenantDatabaseConfig,
):
    pool = get_tenant_pool(tenant)
    return pool.connection()


def close_all_tenant_pools():
    with _pool_lock:
        for pool in _tenant_pools.values():
            pool.close()

        _tenant_pools.clear()