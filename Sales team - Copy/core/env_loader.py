"""Central environment loading + tenant-aware lookup helpers.

Resolution order for tenant lookups: TENANT_KEY -> KEY -> fallback keys -> default.
Nothing here raises; missing values return the default so features can soft-fail.
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent


def load_workspace_env() -> None:
    """Load .env files from the known locations (first one wins, no overriding)."""
    for candidate in (
        ROOT / ".env",
        ROOT / "Gpu_server" / ".env",
        ROOT / "file-classification-" / ".env",
    ):
        if candidate.is_file():
            load_dotenv(candidate, override=False)


def get_env(*keys: str, default: str = "") -> str:
    """Return the first non-empty env value among `keys`, else `default`."""
    for k in keys:
        v = os.getenv(k)
        if v and v.strip():
            return v.strip()
    return default


def tenant_key(tenant: str | None) -> str:
    """Normalise a tenant code/folder to its env-prefix form (e.g. 'notice-manager' -> 'NOTICE_MANAGER')."""
    return (tenant or "").strip().upper().replace(" ", "_").replace("-", "_")


def tenant_env(tenant: str | None, key: str, *fallback_keys: str, default: str = "") -> str:
    """Tenant-specific value (<TENANT>_<KEY>) -> global <KEY> -> fallback keys -> default."""
    t = tenant_key(tenant)
    keys = ([f"{t}_{key}"] if t else []) + [key, *fallback_keys]
    return get_env(*keys, default=default)


def warn_missing(feature: str, *keys: str) -> None:
    """Log a clear config error; the caller disables only the affected feature."""
    log.error("[CONFIG] %s disabled: set one of %s in .env", feature, ", ".join(keys))


_GENERIC_AUTHORITIES = ("common", "organizations", "consumers")


def get_app_tenant_id(tenant: str | None = None) -> str:
    """Azure AD tenant id for app-only (client credentials) calls.

    Order: <TENANT>_MICROSOFT_TENANT_ID -> SYSTEM_MAIL_TENANT_ID -> AZURE_TENANT_ID -> MICROSOFT_TENANT_ID.
    'common' / 'organizations' / 'consumers' are rejected (not valid for client credentials).
    Returns '' when nothing valid is configured.
    """
    t = tenant_key(tenant)
    keys = ([f"{t}_MICROSOFT_TENANT_ID"] if t else []) + [
        "SYSTEM_MAIL_TENANT_ID", "AZURE_TENANT_ID", "MICROSOFT_TENANT_ID",
    ]
    for k in keys:
        v = get_env(k)
        if v and v.lower() not in _GENERIC_AUTHORITIES:
            return v
    return ""


def get_login_authority() -> str:
    """Authority segment for delegated / interactive logins (default 'common')."""
    return get_env("MICROSOFT_LOGIN_AUTHORITY", "MICROSOFT_TENANT_ID", default="common")
