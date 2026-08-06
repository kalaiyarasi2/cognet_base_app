import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { UserManagement } from "@/components/UserManagement";
import { useAuth } from "@/lib/store";

export const Route = createFileRoute("/access")({
  component: AccessPage,
});

function AccessPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  // Admin/Tenant-Admin guard — redirect unauthorized users immediately
  useEffect(() => {
    if (user && user.role !== "ADMIN" && user.role !== "TENANT_ADMIN" && !user.can_manage_users) {
      navigate({ to: "/" });
    }
  }, [user]);

  // Don't render anything for unauthorized users while redirecting
  if (!user || (user.role !== "ADMIN" && user.role !== "TENANT_ADMIN" && !user.can_manage_users)) {
    return null;
  }

  return (
    <div className="space-y-2">
      <UserManagement />
    </div>
  );
}

