import { AxiosError, type AxiosResponse } from "axios";
import { describe, expect, it } from "vitest";
import { orgCreateErrorMessage, slugify, validateOrgForm } from "./orgForm";

function apiError(status: number, data: unknown) {
  return new AxiosError("x", "ERR", undefined, undefined, { status, data } as AxiosResponse);
}

describe("slugify", () => {
  it("transliterates a Russian company name into a valid ID", () => {
    expect(slugify("ООО Ромашка №1")).toBe("ooo-romashka-1");
    expect(slugify("  Дикая Сибирь  ")).toBe("dikaya-sibir");
    expect(slugify("Щёлково_Групп")).toBe("schelkovo_grupp");
  });
  it("keeps already-valid ids and drops junk", () => {
    expect(slugify("my-company_2")).toBe("my-company_2");
    expect(slugify("!!!")).toBe("");
  });
});

describe("validateOrgForm", () => {
  const ok = {
    display_name: "ООО Ромашка",
    slug: "romashka",
    admin_email: "boss@romashka.ru",
    admin_display_name: "Иван Петров",
    admin_password: "correct-horse-1",
  };
  it("accepts a valid form", () => {
    expect(validateOrgForm(ok)).toEqual({});
  });
  it("points at each bad field", () => {
    const e = validateOrgForm({ ...ok, slug: "Ромашка", admin_email: "boss", admin_password: "short" });
    expect(Object.keys(e).sort()).toEqual(["admin_email", "admin_password", "slug"]);
  });
});

describe("orgCreateErrorMessage", () => {
  it("explains a taken slug / email", () => {
    expect(orgCreateErrorMessage(apiError(409, { detail: "Slug already taken: x" }))).toMatch(/ID \(slug\)/);
    expect(orgCreateErrorMessage(apiError(409, { detail: "Email already registered: a@b.c" }))).toMatch(/почтой/);
  });
  it("reads the per-field list from the RFC 7807 `errors` the API really returns", () => {
    const msg = orgCreateErrorMessage(
      apiError(422, {
        detail: "Request body or query parameters failed validation.",
        errors: [{ loc: ["body", "slug"] }, { loc: ["body", "admin_email"] }],
      }),
    );
    expect(msg).toBe("Проверьте поля: ID (slug), Email администратора.");
  });
  it("names the fields a 422 complains about", () => {
    const msg = orgCreateErrorMessage(
      apiError(422, { detail: [{ loc: ["body", "slug"] }, { loc: ["body", "admin_password"] }] }),
    );
    expect(msg).toContain("ID (slug)");
    expect(msg).toContain("Пароль администратора");
  });
});
