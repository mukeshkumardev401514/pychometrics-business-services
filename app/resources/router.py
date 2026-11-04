"""Register concrete routes and concrete OpenAPI request schemas for every table."""
from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.auth.dependencies import get_current_user
from app.auth.platform import get_platform_user
from app.db.tenant_resolver import (resolve_tenant_by_id, TenantNotFoundError,
                                    TenantInactiveError, TenantDatabaseConfigNotFoundError)
from app.resources import service
from app.resources.models import CATALOG, input_model
from app.resources.policy import POLICIES, READ_ONLY

router = APIRouter()


@dataclass
class Context:
    user: object
    tenant: object = None


def tenant_context(user=Depends(get_current_user)):
    return Context(user, user.tenant)


def platform_context(user=Depends(get_platform_user)):
    return Context(user)


def maintenance_context(tenant_id: UUID, user=Depends(get_platform_user)):
    try:
        return Context(user, resolve_tenant_by_id(tenant_id))
    except TenantNotFoundError:
        raise HTTPException(404, 'Tenant not found.') from None
    except (TenantInactiveError, TenantDatabaseConfigNotFoundError):
        raise HTTPException(403, 'Tenant is not available for maintenance.') from None


def register(scope, table, prefix, dependency, maintenance):
    spec = CATALOG[scope][table]
    path = prefix + '/' + table.replace('_', '-')
    group = ('Platform' if scope == 'platform' else 'Tenant maintenance' if maintenance else 'Tenant')
    tags = [group + ': ' + table.replace('_', ' ')]
    desc = 'Source: ' + spec['source'] + '. Record key: ' + ','.join(spec['primary_key']) + '. Composite keys are comma-separated in this order. Foreign keys are immutable on PATCH. DELETE refuses existing references.'

    def listing(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), context: Context = Depends(dependency)):
        return service.execute(scope, table, 'list', context.user, limit=limit, offset=offset, maintenance=maintenance, tenant=context.tenant)

    def detail(key: str, context: Context = Depends(dependency)):
        return service.execute(scope, table, 'get', context.user, key=key, maintenance=maintenance, tenant=context.tenant)

    operations = [('GET', path, listing, 200), ('GET', path+'/{key}', detail, 200)]
    if table not in READ_ONLY:
        Create = input_model(scope, table)
        Update = input_model(scope, table, update=True)

        def create(request: Create, context: Context = Depends(dependency)):
            return service.execute(scope, table, 'create', context.user, values=request.model_dump(exclude_unset=True), maintenance=maintenance, tenant=context.tenant)

        def update(key: str, request: Update, context: Context = Depends(dependency)):
            return service.execute(scope, table, 'update', context.user, key=key, values=request.model_dump(exclude_unset=True), maintenance=maintenance, tenant=context.tenant)

        def delete(key: str, context: Context = Depends(dependency)):
            service.execute(scope, table, 'delete', context.user, key=key, maintenance=maintenance, tenant=context.tenant)
            return Response(status_code=204)

        if maintenance or POLICIES[table][1]:
            if maintenance or table not in {'doctors', 'patients', 'doctor_patients'}:
                operations.append(('POST',path,create,201))
            if Update.model_fields:
                operations.append(('PATCH',path+'/{key}',update,200))
            operations.append(('DELETE',path+'/{key}',delete,204))
    for method, url, endpoint, status in operations:
        router.add_api_route(url, endpoint, methods=[method], status_code=status, tags=tags,
                             name=f'{group} {table} {endpoint.__name__}', description=desc,
                             operation_id=f'{group.replace(" ", "_")}_{table}_{endpoint.__name__}',
                             responses={401: {'description':'JWT required'},403:{'description':'Access denied'},404:{'description':'Record not found'},409:{'description':'Duplicate or related records'},422:{'description':'Invalid values/relationships'}})


for scope, tables in CATALOG.items():
    for table in tables:
        if scope == 'platform':
            register(scope, table, '/platform/data', platform_context, True)
        else:
            register(scope, table, '/platform/tenants/{tenant_id}/data', maintenance_context, True)
            if table in POLICIES:
                register(scope, table, '/data', tenant_context, False)
