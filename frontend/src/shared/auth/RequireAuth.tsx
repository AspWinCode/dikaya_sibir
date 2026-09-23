import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "./store";

/** Gate private routes: redirect to /signin when there is no valid session. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const initializing = useAuthStore((s) => s.initializing);
  const mustChangePassword = useAuthStore((s) => s.user?.must_change_password ?? false);
  const location = useLocation();

  if (initializing) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center text-primary text-xl">
        Загрузка…
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/signin" replace state={{ from: location.pathname }} />;
  }

  if (mustChangePassword) {
    return <Navigate to="/change-password" replace />;
  }

  return <>{children}</>;
}
