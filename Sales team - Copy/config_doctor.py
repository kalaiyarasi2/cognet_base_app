"""Configuration Doctor for CogNet / Drive360 Platform.

Audits environment configuration against required and optional multi-tenant keys,
checking for missing credentials, fallback status, and tenant folder alignments.
"""
import sys
from pathlib import Path
from core.env_loader import load_workspace_env, get_env, tenant_env

# 1. Load workspace environment
load_workspace_env()
WORKSPACE_DIR = Path(__file__).resolve().parent

MASTER_KEYS = [
    ("MICROSOFT_TENANT_ID", True, "Azure AD Tenant ID (GUID) for App-Only Graph APIs"),
    ("MICROSOFT_CLIENT_ID", True, "Azure AD Application Client ID"),
    ("MICROSOFT_CLIENT_SECRET", True, "Azure AD Application Client Secret"),
    ("MICROSOFT_LOGIN_AUTHORITY", False, "Delegated login authority (defaults to 'common')"),
    ("SENDER_EMAIL", False, "Global sender mailbox address"),
    ("DELEGATED_SENDER_EMAIL", False, "Dedicated delegated mailbox for email sends (e.g. drivesupport)"),
    ("SYSTEM_EMAIL", False, "System sender fallback for submissions"),
    ("DEFAULT_TENANT", True, "Default tenant folder code (e.g. wcuw)"),
    ("JWT_SECRET_KEY", True, "JWT Secret Key for authentication sessions"),
    ("SUPER_ADMIN_EMAILS", False, "Comma-separated super administrator emails"),
    ("APP_BASE_URL", False, "Base URL for frontend login links in emails"),
    ("PRODUCT_NAME", False, "Brand/product title used in email communications"),
    ("ENV", False, "Environment mode ('development' or 'production')"),
]

def check_configuration():
    print("=" * 80)
    print(" CogNet / Drive360 Dynamic Configuration Doctor")
    print("=" * 80)

    has_errors = False
    print(f"\n{'KEY':<30} | {'STATUS':<10} | {'VALUE / DETAILS'}")
    print("-" * 80)

    for key, required, desc in MASTER_KEYS:
        val = get_env(key)
        if val:
            display_val = val if len(val) < 40 else val[:15] + "..." + val[-15:]
            if "SECRET" in key:
                display_val = "******** (SET)"
            print(f"{key:<30} | \033[92mSET\033[0m        | {display_val}")
        else:
            if required:
                print(f"{key:<30} | \033[91mMISSING\033[0m    | REQUIRED: {desc}")
                has_errors = True
            else:
                print(f"{key:<30} | \033[93mOPTIONAL\033[0m   | Not set ({desc})")

    # 2. Check tenant configurations
    print("\n" + "=" * 80)
    print(" Tenant Directory & Mailbox Ingestion Audit")
    print("=" * 80)
    tenants_dir = WORKSPACE_DIR / "config" / "tenants"
    if not tenants_dir.exists():
        print(f"\033[91m[ERROR]\033[0m config/tenants directory does not exist at {tenants_dir}")
        has_errors = True
    else:
        for t_dir in sorted(tenants_dir.iterdir()):
            if not t_dir.is_dir():
                continue
            t_name = t_dir.name
            t_json = (t_dir / "tenant.json").exists()
            s_json = (t_dir / "submission.json").exists()

            monitor_mail = tenant_env(t_name, "MONITOR_EMAIL", "PARTNER_POC_MONITOR_EMAIL")
            sender_mail = tenant_env(t_name, "SENDER_EMAIL", "DELEGATED_SENDER_EMAIL")

            status_str = f"tenant.json: {'OK' if t_json else 'MISSING'}, submission.json: {'OK' if s_json else 'MISSING'}"
            fallback_msg = "\033[93m(Unset - will use fallback)\033[0m"
            mail_str = f"Monitor: {monitor_mail or fallback_msg}, Sender: {sender_mail or '(global)'}"
            print(f"\n* Tenant: [{t_name.upper()}] ({t_dir.name})")
            print(f"  Files: {status_str}")
            print(f"  Email: {mail_str}")

    print("\n" + "=" * 80)
    if has_errors:
        print("\033[91m[AUDIT FAILED]\033[0m One or more required configuration keys are missing.")
        sys.exit(1)
    else:
        print("\033[92m[AUDIT PASSED]\033[0m All required platform configurations are present.")
        sys.exit(0)

if __name__ == "__main__":
    check_configuration()
