import { useEffect, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";

export default function AuthCallback() {
  const nav = useNavigate();
  const location = useLocation();
  const { setUser } = useAuth();
  const processed = useRef(false);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;
    const hash = location.hash || window.location.hash;
    const match = hash.match(/session_id=([^&]+)/);
    const sessionId = match ? decodeURIComponent(match[1]) : null;
    if (!sessionId) {
      nav("/login");
      return;
    }
    (async () => {
      try {
        const { data } = await api.post("/auth/session", { session_id: sessionId });
        setUser(data);
        window.history.replaceState(null, "", "/");
        nav(data.role === "doctor" ? "/doctor" : "/");
      } catch {
        nav("/login");
      }
    })();
  }, [location.hash, nav, setUser]);

  return (
    <div className="drd-callback" data-testid="auth-callback">
      <span className="drd-spinner" /> Signing you in…
    </div>
  );
}
