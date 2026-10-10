import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./lib/auth";
import { Toaster } from "./components/ui/sonner";
import TopNav from "./components/TopNav";
import DaiBubble from "./components/DaiBubble";
import LoginPage from "./pages/LoginPage";
import AuthCallback from "./pages/AuthCallback";
import PatientHome from "./pages/PatientHome";
import PatientBook from "./pages/PatientBook";
import PatientQueue from "./pages/PatientQueue";
import DoctorHome from "./pages/DoctorHome";
import DoctorSettings from "./pages/DoctorSettings";
import ReceptionDashboard from "./pages/ReceptionDashboard";
import Patient360 from "./pages/Patient360";
import "./App.css";

function RequireAuth({ children, role, roles }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="drd-loading">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (role && user.role !== role) return <Navigate to="/" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;
  return children;
}

function HomeRouter() {
  const { user, loading } = useAuth();
  if (loading) return <div className="drd-loading">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === "doctor") return <DoctorHome />;
  if (user.role === "reception" || user.role === "admin") return <Navigate to="/reception" replace />;
  return <PatientHome />;
}

function AppRoutes() {
  const location = useLocation();
  const { user } = useAuth();

  // Google OAuth callback: detect synchronously
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }

  return (
    <div className="drd-shell">
      <TopNav />
      <main className="drd-main">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<HomeRouter />} />
          <Route
            path="/book"
            element={
              <RequireAuth role="patient">
                <PatientBook />
              </RequireAuth>
            }
          />
          <Route
            path="/book/:doctorId"
            element={
              <RequireAuth role="patient">
                <PatientBook />
              </RequireAuth>
            }
          />
          <Route
            path="/queue"
            element={
              <RequireAuth role="patient">
                <PatientQueue />
              </RequireAuth>
            }
          />
          <Route
            path="/doctor"
            element={
              <RequireAuth role="doctor">
                <DoctorHome />
              </RequireAuth>
            }
          />
          <Route
            path="/doctor/settings"
            element={
              <RequireAuth role="doctor">
                <DoctorSettings />
              </RequireAuth>
            }
          />
          <Route
            path="/reception"
            element={
              <RequireAuth roles={["reception", "admin"]}>
                <ReceptionDashboard />
              </RequireAuth>
            }
          />
          <Route
            path="/patient360"
            element={
              <RequireAuth roles={["doctor", "reception", "admin"]}>
                <Patient360 />
              </RequireAuth>
            }
          />
          <Route
            path="/patient360/:patientId"
            element={
              <RequireAuth roles={["doctor", "reception", "admin"]}>
                <Patient360 />
              </RequireAuth>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      {user && <DaiBubble />}
      <Toaster />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
