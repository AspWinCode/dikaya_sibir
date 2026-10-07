import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { RequireAuth } from "./RequireAuth";
import { useAuthStore } from "./store";
import type { CurrentUser } from "../api/auth";

const BASE_USER: CurrentUser = {
  id: "user-1",
  email: "user@example.com",
  display_name: "Test User",
  is_active: true,
  is_superuser: false,
  totp_enabled: false,
  last_login_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  roles: [],
};

function setAuthed(user: CurrentUser) {
  useAuthStore.setState({ user, isAuthenticated: true, initializing: false });
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<RequireAuth><div>MainPage</div></RequireAuth>} />
        <Route path="/admin" element={<RequireAuth><div>AdminDashboard</div></RequireAuth>} />
        <Route path="/views" element={<RequireAuth><div>ViewEditor</div></RequireAuth>} />
      </Routes>
    </MemoryRouter>
  );
}

afterEach(() => {
  useAuthStore.setState({ user: null, isAuthenticated: false, initializing: false });
});

describe("RequireAuth — platform_admin landing redirect", () => {
  it("a platform_admin opening '/' (e.g. right after login) lands on the admin dashboard", () => {
    setAuthed({ ...BASE_USER, roles: [{ id: "platform_admin", display_name: "Platform admin" }] });
    renderAt("/");
    expect(screen.getByText("AdminDashboard")).toBeInTheDocument();
    expect(screen.queryByText("MainPage")).not.toBeInTheDocument();
  });

  it("a regular app user opening '/' stays on the normal start page, not the admin dashboard", () => {
    setAuthed({ ...BASE_USER, roles: [{ id: "app_owner", display_name: "App owner" }] });
    renderAt("/");
    expect(screen.getByText("MainPage")).toBeInTheDocument();
    expect(screen.queryByText("AdminDashboard")).not.toBeInTheDocument();
  });

  it("an already-authenticated platform_admin who opens '/' directly (e.g. on reload) still lands on the admin dashboard", () => {
    setAuthed({ ...BASE_USER, roles: [{ id: "platform_admin", display_name: "Platform admin" }] });
    renderAt("/");
    expect(screen.getByText("AdminDashboard")).toBeInTheDocument();
  });

  it("a platform_admin who also holds app-level roles still starts on the admin dashboard, not the app", () => {
    // AppMember status isn't tracked in the auth store's roles at all — this
    // test documents that holding *other* roles alongside platform_admin
    // doesn't change the landing page; app-level access remains a separate,
    // unaffected concern (see test_app_access_authorization.py backend-side).
    setAuthed({
      ...BASE_USER,
      roles: [
        { id: "platform_admin", display_name: "Platform admin" },
        { id: "app_owner", display_name: "App owner" },
      ],
    });
    renderAt("/");
    expect(screen.getByText("AdminDashboard")).toBeInTheDocument();
  });

  it("does not redirect a platform_admin away from a route they navigated to consciously", () => {
    setAuthed({ ...BASE_USER, roles: [{ id: "platform_admin", display_name: "Platform admin" }] });
    renderAt("/views");
    expect(screen.getByText("ViewEditor")).toBeInTheDocument();
  });
});
