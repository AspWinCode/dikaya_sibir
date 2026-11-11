import { describe, expect, it } from "vitest";
import { titleForPath } from "./PageTitle";

describe("titleForPath", () => {
  it("names known pages and appends the brand", () => {
    expect(titleForPath("/signin")).toBe("Вход — Лесовик");
    expect(titleForPath("/deploy/")).toBe("Публикация — Лесовик");
    expect(titleForPath("/")).toBe("Проекты — Лесовик");
  });
  it("handles parameterised routes", () => {
    expect(titleForPath("/invite/abc123")).toBe("Приглашение — Лесовик");
  });
  it("falls back to the brand for unknown or landing pages", () => {
    expect(titleForPath("/landing")).toBe("Лесовик");
    expect(titleForPath("/nope")).toBe("Лесовик");
  });
});
