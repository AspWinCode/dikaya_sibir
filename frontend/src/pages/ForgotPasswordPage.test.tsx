import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AxiosError } from "axios";
import { apiClient } from "@/shared/api/client";
import { ForgotPasswordPage } from "./ForgotPasswordPage";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderPage() {
  return render(
    <MemoryRouter>
      <ForgotPasswordPage />
    </MemoryRouter>
  );
}

describe("ForgotPasswordPage", () => {
  it("shows a neutral success message regardless of whether the account exists", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue({ data: {} });
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText("Почта"), "someone@example.com");
    await user.click(screen.getByRole("button", { name: /отправить ссылку/i }));

    await waitFor(() =>
      expect(
        screen.getByText(/если аккаунт с этим адресом существует/i)
      ).toBeInTheDocument()
    );
    expect(postSpy).toHaveBeenCalledWith("/auth/forgot-password", {
      email: "someone@example.com",
    });
  });

  it("still shows the same neutral success message when the backend 404s (no user enumeration)", async () => {
    const err = new AxiosError("Not Found");
    err.response = { status: 404, data: {}, statusText: "", headers: {}, config: {} as never };
    vi.spyOn(apiClient, "post").mockRejectedValue(err);
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText("Почта"), "nobody@example.com");
    await user.click(screen.getByRole("button", { name: /отправить ссылку/i }));

    await waitFor(() =>
      expect(
        screen.getByText(/если аккаунт с этим адресом существует/i)
      ).toBeInTheDocument()
    );
  });

  it("shows a server-down message only for a genuine network failure", async () => {
    const err = new AxiosError("Network Error");
    vi.spyOn(apiClient, "post").mockRejectedValue(err);
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText("Почта"), "someone@example.com");
    await user.click(screen.getByRole("button", { name: /отправить ссылку/i }));

    await waitFor(() => expect(screen.getByText("Сервер недоступен")).toBeInTheDocument());
  });
});
