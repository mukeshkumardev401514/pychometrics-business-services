"""Resolve login tenant hints; credentials still authenticate against that tenant."""
import re
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from app.core.config import settings


def tenant_from_host(host: str) -> str | None:
    host = host.lower().rstrip('.')
    for domain in settings.tenant_base_domains.split(','):
        domain = domain.strip().lower().strip('.')
        if domain and host.endswith('.' + domain):
            code = host[:-(len(domain) + 1)]
            if re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,48}[a-z0-9])', code):
                return code.upper()
    return None


def login_tenant(request: Request, supplied: str | None) -> str:
    host_code = tenant_from_host(request.url.hostname or '')
    origin_code = None
    origin = request.headers.get('origin')
    if origin:
        try:
            parsed = urlsplit(origin)
            if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
                    or parsed.username or parsed.password or parsed.path
                    or parsed.query or parsed.fragment):
                raise ValueError
            origin_code = tenant_from_host(parsed.hostname)
        except ValueError:
            raise HTTPException(400, 'Invalid login origin.') from None
        if not origin_code:
            raise HTTPException(400, 'Tenant subdomain required in login origin.')
    codes = {code for code in (host_code, origin_code,
                              supplied.strip().upper() if supplied else None) if code}
    if len(codes) > 1:
        raise HTTPException(400, 'Tenant does not match login URL.')
    if not codes:
        raise HTTPException(400, 'Tenant subdomain or tenant_code required.')
    return codes.pop()
