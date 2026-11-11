import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FunctionChecklist, RoleFunctionsPanel, groupCatalog } from "./RoleFunctions";
import { useAuthStore } from "@/shared/auth/store";
import type { FunctionCatalogItem, Role, RoleFunctions } from "@/shared/api/roles";

const CATALOG: FunctionCatalogItem[] = [
  { code: "users.view", label: "Просматривать пользователей", description: "Список", group: "Пользователи" },
  { code: "users.manage", label: "Создавать пользователей", description: "Создание", group: "Пользователи" },
  { code: "audit.view", label: "Смотреть журнал аудита", description: "Журнал", group: "Безопасность" },
];

let roleFns: RoleFunctions;
const saveMutate = vi.fn();

vi.mock("@/shared/hooks/useRbac", () => ({
  useFunctionCatalog: () => ({ isLoading: false, isError: false, data: CATALOG }),
  useRoleFunctions: () => ({ isLoading: false, isError: false, data: roleFns }),
  useSaveRoleFunctions: () => ({ mutate: saveMutate, isPending: false, isError: false, isSuccess: false }),
}));

const ROLE: Role = { id: "org_admin", display_name: "Администратор организации", description: null, is_system: true };

function setUser(roleIds: string[]) {
  useAuthStore.setState({
    user: { roles: roleIds.map((id) => ({ id, display_name: id })) } as never,
    isAuthenticated: true,
    initializing: false,
  });
}

beforeEach(() => {
  saveMutate.mockClear();
  roleFns = {
    role_id: "org_admin",
    locked: false,
    is_system: true,
    allowed: ["users.view", "users.manage"],
    defaults: ["users.view", "users.manage"],
  };
  setUser(["platform_admin"]);
});

afterEach(() => useAuthStore.setState({ user: null, isAuthenticated: false, initializing: false }));

describe("groupCatalog", () => {
  it("groups functions in first-seen order", () => {
    const g = groupCatalog(CATALOG);
    expect(g.map((x) => x.group)).toEqual(["Пользователи", "Безопасность"]);
    expect(g[0].items).toHaveLength(2);
  });
});

describe("FunctionChecklist", () => {
  it("toggles one function and a whole group", () => {
    const onChange = vi.fn();
    render(<FunctionChecklist catalog={CATALOG} selected={new Set(["users.view"])} onChange={onChange} />);
    fireEvent.click(screen.getByLabelText(/Создавать пользователей/));
    expect([...(onChange.mock.calls[0][0] as Set<string>)].sort()).toEqual(["users.manage", "users.view"]);

    fireEvent.click(screen.getAllByText("Выбрать все")[0]); // "Пользователи" group
    expect([...(onChange.mock.calls[1][0] as Set<string>)].sort()).toEqual(["users.manage", "users.view"]);
  });

  it("is inert when disabled", () => {
    const onChange = vi.fn();
    render(<FunctionChecklist catalog={CATALOG} selected={new Set()} onChange={onChange} disabled />);
    fireEvent.click(screen.getByLabelText(/Смотреть журнал аудита/));
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByText("Выбрать все")).toBeNull();
  });
});

describe("RoleFunctionsPanel", () => {
  it("lets a platform admin untick a function and save the new set", () => {
    render(<RoleFunctionsPanel role={ROLE} />);
    const save = screen.getByText("Сохранить") as HTMLButtonElement;
    expect(save.disabled).toBe(true); // nothing changed yet

    fireEvent.click(screen.getByLabelText(/Создавать пользователей/));
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    expect(saveMutate).toHaveBeenCalledWith({ roleId: "org_admin", allowed: ["users.view"] });
  });

  it("restores defaults and can revert unsaved edits", () => {
    roleFns = { ...roleFns, allowed: ["users.view"] }; // one default removed earlier
    render(<RoleFunctionsPanel role={ROLE} />);
    const box = screen.getByLabelText(/Создавать пользователей/) as HTMLInputElement;
    expect(box.checked).toBe(false);

    fireEvent.click(screen.getByText("Вернуть значения по умолчанию"));
    expect(box.checked).toBe(true);

    fireEvent.click(screen.getByText("Отменить изменения"));
    expect(box.checked).toBe(false);
  });

  it("shows the platform admin role as locked and read-only", () => {
    roleFns = { ...roleFns, role_id: "platform_admin", locked: true, allowed: CATALOG.map((c) => c.code) };
    render(<RoleFunctionsPanel role={{ ...ROLE, id: "platform_admin" }} />);
    expect(screen.getByText(/всегда имеет все функции/)).toBeTruthy();
    expect((screen.getByLabelText(/Смотреть журнал аудита/) as HTMLInputElement).disabled).toBe(true);
    expect(screen.queryByText("Сохранить")).toBeNull();
  });

  it("makes system roles read-only for an org admin", () => {
    setUser(["org_admin"]);
    render(<RoleFunctionsPanel role={ROLE} />);
    expect(screen.getByText(/может менять только администратор платформы/)).toBeTruthy();
    expect(screen.queryByText("Сохранить")).toBeNull();
  });
});
