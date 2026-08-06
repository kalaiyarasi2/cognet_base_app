import { useState, useEffect } from "react";
import { useAuth } from "@/lib/store";

export interface TenantInfo {
  tenant_id: number;
  tenant_code: string;
  tenant_name: string;
  active: boolean;
  enabled_modules: string[];
}

let globalTenantCache: { [code: string]: TenantInfo } = {};

export function useTenant() {
  const { user } = useAuth();

  const urlParams = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : new URLSearchParams();
  const storedTenant = typeof window !== "undefined" ? localStorage.getItem("active_tenant_code") : null;
  const isSuperAdmin = user?.role === "ADMIN" || user?.role === "SUPER_ADMIN" || (user as any)?.app_role === "ADMIN";
  const targetCode = (
    urlParams.get("tenant") ||
    urlParams.get("tenant_code") ||
    (!isSuperAdmin && user?.tenant_code ? user.tenant_code : null) ||
    storedTenant ||
    user?.tenant_code ||
    (isSuperAdmin ? "GLOBAL" : "CLIENT_A")
  ).toUpperCase();

  const cached = globalTenantCache[targetCode];

  const [tenant, setTenant] = useState<TenantInfo>(
    cached || {
      tenant_id: 1,
      tenant_code: targetCode,
      tenant_name: targetCode === "CLIENT_A" ? "ABC Company" : targetCode,
      active: true,
      enabled_modules: ["INVOICE", "SBC"],
    }
  );
  const [loading, setLoading] = useState(!cached);

  useEffect(() => {
    let isMounted = true;

    async function fetchTenantModules() {
      if (globalTenantCache[targetCode]) {
        if (isMounted) {
          setTenant(globalTenantCache[targetCode]);
          setLoading(false);
        }
        return;
      }

      try {
        const fetchUrl = `http://localhost:8000/api/modules?tenant_code=${encodeURIComponent(targetCode)}`;
        const res = await fetch(fetchUrl);
        if (res.ok) {
          const data = await res.json();
          if (data.status === "ok" && Array.isArray(data.enabled_modules)) {
            const fetchedTenant: TenantInfo = {
              tenant_id: data.tenant_id || 1,
              tenant_code: data.tenant_code || targetCode,
              tenant_name: data.tenant_name || targetCode,
              active: data.active ?? true,
              enabled_modules: data.enabled_modules.map((m: string) => m.toUpperCase()),
              email: data.email
            };
            globalTenantCache[targetCode] = fetchedTenant;
            if (isMounted) {
              setTenant(fetchedTenant);
            }
          }
        }
      } catch (err) {
        console.warn("[useTenant] Failed to fetch /api/modules:", err);
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    fetchTenantModules();

    return () => {
      isMounted = false;
    };
  }, [targetCode]);

  function isModuleEnabled(routeOrCode: string): boolean {
    const isExplicitTenantView = urlParams.has("tenant") || urlParams.has("tenant_code") || urlParams.get("view") === "tenant";
    const isAdmin = !!user?.can_manage_tenants && !isExplicitTenantView;
    if (isAdmin) return true;

    // Extract user allowed modules list if specified
    const userModulesRaw = user?.allowed_modules;
    const isUserRestricted = Boolean(userModulesRaw && userModulesRaw !== "ALL");
    let userModules: string[] = [];
    if (isUserRestricted) {
      userModules = Array.isArray(userModulesRaw)
        ? userModulesRaw.map((m: string) => m.toUpperCase())
        : (userModulesRaw as string).split(",").map((s) => s.trim().toUpperCase());
    }

    // Helper: Module is only enabled if enabled for TENANT (by Super Admin) AND allowed for USER (by Tenant Admin)
    const isAllowed = (modCode: string): boolean => {
      const tenantHas = tenant.enabled_modules && tenant.enabled_modules.includes(modCode);
      if (!tenantHas) return false;
      if (!isUserRestricted) return true;
      return userModules.includes(modCode.toUpperCase());
    };

    const cleanRoute = routeOrCode.split("?")[0];
    const key = cleanRoute.toLowerCase().replace(/^\//, "").replace(/-/g, "_");

    if (key === "drive_gpu" || key === "accord") {
      return (
        isAllowed("ACCORD") ||
        isAllowed("VENDOR_INVOICE") ||
        isAllowed("INVOICE") ||
        isAllowed("BANK_STATEMENT") ||
        isAllowed("LOSS_RUN") ||
        isAllowed("WORK_COMP")
      );
    }
    if (key === "resourcing_edge" || key === "re") {
      return isAllowed("RE");
    }
    if (key === "loss_run") {
      return isAllowed("LOSS_RUN");
    }
    if (key === "converter" || key === "invoice") {
      return isAllowed("INVOICE") || isAllowed("VENDOR_INVOICE");
    }
    if (key === "rpve") {
      return isAllowed("RPVE");
    }
    if (key === "parity_setup" || key === "sbc") {
      return isAllowed("SBC");
    }
    if (key === "classification" || key === "bank_statement") {
      return isAllowed("BANK_STATEMENT");
    }
    if (key === "renewal_process" || key === "renewal") {
      return isAllowed("RENEWAL");
    }

    // Default other workspace items (e.g. settings, about) to true
    return true;
  }

  function getPrimaryEnabledRoute(): string {
    if (tenant.enabled_modules.includes("ACCORD")) return "/drive-gpu?pipeline=WORK_COMP";
    if (tenant.enabled_modules.includes("LOSS_RUN")) return "/drive-gpu?pipeline=INSURANCE";
    if (tenant.enabled_modules.includes("BANK_STATEMENT")) return "/drive-gpu?pipeline=BANK_STATEMENT";
    if (tenant.enabled_modules.includes("INVOICE") || tenant.enabled_modules.includes("VENDOR_INVOICE")) return "/drive-gpu?pipeline=INVOICE";
    if (tenant.enabled_modules.includes("WORK_COMP")) return "/drive-gpu?pipeline=WORK_COMP";
    if (tenant.enabled_modules.includes("RPVE")) return "/rpve";
    if (tenant.enabled_modules.includes("SBC")) return "/parity-setup";
    if (tenant.enabled_modules.includes("RE")) return "/resourcing-edge";
    return "/";
  }

  return {
    tenant,
    loading,
    isModuleEnabled,
    getPrimaryEnabledRoute,
  };
}
