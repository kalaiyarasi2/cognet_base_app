import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState, useEffect } from "react";
import { Mail, Loader2, AlertTriangle, Eye, EyeOff, ShieldCheck, Sparkles, KeyRound, CheckCircle2, X, ArrowRight } from "lucide-react";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import logoUrl from "../logo.png";

export const Route = createFileRoute("/login")({
  component: LoginPage,
});

function LoginPage() {
  const navigate = useNavigate();
  const { login, isAuthenticated, checkAuth } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);


  const [loginStep, setLoginStep] = useState<"email" | "password" | "setup" | "otp">("email");
  const [loginOtp, setLoginOtp] = useState("");
  const [setupPassword, setSetupPassword] = useState("");
  const [setupConfirm, setSetupConfirm] = useState("");

  // Forgot password modal state
  const [showForgotModal, setShowForgotModal] = useState(false);
  const [forgotStep, setForgotStep] = useState<1 | 2>(1);
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotOtp, setForgotOtp] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [forgotLoading, setForgotLoading] = useState(false);
  const [forgotSuccess, setForgotSuccess] = useState<string | null>(null);
  const [forgotError, setForgotError] = useState<string | null>(null);

  useEffect(() => {
    if (isAuthenticated && checkAuth()) {
      navigate({ to: "/" });
    }
  }, [isAuthenticated]);

  async function handleCheckEmail() {
    const cleanEmail = email.trim().toLowerCase();
    if (!cleanEmail) { setError("Please enter your email address."); return; }
    setLoading(true); setError(null);
    try {
      const res = await api.checkEmail(cleanEmail);
      if (res.status === "first_time_setup") {
        setLoginStep("setup");
      } else {
        setLoginStep("password");
      }
    } catch (err: any) {
      const msg: string = err?.message ?? "Failed to verify email.";
      if (msg.includes("not authorized") || msg.includes("Access Denied")) {
        setError(`Access Denied: "${cleanEmail}" is not authorized. Please contact your Administrator.`);
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleSetupAccount() {
    if (!loginOtp.trim()) { setError("Please enter the OTP."); return; }
    if (!setupPassword.trim() || setupPassword !== setupConfirm) { setError("Passwords do not match."); return; }
    setLoading(true); setError(null);
    try {
      const res = await api.setupPassword(email.trim().toLowerCase(), loginOtp.trim(), setupPassword);
      login({ ...res.user, role: res.user.role as any }, res.token);
      navigate({ to: "/" });
    } catch (err: any) {
      setError(err?.message ?? "Failed to setup account.");
    } finally {
      setLoading(false);
    }
  }

  async function handleLogin() {
    const cleanEmail = email.trim().toLowerCase();
    if (!password.trim()) { setError("Please enter your password."); return; }
    setLoading(true); setError(null);
    try {
      const res = await api.authLogin(cleanEmail, password);
      if (res.status === "otp_required") {
        setLoginStep("otp");
        return;
      }
      if (res.user && res.token) {
        login({ ...res.user, role: res.user.role as any }, res.token);
        navigate({ to: "/" });
      }
    } catch (err: any) {
      setError(err?.message ?? "Authentication failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyOtp() {
    if (!loginOtp.trim()) { setError("Please enter the OTP."); return; }
    setLoading(true); setError(null);
    try {
      const res = await api.verifyOtp(email.trim().toLowerCase(), loginOtp.trim());
      login({ ...res.user, role: res.user.role as any }, res.token);
      navigate({ to: "/" });
    } catch (err: any) {
      setError(err?.message ?? "Invalid OTP.");
    } finally {
      setLoading(false);
    }
  }

  function generateRandomString(length: number) {
    let text = "";
    const possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~";
    for (let i = 0; i < length; i++) {
        text += possible.charAt(Math.floor(Math.random() * possible.length));
    }
    return text;
  }

  async function generateCodeChallenge(codeVerifier: string) {
    const encoder = new TextEncoder();
    const data = encoder.encode(codeVerifier);
    const digest = await window.crypto.subtle.digest('SHA-256', data);
    return btoa(String.fromCharCode.apply(null, Array.from(new Uint8Array(digest))))
        .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  async function handleMicrosoftSSO() {
    const clientId = "c08eee76-3a6c-433f-8c54-b46f32e1634c";
    const tenantId = "4858c3ed-d305-48b4-80e0-0bcdbf8ff3ae";
    const backendOrigin = "http://localhost:8000";
    const redirectUri = encodeURIComponent(backendOrigin + "/api/auth/sso/callback");
    const scope = encodeURIComponent("openid profile email User.Read");

    const msUrl = `https://login.microsoftonline.com/${tenantId}/oauth2/v2.0/authorize?client_id=${clientId}&response_type=code&redirect_uri=${redirectUri}&scope=${scope}&prompt=select_account`;
    window.location.href = msUrl;
  }

  async function handleRequestForgotOtp() {
    if (!forgotEmail.trim()) {
      setForgotError("Please enter your email.");
      return;
    }
    setForgotLoading(true);
    setForgotError(null);
    try {
      const res = await api.requestOtp(forgotEmail.trim().toLowerCase());
      setForgotSuccess(res.message);
      setForgotStep(2);
    } catch (e: any) {
      setForgotError(e?.message ?? "Failed to send OTP.");
    } finally {
      setForgotLoading(false);
    }
  }

  async function handleResetPassword() {
    if (!forgotOtp.trim() || !newPassword.trim()) {
      setForgotError("Please enter both OTP and new password.");
      return;
    }
    setForgotLoading(true);
    setForgotError(null);
    setForgotSuccess(null);
    try {
      const res = await api.forgotPassword(forgotEmail.trim().toLowerCase(), forgotOtp.trim(), newPassword.trim());
      setForgotSuccess(res.message);
      setTimeout(() => {
        setEmail(forgotEmail);
        setPassword(newPassword);
        setShowForgotModal(false);
        setForgotStep(1);
        setForgotOtp("");
        setNewPassword("");
        setForgotSuccess(null);
      }, 2000);
    } catch (e: any) {
      setForgotError(e?.message ?? "Failed to reset password.");
    } finally {
      setForgotLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif" }}>
      {/* ── LEFT PANEL — Login Form ── */}
      <div style={{
        flex: "0 0 440px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        padding: "48px 48px",
        background: "#ffffff",
        boxShadow: "2px 0 24px rgba(0,0,0,0.06)",
        position: "relative",
        zIndex: 1,
      }}>
        {/* Logo */}
        <div style={{ display: "flex", alignItems: "center", marginBottom: "32px" }}>
          <img src={logoUrl} alt="DRIVE AI Logo" style={{ height: "48px", objectFit: "contain" }} />
        </div>

        <h1 style={{ fontSize: 24, fontWeight: 700, color: "#0f1117", margin: "0 0 4px 0" }}>Welcome back!</h1>
        <p style={{ fontSize: 14, color: "#6b7280", margin: "0 0 28px 0" }}>Sign in to continue to your workspace</p>

        {/* Error Banner */}
        {error && (
          <div style={{
            display: "flex", alignItems: "flex-start", gap: 10,
            padding: "12px 14px", borderRadius: 8,
            background: "#fef2f2", border: "1px solid #fecaca",
            marginBottom: 20,
          }}>
            <AlertTriangle size={15} style={{ color: "#ef4444", marginTop: 1, flexShrink: 0 }} />
            <span style={{ fontSize: 13, color: "#dc2626", lineHeight: 1.5 }}>{error}</span>
          </div>
        )}

        {/* Login Form Fields */}
        {loginStep === "email" && (
          <>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 6 }}>Email Address</label>
              <input type="email" value={email} onChange={(e) => { setEmail(e.target.value); setError(null); }} onKeyDown={(e) => e.key === "Enter" && handleCheckEmail()} placeholder="Enter your email" autoFocus autoComplete="email" style={{ width: "100%", height: 42, padding: "0 14px", border: "1.5px solid #e5e7eb", borderRadius: 8, fontSize: 14, color: "#0f1117", outline: "none", boxSizing: "border-box", background: "#fff", transition: "border-color 0.15s" }} onFocus={(e) => e.target.style.borderColor = "#0057FF"} onBlur={(e) => e.target.style.borderColor = "#e5e7eb"} />
            </div>
            <button onClick={handleCheckEmail} disabled={loading || !email.trim()} style={{ width: "100%", height: 42, background: loading || !email.trim() ? "#93b4ff" : "#0057FF", border: "none", borderRadius: 8, color: "#fff", fontSize: 14, fontWeight: 600, cursor: loading || !email.trim() ? "not-allowed" : "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, transition: "background 0.15s", marginBottom: 16 }}>{loading ? <Loader2 size={16} className="animate-spin" /> : "Continue"} {!loading && <ArrowRight size={16} />}</button>
          </>
        )}

        {loginStep === "password" && (
          <>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 6 }}>Email Address</label>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0 14px", height: 42, border: "1.5px solid #e5e7eb", borderRadius: 8, background: "#f9fafb", color: "#6b7280", fontSize: 14 }}>
                <span>{email}</span>
                <button onClick={() => setLoginStep("email")} style={{ background: "none", border: "none", color: "#0057FF", cursor: "pointer", fontSize: 13, fontWeight: 500 }}>Edit</button>
              </div>
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 6 }}>Password</label>
              <div style={{ position: "relative" }}>
                <input type={showPassword ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleLogin()} placeholder="Enter your password" autoFocus autoComplete="current-password" style={{ width: "100%", height: 42, padding: "0 40px 0 14px", border: "1.5px solid #e5e7eb", borderRadius: 8, fontSize: 14, color: "#0f1117", outline: "none", boxSizing: "border-box", background: "#fff" }} onFocus={(e) => e.target.style.borderColor = "#0057FF"} onBlur={(e) => e.target.style.borderColor = "#e5e7eb"} />
                <button type="button" onClick={() => setShowPassword(!showPassword)} style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", padding: 0, color: "#9ca3af", display: "flex", alignItems: "center" }}>{showPassword ? <EyeOff size={16} /> : <Eye size={16} />}</button>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 22 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}><input type="checkbox" checked={rememberMe} onChange={(e) => setRememberMe(e.target.checked)} style={{ width: 15, height: 15, accentColor: "#0057FF" }} /><span style={{ fontSize: 13, color: "#374151" }}>Remember me</span></label>
              <button type="button" onClick={() => { setForgotEmail(email); setShowForgotModal(true); }} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 13, color: "#0057FF", fontWeight: 500 }}>Forgot password?</button>
            </div>
            <button onClick={handleLogin} disabled={loading || !password.trim()} style={{ width: "100%", height: 42, background: loading || !password.trim() ? "#93b4ff" : "#0057FF", border: "none", borderRadius: 8, color: "#fff", fontSize: 14, fontWeight: 600, cursor: loading || !password.trim() ? "not-allowed" : "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, transition: "background 0.15s", marginBottom: 16 }}>{loading ? <Loader2 size={16} className="animate-spin" /> : "Sign In"} {!loading && <ArrowRight size={16} />}</button>
          </>
        )}

        {loginStep === "setup" && (
          <>
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, background: "#f0fdf4", color: "#166534", padding: "10px 14px", borderRadius: 8, fontSize: 13, marginBottom: 16, border: "1px solid #bbf7d0" }}>
                <CheckCircle2 size={16} /> <span>An OTP has been sent to <strong>{email}</strong>.</span>
              </div>
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 6 }}>6-Digit OTP Code</label>
              <input type="text" value={loginOtp} onChange={(e) => { setLoginOtp(e.target.value.replace(/\D/g, '').slice(0,6)); setError(null); }} placeholder="Enter 6-digit code" autoFocus style={{ width: "100%", height: 42, padding: "0 14px", border: "1.5px solid #e5e7eb", borderRadius: 8, fontSize: 16, color: "#0f1117", letterSpacing: "2px", outline: "none", boxSizing: "border-box", textAlign: "center", background: "#fff", transition: "border-color 0.15s" }} onFocus={(e) => e.target.style.borderColor = "#0057FF"} onBlur={(e) => e.target.style.borderColor = "#e5e7eb"} />
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 6 }}>Set New Password</label>
              <input type="password" value={setupPassword} onChange={(e) => setSetupPassword(e.target.value)} placeholder="Choose a secure password" style={{ width: "100%", height: 42, padding: "0 14px", border: "1.5px solid #e5e7eb", borderRadius: 8, fontSize: 14, color: "#0f1117", outline: "none", boxSizing: "border-box", background: "#fff" }} onFocus={(e) => e.target.style.borderColor = "#0057FF"} onBlur={(e) => e.target.style.borderColor = "#e5e7eb"} />
            </div>
            <div style={{ marginBottom: 22 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 6 }}>Confirm Password</label>
              <input type="password" value={setupConfirm} onChange={(e) => setSetupConfirm(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleSetupAccount()} placeholder="Re-enter your password" style={{ width: "100%", height: 42, padding: "0 14px", border: "1.5px solid #e5e7eb", borderRadius: 8, fontSize: 14, color: "#0f1117", outline: "none", boxSizing: "border-box", background: "#fff" }} onFocus={(e) => e.target.style.borderColor = "#0057FF"} onBlur={(e) => e.target.style.borderColor = "#e5e7eb"} />
            </div>
            <button onClick={handleSetupAccount} disabled={loading || loginOtp.length < 6 || !setupPassword.trim() || !setupConfirm.trim()} style={{ width: "100%", height: 42, background: loading || loginOtp.length < 6 || !setupPassword.trim() || !setupConfirm.trim() ? "#93b4ff" : "#0057FF", border: "none", borderRadius: 8, color: "#fff", fontSize: 14, fontWeight: 600, cursor: loading || loginOtp.length < 6 || !setupPassword.trim() || !setupConfirm.trim() ? "not-allowed" : "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, transition: "background 0.15s", marginBottom: 16 }}>{loading ? <Loader2 size={16} className="animate-spin" /> : "Complete Setup & Sign In"} {!loading && <ArrowRight size={16} />}</button>
          </>
        )}

        {loginStep === "otp" && (
          <div style={{ marginBottom: 22 }}>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 6 }}>6-Digit OTP Code</label>
            <input type="text" value={loginOtp} onChange={(e) => { setLoginOtp(e.target.value.replace(/\D/g, '').slice(0,6)); setError(null); }} onKeyDown={(e) => e.key === "Enter" && handleVerifyOtp()} placeholder="Enter 6-digit code" autoFocus style={{ width: "100%", height: 42, padding: "0 14px", border: "1.5px solid #e5e7eb", borderRadius: 8, fontSize: 18, color: "#0f1117", letterSpacing: "4px", outline: "none", boxSizing: "border-box", textAlign: "center", background: "#fff", transition: "border-color 0.15s" }} onFocus={(e) => e.target.style.borderColor = "#0057FF"} onBlur={(e) => e.target.style.borderColor = "#e5e7eb"} />
            <button onClick={handleVerifyOtp} disabled={loading || loginOtp.length < 6} style={{ width: "100%", height: 42, background: loading || loginOtp.length < 6 ? "#93b4ff" : "#0057FF", border: "none", borderRadius: 8, color: "#fff", fontSize: 14, fontWeight: 600, cursor: loading || loginOtp.length < 6 ? "not-allowed" : "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, transition: "background 0.15s", marginTop: 22, marginBottom: 16 }}>{loading ? <Loader2 size={16} className="animate-spin" /> : "Verify & Continue"}</button>
          </div>
        )}

        {/* Divider */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
          <div style={{ flex: 1, height: 1, background: "#e5e7eb" }} />
          <span style={{ fontSize: 12, color: "#9ca3af" }}>or</span>
          <div style={{ flex: 1, height: 1, background: "#e5e7eb" }} />
        </div>

        {/* Sign in with Microsoft (Real OAuth) */}
        <button
          id="login-microsoft-sso-btn"
          onClick={handleMicrosoftSSO}
          style={{
            width: "100%", height: 42,
            background: "#fff", border: "1.5px solid #e5e7eb", borderRadius: 8,
            color: "#374151", fontSize: 13, fontWeight: 600,
            cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
            marginBottom: 14, transition: "border-color 0.15s, background 0.15s",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "#f9fafb")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "#fff")}
        >
          <svg width="18" height="18" viewBox="0 0 21 21" fill="none">
            <rect x="1" y="1" width="9" height="9" fill="#f25022" />
            <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
            <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
            <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
          </svg>
          Sign in with Microsoft
        </button>

      </div>

      {/* ── RIGHT PANEL — Branding ── */}
      <div style={{
        flex: 1,
        background: "linear-gradient(135deg, #f0f6ff 0%, #e8f0fe 50%, #f4f0ff 100%)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "60px 48px",
        position: "relative",
        overflow: "hidden",
      }}>
        <div style={{ textAlign: "center", maxWidth: 480, marginBottom: 48 }}>
          <h2 style={{ fontSize: 36, fontWeight: 800, color: "#0f1117", lineHeight: 1.2, margin: "0 0 8px 0" }}>
            Your inbox,
          </h2>
          <h2 style={{ fontSize: 36, fontWeight: 800, color: "#0057FF", lineHeight: 1.2, margin: "0 0 20px 0" }}>
            auto-piloted.
          </h2>
          <p style={{ fontSize: 15, color: "#6b7280", lineHeight: 1.7, margin: 0 }}>
            CogNet automates email ingestion, classifies attachments, extracts data, and delivers structured outputs — all in one place.
          </p>
        </div>

        {/* Dashboard illustration card */}
        <div style={{ position: "relative", width: "100%", maxWidth: 420 }}>
          <div style={{
            background: "#fff", borderRadius: 16,
            boxShadow: "0 20px 60px rgba(0,87,255,0.12), 0 4px 16px rgba(0,0,0,0.06)",
            padding: "20px", marginBottom: 16,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 14 }}>
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#fecaca" }} />
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#fde68a" }} />
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#a7f3d0" }} />
              <div style={{ flex: 1, height: 8, background: "#f3f4f6", borderRadius: 4, marginLeft: 8 }} />
            </div>
            {[
              { label: "Invoice – BCBS Q2 2026.pdf", tag: "Invoice", color: "#dbeafe", tagColor: "#2563eb" },
              { label: "Employee Census – Aetna.xlsx", tag: "Census", color: "#d1fae5", tagColor: "#059669" },
              { label: "SBC Benefit Plan 2026.pdf", tag: "SBC", color: "#ede9fe", tagColor: "#7c3aed" },
              { label: "MED Renewal Notice.pdf", tag: "Renewal", color: "#fef3c7", tagColor: "#d97706" },
            ].map((row, i) => (
              <div key={i} style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                padding: "8px 10px", borderRadius: 8, marginBottom: 6,
                background: "#f9fafb", border: "1px solid #f3f4f6",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{ width: 28, height: 28, borderRadius: 6, background: row.color, flexShrink: 0 }} />
                  <span style={{ fontSize: 12, color: "#374151", fontWeight: 500 }}>{row.label}</span>
                </div>
                <span style={{
                  fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 20,
                  background: row.color, color: row.tagColor, whiteSpace: "nowrap",
                }}>
                  {row.tag}
                </span>
              </div>
            ))}
          </div>

          <div style={{ display: "flex", gap: 12 }}>
            {[
              { value: "98.4%", label: "Classification accuracy", color: "#0057FF" },
              { value: "2.1s", label: "Avg. processing time", color: "#7c3aed" },
              { value: "12k+", label: "Documents processed", color: "#059669" },
            ].map((stat, i) => (
              <div key={i} style={{
                flex: 1, background: "#fff", borderRadius: 12, padding: "14px 12px", textAlign: "center",
                boxShadow: "0 4px 16px rgba(0,0,0,0.06)", border: "1px solid #f3f4f6",
              }}>
                <div style={{ fontSize: 18, fontWeight: 800, color: stat.color, marginBottom: 2 }}>{stat.value}</div>
                <div style={{ fontSize: 10, color: "#9ca3af", fontWeight: 500 }}>{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── FORGOT PASSWORD MODAL ── */}
      {showForgotModal && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.6)", backdropFilter: "blur(4px)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: 16
        }}>
          <div style={{
            background: "#ffffff", width: "100%", maxWidth: 400, borderRadius: 16,
            padding: "28px 28px", boxShadow: "0 25px 50px -12px rgba(0,0,0,0.25)", position: "relative"
          }}>
            <button
              onClick={() => setShowForgotModal(false)}
              style={{
                position: "absolute", right: 16, top: 16, background: "none", border: "none",
                cursor: "pointer", color: "#9ca3af"
              }}
            >
              <X size={18} />
            </button>

            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
              <div style={{ width: 36, height: 36, borderRadius: 8, background: "#eff6ff", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <KeyRound size={18} style={{ color: "#0057FF" }} />
              </div>
              <div>
                <h3 style={{ fontSize: 16, fontWeight: 700, color: "#111827", margin: 0 }}>Reset Password</h3>
                <p style={{ fontSize: 12, color: "#6b7280", margin: 0 }}>Update your account credentials</p>
              </div>
            </div>

            {forgotSuccess && (
              <div style={{
                display: "flex", alignItems: "center", gap: 8, padding: "10px 12px", borderRadius: 8,
                background: "#f0fdf4", border: "1px solid #bbf7d0", color: "#16a34a", fontSize: 13, marginBottom: 14
              }}>
                <CheckCircle2 size={16} />
                <span>{forgotSuccess}</span>
              </div>
            )}

            {forgotError && (
              <div style={{
                display: "flex", alignItems: "center", gap: 8, padding: "10px 12px", borderRadius: 8,
                background: "#fef2f2", border: "1px solid #fecaca", color: "#dc2626", fontSize: 13, marginBottom: 14
              }}>
                <AlertTriangle size={16} />
                <span>{forgotError}</span>
              </div>
            )}

            {forgotStep === 1 ? (
              <>
                <div style={{ marginBottom: 20 }}>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 6 }}>
                    Work Email
                  </label>
                  <input
                    type="email"
                    value={forgotEmail}
                    onChange={(e) => setForgotEmail(e.target.value)}
                    placeholder="you@company.com"
                    style={{
                      width: "100%", height: 38, padding: "0 12px", borderRadius: 8,
                      border: "1.5px solid #e5e7eb", fontSize: 13, outline: "none", boxSizing: "border-box"
                    }}
                  />
                </div>
                <button
                  onClick={handleRequestForgotOtp}
                  disabled={forgotLoading || !forgotEmail.trim()}
                  style={{
                    width: "100%", height: 38, background: forgotLoading || !forgotEmail.trim() ? "#9ca3af" : "#0057FF",
                    color: "#fff", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600,
                    cursor: forgotLoading || !forgotEmail.trim() ? "not-allowed" : "pointer",
                    display: "flex", alignItems: "center", justifyContent: "center", gap: 8
                  }}
                >
                  {forgotLoading ? <Loader2 size={15} className="animate-spin" /> : "Send OTP"}
                </button>
              </>
            ) : (
              <>
                <div style={{ marginBottom: 14 }}>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 6 }}>
                    OTP Code
                  </label>
                  <input
                    type="text"
                    value={forgotOtp}
                    onChange={(e) => setForgotOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    placeholder="6-digit code"
                    style={{
                      width: "100%", height: 38, padding: "0 12px", borderRadius: 8,
                      border: "1.5px solid #e5e7eb", fontSize: 13, outline: "none", boxSizing: "border-box", letterSpacing: "2px"
                    }}
                  />
                </div>
                <div style={{ marginBottom: 20 }}>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 6 }}>
                    New Password
                  </label>
                  <input
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="Enter new password"
                    style={{
                      width: "100%", height: 38, padding: "0 12px", borderRadius: 8,
                      border: "1.5px solid #e5e7eb", fontSize: 13, outline: "none", boxSizing: "border-box"
                    }}
                  />
                </div>
                <button
                  onClick={handleResetPassword}
                  disabled={forgotLoading || !forgotOtp.trim() || !newPassword.trim()}
                  style={{
                    width: "100%", height: 38, background: forgotLoading || !forgotOtp.trim() || !newPassword.trim() ? "#9ca3af" : "#0057FF",
                    color: "#fff", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600,
                    cursor: forgotLoading || !forgotOtp.trim() || !newPassword.trim() ? "not-allowed" : "pointer",
                    display: "flex", alignItems: "center", justifyContent: "center", gap: 8
                  }}
                >
                  {forgotLoading ? <Loader2 size={15} className="animate-spin" /> : "Verify & Reset Password"}
                </button>
              </>
            )}
          </div>
        </div>
      )}

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        @keyframes spin { to { transform: rotate(360deg); } }
        * { box-sizing: border-box; }
      `}</style>
    </div>
  );
}
