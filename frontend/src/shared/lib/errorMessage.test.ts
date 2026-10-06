import { describe, expect, it } from "vitest";
import { AxiosError } from "axios";
import { getFriendlyErrorMessage } from "./errorMessage";

function axiosErr(status: number, data?: unknown): AxiosError {
  const err = new AxiosError("Request failed");
  err.response = {
    status,
    data,
    statusText: "",
    headers: {},
    config: {} as never,
  };
  return err;
}

describe("getFriendlyErrorMessage", () => {
  it("returns a network message when there is no response", () => {
    const err = new AxiosError("Network Error");
    expect(getFriendlyErrorMessage(err)).toMatch(/недоступен/);
  });

  it("never leaks raw backend detail by default", () => {
    const err = axiosErr(500, { detail: "Traceback: ValueError at line 42 in records.py" });
    const message = getFriendlyErrorMessage(err);
    expect(message).not.toContain("Traceback");
    expect(message).not.toContain("records.py");
  });

  it("maps common statuses to Russian messages", () => {
    expect(getFriendlyErrorMessage(axiosErr(403))).toMatch(/прав/);
    expect(getFriendlyErrorMessage(axiosErr(404))).toMatch(/не найдена/);
    expect(getFriendlyErrorMessage(axiosErr(409))).toMatch(/изменены/);
  });

  it("falls back for non-axios errors", () => {
    expect(getFriendlyErrorMessage(new Error("boom"))).toBe(
      "Произошла ошибка. Попробуйте ещё раз."
    );
  });

  it("allows curated russian detail only when explicitly opted in", () => {
    const err = axiosErr(400, { detail: "Ссылка недействительна или истекла" });
    expect(getFriendlyErrorMessage(err, { allowedDetail: true })).toBe(
      "Ссылка недействительна или истекла"
    );
    expect(getFriendlyErrorMessage(err)).not.toBe("Ссылка недействительна или истекла");
  });
});
