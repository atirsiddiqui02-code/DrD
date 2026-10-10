import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { Button } from "../components/ui/button";

const NAV = [
  { to: "/", label: "Home" },
  { to: "/book", label: "Patient · Book", role: "patient" },
  { to: "/queue", label: "Patient · Queue", role: "patient" },
  { to: "/doctor", label: "Doctor · Home", role: "doctor" },
  { to: "/doctor/settings", label: "Doctor · Settings", role: "doctor" },
  { to: "/reception", label: "Reception · Today", roles: ["reception", "admin"] },
  { to: "/patient360", label: "Patient 360", roles: ["doctor", "reception", "admin"] },
];

export default function TopNav() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const nav = useNavigate();
  const items = NAV.filter((n) => {
    if (!n.role && !n.roles) return true;
    if (n.role) return n.role === user?.role;
    if (n.roles) return user && n.roles.includes(user.role);
    return false;
  });

  return (
    <header className="drd-topnav">
      <Link to="/" className="drd-brand" data-testid="brand-link">
        <span className="drd-logo">
          <span className="drd-logo-d">D</span>
          <span className="drd-logo-dot" />
        </span>
        <span className="drd-wordmark">
          <span className="drd-wordmark-main">
            Dr.<span className="drd-wordmark-accent">D</span>
          </span>
          <span className="drd-wordmark-sub">with Dai ✨</span>
        </span>
        <span className="drd-preview-chip">Preview</span>
      </Link>
      <nav className="drd-nav">
        {!user && (
          <Link
            to="/login"
            data-testid="nav-login"
            className={`drd-nav-link ${location.pathname === "/login" ? "active" : ""}`}
          >
            Login
          </Link>
        )}
        {items.map((n) => (
          <Link
            key={n.to}
            to={n.to}
            data-testid={`nav-${n.label.replace(/[^a-z]/gi, "-").toLowerCase()}`}
            className={`drd-nav-link ${location.pathname === n.to ? "active" : ""}`}
          >
            {n.label}
          </Link>
        ))}
        {user && (
          <Button
            variant="ghost"
            size="sm"
            onClick={async () => {
              await logout();
              nav("/login");
            }}
            data-testid="nav-logout"
            className="drd-nav-logout"
          >
            Sign out
          </Button>
        )}
      </nav>
    </header>
  );
}
