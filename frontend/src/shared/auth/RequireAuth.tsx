import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "./store";

/** Gate private routes: redirect to /signin when there is no valid session. */
export function RequireAuth({
  children,
  roles,
}: {
  children: ReactNode;
  /** If set, the user must hold at least one of these roles; otherwise they
   * are sent back to "/". Backend still enforces access — this just stops the
   * UI shell of a restricted page opening for an account that can't use it. */
  roles?: string[];
}) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const initializing = useAuthStore((s) => s.initializing);
  const mustChangePassword = useAuthStore((s) => s.user?.must_change_password ?? false);
  const isPlatformAdmin = useAuthStore(
    (s) => s.user?.roles.some((r) => r.id === "platform_admin") ?? false
  );
  const userRoleIds = useAuthStore((s) => s.user?.roles.map((r) => r.id).join(",") ?? "");
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

  if (roles && !roles.some((r) => userRoleIds.split(",").includes(r))) {
    return <Navigate to="/" replace />;
  }

  // platform_admin's landing page is the platform admin dashboard, not the
  // app list (ТЗ: no automatic app-level access this way — AppMember is
  // still required to open a specific app/editor/runtime). This only
  // redirects away from "/" itself, so the admin can still navigate
  // elsewhere (e.g. "Приложения" in the dashboard) once there. Centralized
  // here (not just in SignInPage's post-login navigate) so it also applies
  // on reload and on a direct visit to "/".
  if (isPlatformAdmin && location.pathname === "/") {
    return <Navigate to="/admin" replace />;
  }

  return <>{children}</>;
}
