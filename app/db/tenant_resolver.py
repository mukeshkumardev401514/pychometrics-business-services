from dataclasses import dataclass
from uuid import UUID

from app.db.platform import platform_pool


@dataclass(frozen=True)
class TenantDatabaseConfig:
    tenant_id: UUID
    tenant_code: str
    tenant_name: str
    database_name: str
    host: str
    port: int
    username: str
    tenant_type: str


class TenantNotFoundError(Exception):
    pass


class TenantInactiveError(Exception):
    pass


class TenantDatabaseConfigNotFoundError(Exception):
    pass


def resolve_tenant(tenant_code: str) -> TenantDatabaseConfig:
    normalized_code = tenant_code.strip().upper()

    sql = """
        SELECT
            t.id,
            t.tenant_code,
            t.tenant_name,
            t.status,
            c.database_name,
            c.host,
            c.port,
            c.username,
            c.status,
            t.tenant_type
        FROM tenants t
        LEFT JOIN tenant_database_config c
            ON c.tenant_id = t.id
        WHERE t.tenant_code = %s
    """

    with platform_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (normalized_code,))
            row = cur.fetchone()

    if row is None:
        raise TenantNotFoundError(
            f"Tenant '{normalized_code}' not found."
        )

    tenant_status = row[3]

    if tenant_status != "ACTIVE":
        raise TenantInactiveError(
            f"Tenant '{normalized_code}' is not active."
        )

    if row[4] is None:
        raise TenantDatabaseConfigNotFoundError(
            f"Database configuration not found for "
            f"tenant '{normalized_code}'."
        )

    database_config_status = row[8]

    if database_config_status != "ACTIVE":
        raise TenantDatabaseConfigNotFoundError(
            f"Database configuration is not active for "
            f"tenant '{normalized_code}'."
        )

    return TenantDatabaseConfig(
        tenant_id=row[0],
        tenant_code=row[1],
        tenant_name=row[2],
        database_name=row[4],
        host=row[5],
        port=row[6],
        username=row[7],
        tenant_type=row[9],
    )

def resolve_tenant_by_id(
    tenant_id: UUID,
) -> TenantDatabaseConfig:

    sql = """
        SELECT
            t.id,
            t.tenant_code,
            t.tenant_name,
            t.status,
            c.database_name,
            c.host,
            c.port,
            c.username,
            c.status,
            t.tenant_type
        FROM tenants t
        LEFT JOIN tenant_database_config c
            ON c.tenant_id = t.id
        WHERE t.id = %s
    """

    with platform_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (tenant_id,))
            row = cur.fetchone()

    if row is None:
        raise TenantNotFoundError(
            "Tenant not found."
        )

    if row[3] != "ACTIVE":
        raise TenantInactiveError(
            "Tenant is not active."
        )

    if row[4] is None:
        raise TenantDatabaseConfigNotFoundError(
            "Tenant database configuration not found."
        )

    if row[8] != "ACTIVE":
        raise TenantDatabaseConfigNotFoundError(
            "Tenant database configuration is not active."
        )

    return TenantDatabaseConfig(
        tenant_id=row[0],
        tenant_code=row[1],
        tenant_name=row[2],
        database_name=row[4],
        host=row[5],
        port=row[6],
        username=row[7],
        tenant_type=row[9],
    )