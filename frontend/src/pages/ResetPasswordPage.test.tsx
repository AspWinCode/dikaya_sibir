import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AxiosError } from "axios";
import { apiClient } from "@/shared/api/client";
import { ResetPasswordPage } from "./ResetPasswordPage";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderWithToken(token = "valid-token") {
  return render(
    <MemoryRouter initialEntries={[`/reset-password?token=${token}`]}>
      <ResetPasswordPage />
    </MemoryRouter>
  );
}

describe("ResetPasswordPage", () => {
  it("shows an invalid-link state when there is no token in the URL", () => {
    render(
      <MemoryRouter initialEntries={["/reset-password"]}>
        <ResetPasswordPage />
      </MemoryRouter>
    );
    expect(screen.getByText(/недействительная ссылка/i)).toBeInTheDocument();
  });

  it("blocks submission client-side when passwords don't match", async () => {
    const postSpy = vi.spyOn(apiClient, "post");
    const user = userEvent.setup();
    renderWithToken();

    await user.type(screen.getByLabelText("Новый пароль"), "Aa1!aaaaaa");
    await user.type(screen.getByLabelText("Повторите пароль"), "Different1!");
    await user.click(screen.getByRole("button", { name: /сохранить пароль/i }));

    expect(await screen.findByText("Пароли не совпадают")).toBeInTheDocument();
    expect(postSpy).not.toHaveBeenCalled();
  });

  it("submits the new password and shows a success state", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue({ data: {} });
    const user = userEvent.setup();
    renderWithToken("good-token");

    await user.type(screen.getByLabelText("Новый пароль"), "Aa1!aaaaaa");
    await user.type(screen.getByLabelText("Повторите пароль"), "Aa1!aaaaaa");
    await user.click(screen.getByRole("button", { name: /сохранить пароль/i }));

    expect(await screen.findByText(/пароль успешно изменён/i)).toBeInTheDocument();
    expect(apiClient.post).toHaveBeenCalledWith("/auth/reset-password", {
      token: "good-token",
      new_password: "Aa1!aaaaaa",
    });
  });

  it("shows the backend's curated message for an expired/used token, not raw error text", async () => {
    const err = new AxiosError("Bad Request");
    err.response = {
      status: 400,
      data: { detail: "Ссылка недействительна или истекла" },
      statusText: "",
      headers: {},
      config: {} as never,
    };
    vi.spyOn(apiClient, "post").mockRejectedValue(err);
    const user = userEvent.setup();
    renderWithToken("used-token");

    await user.type(screen.getByLabelText("Новый пароль"), "Aa1!aaaaaa");
    await user.type(screen.getByLabelText("Повторите пароль"), "Aa1!aaaaaa");
    await user.click(screen.getByRole("button", { name: /сохранить пароль/i }));

    expect(await screen.findByText("Ссылка недействительна или истекла")).toBeInTheDocument();
  });

  it("never shows raw technical error text to the user", async () => {
    const err = new AxiosError("Internal Server Error");
    err.response = { status: 500, data: {}, statusText: "", headers: {}, config: {} as never };
    vi.spyOn(apiClient, "post").mockRejectedValue(err);
    const user = userEvent.setup();
    renderWithToken("any-token");

    await user.type(screen.getByLabelText("Новый пароль"), "Aa1!aaaaaa");
    await user.type(screen.getByLabelText("Повторите пароль"), "Aa1!aaaaaa");
    await user.click(screen.getByRole("button", { name: /сохранить пароль/i }));

    expect(await screen.findByText(/сервер недоступен/i)).toBeInTheDocument();
  });
});
