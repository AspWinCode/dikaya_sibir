import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CreateOrgDialog } from "./AdminPage";

const mutate = vi.fn();
vi.mock("@/shared/hooks/useOrgs", () => ({
  useOrgs: () => ({ data: [], isLoading: false }),
  useUpdateOrg: () => ({ mutate: vi.fn() }),
  useCreateOrg: () => ({ mutate, isPending: false, isError: false, error: null }),
}));

beforeEach(() => mutate.mockClear());

function fill(placeholder: string, value: string) {
  fireEvent.change(screen.getByPlaceholderText(placeholder), { target: { value } });
}

describe("CreateOrgDialog", () => {
  it("builds the ID from the company name and keeps the same input mounted while typing", () => {
    render(<CreateOrgDialog onClose={() => {}} />);
    const name = screen.getByPlaceholderText("ООО Ромашка");
    fireEvent.change(name, { target: { value: "ООО Ромашка" } });
    // same DOM node => the field did not remount (a remount would drop focus on every key)
    expect(screen.getByPlaceholderText("ООО Ромашка")).toBe(name);
    expect((screen.getByPlaceholderText("romashka") as HTMLInputElement).value).toBe("ooo-romashka");
  });

  it("stops following the name once the ID is edited by hand", () => {
    render(<CreateOrgDialog onClose={() => {}} />);
    fill("ООО Ромашка", "Первая");
    fill("romashka", "custom-id");
    fill("ООО Ромашка", "Первая компания");
    expect((screen.getByPlaceholderText("romashka") as HTMLInputElement).value).toBe("custom-id");
  });

  it("names each wrong field on submit and does not call the API", () => {
    render(<CreateOrgDialog onClose={() => {}} />);
    fireEvent.click(screen.getByText("Создать", { selector: "button[type=submit]" }));
    expect(mutate).not.toHaveBeenCalled();
    expect(screen.getByText(/Введите название/)).toBeTruthy();
    expect(screen.getByText(/Введите корректный email/)).toBeTruthy();
    expect(screen.getByText("Пароль — не менее 10 символов")).toBeTruthy();
  });

  it("submits a valid form with a transliterated ID", () => {
    render(<CreateOrgDialog onClose={() => {}} />);
    fill("ООО Ромашка", "Дикая Сибирь");
    fill("admin@company.ru", "boss@sibir.ru");
    fill("Иван Петров", "Иван Петров");
    fill("••••••••••", "correct-horse-1");
    fireEvent.click(screen.getByText("Создать", { selector: "button[type=submit]" }));
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toMatchObject({
      display_name: "Дикая Сибирь",
      slug: "dikaya-sibir",
      plan: "trial",
      admin_email: "boss@sibir.ru",
      admin_password: "correct-horse-1",
    });
  });
});
