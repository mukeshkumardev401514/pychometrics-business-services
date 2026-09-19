from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import re

from app.core.config import settings
from app.db.platform import platform_pool
from app.db.tenant import close_all_tenant_pools


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

    close_all_tenant_pools()
    platform_pool.close()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)

tenant_domains = '|'.join(re.escape(domain.strip().strip('.'))
                          for domain in settings.tenant_base_domains.split(',') if domain.strip())
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=rf'https?://[a-z0-9](?:[a-z0-9-]{{0,48}}[a-z0-9])\.(?:{tenant_domains})(?::[0-9]+)?',
    allow_methods=['GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS'],
    allow_headers=['Authorization', 'Content-Type'],
)

from app.auth.router import router as auth_router

app.include_router(auth_router)

from app.doctors.router import router as doctors_router

app.include_router(doctors_router)

from app.patients.router import router as patients_router

app.include_router(patients_router)


@app.get("/health")
def health():
    return {
        "status": "UP",
        "application": settings.app_name,
        "environment": settings.app_env,
    }


from app.auth.platform import router as platform_auth_router
from app.resources.router import router as resources_router

app.include_router(platform_auth_router)
app.include_router(resources_router)
