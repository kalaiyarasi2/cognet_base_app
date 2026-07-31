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

  // Admin-only guard — redirect non-admins immediately
  useEffect(() => {
    if (user && user.role !== "ADMIN") {
      navigate({ to: "/" });
    }
  }, [user]);

  // Don't render anything for non-admins while redirecting
  if (!user || user.role !== "ADMIN") {
    return null;
  }

  return (
    <div className="space-y-2">
      <UserManagement />
    </div>
  );
}

