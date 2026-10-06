import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useSearchParams } from "react-router-dom";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { handlers } from "@/mocks/handlers";
import { DeployPage } from "./DeployPage";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers(...handlers));
afterAll(() => server.close());

beforeEach(() => {
  localStorage.setItem("access_token", "test-token");
});

function PreviewStub() {
  const [params] = useSearchParams();
  return <div data-testid="preview-screen">PREVIEW app={params.get("app")}</div>;
}

function renderDeployPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/deploy"]}>
        <Routes>
          <Route path="/deploy" element={<DeployPage />} />
          <Route path="/preview" element={<PreviewStub />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("DeployPage — publication", () => {
  it("navigates to the real preview screen with the active app's id instead of doing nothing", async () => {
    const user = userEvent.setup();
    renderDeployPage();

    const previewButtons = await screen.findAllByRole("button", { name: "Предпросмотр" });
    // One in the sidebar, one in the publish-section action row — both must work.
    await user.click(previewButtons[0]);

    const preview = await screen.findByTestId("preview-screen");
    expect(preview.textContent).toMatch(/^PREVIEW app=[0-9a-f-]+$/);
  });

  it("disables Опубликовать while the readiness check reports a blocking error", async () => {
    renderDeployPage();

    await waitFor(() => {
      expect(screen.getByText(/связь.*client_ref/i)).toBeInTheDocument();
    });

    const publishBtn = screen.getByRole("button", { name: /опубликовать/i });
    expect(publishBtn).toBeDisabled();
    expect(
      screen.getByText(/публикация заблокирована/i)
    ).toBeInTheDocument();
  });
});
