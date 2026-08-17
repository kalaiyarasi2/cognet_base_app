import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Loader2, AlertTriangle, ShieldCheck } from "lucide-react";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";

export const Route = createFileRoute("/auth/callback")({
  component: AuthCallbackPage,
});

function AuthCallbackPage() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function handleSSOCallback() {
      const params = new URLSearchParams(window.location.search);
      const code = params.get("code");
      const err = params.get("error");
      const errDesc = params.get("error_description");

      // ── Server-side redirect flow: backend already exchanged the code ──
      const ssoToken = params.get("sso_token");
      if (ssoToken) {
        const email = params.get("email") || "";
        const name = params.get("name") || "";
        const role = params.get("role") || "USER";
        const allowedModules = params.get("allowed_modules") || "ALL";
        login(
          {
            email,
            name,
            role: role as "ADMIN" | "USER",
            allowed_modules: allowedModules.includes(",") ? allowedModules.split(",") : allowedModules,
          },
          ssoToken
        );
        navigate({ to: "/" });
        return;
      }

      if (err) {
        setError(`Microsoft Sign-in error: ${errDesc || err}`);
        return;
      }

      if (!code) {
        setError("No authorization code received from Microsoft.");
        return;
      }

      try {
        const codeVerifier = sessionStorage.getItem("code_verifier") || undefined;
        const redirectUri = window.location.origin + "/auth/callback";
        const res = await api.ssoCallback(code, undefined, codeVerifier, redirectUri);
        
        // Clean up code_verifier
        sessionStorage.removeItem("code_verifier");
        
        login(
          {
            email: res.user.email,
            name: res.user.name,
            role: res.user.role as "ADMIN" | "USER",
            allowed_modules: res.user.allowed_modules,
          },
          res.token
        );
        navigate({ to: "/" });
      } catch (e: any) {
        const msg = e?.message ?? "Authentication failed.";
        setError(msg);
      }
    }

    handleSSOCallback();
  }, []);

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%)", fontFamily: "'Inter', sans-serif"
    }}>
      <div style={{
        background: "#ffffff", padding: "40px 36px", borderRadius: 16,
        maxWidth: 420, width: "100%", textAlign: "center", boxShadow: "0 20px 60px rgba(0,0,0,0.2)"
      }}>
        {error ? (
          <div>
            <div style={{
              width: 50, height: 50, borderRadius: "50%", background: "#fef2f2",
              margin: "0 auto 16px", display: "flex", alignItems: "center", justifyContent: "center"
            }}>
              <AlertTriangle size={24} style={{ color: "#ef4444" }} />
            </div>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: "#111827", margin: "0 0 8px" }}>
              Authentication Failed
            </h2>
            <p style={{ fontSize: 13, color: "#6b7280", margin: "0 0 20px", lineHeight: 1.5 }}>
              {error}
            </p>
            <button
              onClick={() => navigate({ to: "/login" })}
              style={{
                background: "#0057FF", color: "#fff", border: "none", borderRadius: 8,
                padding: "10px 20px", fontSize: 13, fontWeight: 600, cursor: "pointer"
              }}
            >
              Back to Login
            </button>
          </div>
        ) : (
          <div>
            <div style={{
              width: 50, height: 50, borderRadius: "50%", background: "#eff6ff",
              margin: "0 auto 16px", display: "flex", alignItems: "center", justifyContent: "center"
            }}>
              <Loader2 size={24} style={{ color: "#0057FF", animation: "spin 1s linear infinite" }} />
            </div>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: "#111827", margin: "0 0 6px" }}>
              Authenticating with Microsoft
            </h2>
            <p style={{ fontSize: 13, color: "#6b7280", margin: 0 }}>
              Verifying your account permissions…
            </p>
          </div>
        )}
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
