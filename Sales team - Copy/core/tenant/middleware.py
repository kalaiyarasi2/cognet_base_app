from __future__ import annotations
import logging
from typing import Callable
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from core.tenant.provider import SingleTenantProvider

logger = logging.getLogger(__name__)


def validate_tenant_startup() -> None:
    """Validates single-tenant configuration on application startup."""
    provider = SingleTenantProvider.get_instance()
    tenant = provider.tenant
    if not tenant.active:
        logger.warning(f"[TENANT STARTUP WARNING] Tenant {tenant.tenant_code} (ID: {tenant.tenant_id}) is INACTIVE!")
    else:
        logger.info(
            f"[TENANT STARTUP OK] Loaded Active Tenant: {tenant.tenant_name} ({tenant.tenant_code}, ID: {tenant.tenant_id}) "
            f"with Enabled Modules: {provider.access_service.get_enabled_modules()}"
        )



def verify_module_access(module_code: str) -> None:
    """FastAPI Dependency for route-level module authorization."""
    provider = SingleTenantProvider.get_instance()
    if not provider.access_service.can_access(module_code):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Access Denied",
                "message": f"Module '{module_code.upper()}' is disabled for tenant '{provider.tenant.tenant_code}'.",
                "tenant_id": provider.tenant.tenant_id,
                "tenant_code": provider.tenant.tenant_code,
                "enabled_modules": provider.access_service.get_enabled_modules()
            }
        )


class TenantAccessMiddleware(BaseHTTPMiddleware):
    """
    Middleware intercepting sub-app routes to enforce tenant module permissions.
    - Path prefix /api/resourcing -> LOSS_RUN
    - Path prefix /api/renewal    -> RENEWAL
    - Path prefix /api/rpve       -> INVOICE
    - Path prefix /api/parity     -> SBC
    """

    ROUTE_MODULE_MAP = {
        "/api/resourcing": "LOSS_RUN",
        "/api/renewal": "RENEWAL",
        "/api/rpve": "INVOICE",
        "/api/parity": "SBC",
    }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        provider = SingleTenantProvider.get_instance()
        path = request.url.path

        for prefix, module_code in self.ROUTE_MODULE_MAP.items():
            if path == prefix or path.startswith(prefix + "/"):
                if not provider.access_service.can_access(module_code):
                    logger.warning(f"[TENANT GUARD] Denied request to {path} for disabled module {module_code}")
                    return JSONResponse(
                        status_code=403,
                        content={
                            "status": "error",
                            "error": "Access Denied",
                            "message": f"Module '{module_code}' is disabled for tenant '{provider.tenant.tenant_code}'.",
                            "tenant_id": provider.tenant.tenant_id,
                            "tenant_code": provider.tenant.tenant_code,
                            "enabled_modules": provider.access_service.get_enabled_modules()
                        }
                    )

        return await call_next(request)
