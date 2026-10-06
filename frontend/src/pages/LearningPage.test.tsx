import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { handlers } from "@/mocks/handlers";
import { useAuthStore } from "@/shared/auth/store";
import type { CurrentUser } from "@/shared/api/auth";
import { LearningPage } from "./LearningPage";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers(...handlers));
afterAll(() => server.close());

function baseUser(roles: CurrentUser["roles"]): CurrentUser {
  return {
    id: "u1",
    email: "u@example.com",
    display_name: "Tester",
    is_active: true,
    is_superuser: false,
    totp_enabled: false,
    last_login_at: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    roles,
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <LearningPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("LearningPage", () => {
  beforeEach(() => {
    localStorage.setItem("access_token", "test-token");
  });

  it("renders the next-steps and materials content from the Knowledge Base, not hardcoded TSX", async () => {
    useAuthStore.setState({ user: baseUser([]) });
    renderPage();

    // From the "Следующие шаги" KB fixture — proves these came from data.
    expect(await screen.findByText("Изучите приложение")).toBeInTheDocument();
    expect(await screen.findByText("Выберите тему")).toBeInTheDocument();
    // From the "Обучение" KB fixture.
    expect(await screen.findByText("С чего начать работу с приложением")).toBeInTheDocument();
  });

  it("hides admin controls from a user without the platform_admin role", async () => {
    useAuthStore.setState({ user: baseUser([]) });
    renderPage();

    await screen.findByText("Изучите приложение");
    expect(screen.queryByText("+ Добавить шаг")).not.toBeInTheDocument();
    expect(screen.queryByText("+ Добавить материал")).not.toBeInTheDocument();
  });

  it("shows admin controls for a platform_admin", async () => {
    useAuthStore.setState({
      user: baseUser([{ id: "platform_admin", display_name: "Platform Admin" }]),
    });
    renderPage();

    await screen.findByText("Изучите приложение");
    expect(screen.getByText("+ Добавить шаг")).toBeInTheDocument();
    expect(screen.getByText("+ Добавить материал")).toBeInTheDocument();
  });
});
