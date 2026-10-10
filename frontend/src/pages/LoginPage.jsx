import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errMsg } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Sparkles } from "lucide-react";

export default function LoginPage() {
  const nav = useNavigate();
  const { refresh } = useAuth();
  const [mode, setMode] = useState("login");
  const [role, setRole] = useState("patient");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("patient@drd.demo");
  const [password, setPassword] = useState("Patient123!");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      if (mode === "login") {
        await api.post("/auth/login", { email, password });
      } else {
        await api.post("/auth/register", { name, email, password, role });
      }
      const u = await refresh();
      nav(u?.role === "doctor" ? "/doctor" : "/");
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  const googleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="drd-login-wrap">
      <div className="drd-login-card" data-testid="login-card">
        <div className="drd-login-head">
          <span className="drd-logo">
            <span className="drd-logo-d">D</span>
            <span className="drd-logo-dot" />
          </span>
          <div>
            <div className="drd-wordmark-main" style={{ fontSize: "1.25rem" }}>
              Dr.<span className="drd-wordmark-accent">D</span>
            </div>
            <small className="drd-muted">Book. Track. Relax.</small>
          </div>
        </div>

        <Tabs value={mode} onValueChange={setMode} className="w-full">
          <TabsList className="drd-tabs">
            <TabsTrigger value="login" data-testid="tab-login">Sign in</TabsTrigger>
            <TabsTrigger value="register" data-testid="tab-register">Create account</TabsTrigger>
          </TabsList>

          <TabsContent value="login" className="drd-tab-content">
            <form onSubmit={submit} className="drd-form">
              <div>
                <Label htmlFor="email-login">Email</Label>
                <Input
                  id="email-login"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  data-testid="login-email"
                />
              </div>
              <div>
                <Label htmlFor="pw-login">Password</Label>
                <Input
                  id="pw-login"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  data-testid="login-password"
                />
              </div>
              {error && <div className="drd-error" data-testid="login-error">{error}</div>}
              <Button
                type="submit"
                disabled={busy}
                className="drd-btn-primary"
                data-testid="login-submit"
              >
                {busy ? "Signing in…" : "Sign in"}
              </Button>
            </form>
          </TabsContent>

          <TabsContent value="register" className="drd-tab-content">
            <form onSubmit={submit} className="drd-form">
              <div>
                <Label>Full name</Label>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  data-testid="register-name"
                />
              </div>
              <div>
                <Label>Email</Label>
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  data-testid="register-email"
                />
              </div>
              <div>
                <Label>Password</Label>
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  data-testid="register-password"
                />
              </div>
              <div className="drd-role-toggle">
                <button
                  type="button"
                  className={role === "patient" ? "active" : ""}
                  onClick={() => setRole("patient")}
                  data-testid="role-patient"
                >
                  I'm a patient
                </button>
                <button
                  type="button"
                  className={role === "doctor" ? "active" : ""}
                  onClick={() => setRole("doctor")}
                  data-testid="role-doctor"
                >
                  I'm a doctor
                </button>
              </div>
              {error && <div className="drd-error">{error}</div>}
              <Button
                type="submit"
                disabled={busy}
                className="drd-btn-primary"
                data-testid="register-submit"
              >
                {busy ? "Creating…" : "Create account"}
              </Button>
            </form>
          </TabsContent>
        </Tabs>

        <div className="drd-login-divider"><span>or</span></div>

        <Button
          type="button"
          variant="outline"
          onClick={googleLogin}
          className="drd-btn-google"
          data-testid="google-signin"
        >
          <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
            <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.6 32.9 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3 0 5.8 1.1 7.9 3l5.7-5.7C33.9 6.2 29.2 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20c11 0 19.7-8 19.7-20 0-1.3-.1-2.4-.3-3.5z"/>
            <path fill="#FF3D00" d="M6.3 14.1l6.6 4.8C14.7 15.2 19 12 24 12c3 0 5.8 1.1 7.9 3l5.7-5.7C33.9 6.2 29.2 4 24 4 16.3 4 9.7 8.3 6.3 14.1z"/>
            <path fill="#4CAF50" d="M24 44c5.1 0 9.8-2 13.3-5.2l-6.1-5c-2 1.4-4.5 2.2-7.2 2.2-5.1 0-9.4-3-11.1-7.3l-6.5 5C9.5 39.6 16.2 44 24 44z"/>
            <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.3-2.4 4.3-4.5 5.7l6.1 5C40 36 44 30.6 44 24c0-1.3-.1-2.4-.4-3.5z"/>
          </svg>
          Continue with Google
        </Button>

        <p className="drd-dai-hint" data-testid="login-dai-hint">
          <Sparkles size={14} /> Dai can help you book or check your queue.
        </p>
        <small className="drd-muted drd-demo-hint" data-testid="demo-hint">
          Demo patient: patient@drd.demo / Patient123!<br />
          Demo doctor: doctor@drd.demo / Doctor123!
        </small>
      </div>
    </div>
  );
}
