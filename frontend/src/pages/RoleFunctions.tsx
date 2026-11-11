import { useEffect, useMemo, useState } from "react";
import { useAuthStore } from "@/shared/auth/store";
import { useFunctionCatalog, useRoleFunctions, useSaveRoleFunctions } from "@/shared/hooks/useRbac";
import type { FunctionCatalogItem, Role } from "@/shared/api/roles";

/** Group the catalog preserving the order groups first appear in. */
export function groupCatalog(catalog: FunctionCatalogItem[]): { group: string; items: FunctionCatalogItem[] }[] {
  const order: string[] = [];
  const map = new Map<string, FunctionCatalogItem[]>();
  for (const f of catalog) {
    if (!map.has(f.group)) {
      map.set(f.group, []);
      order.push(f.group);
    }
    map.get(f.group)!.push(f);
  }
  return order.map((group) => ({ group, items: map.get(group)! }));
}

/** Grouped checkbox list of functions. Controlled: the parent owns `selected`. */
export function FunctionChecklist({
  catalog,
  selected,
  onChange,
  disabled = false,
}: {
  catalog: FunctionCatalogItem[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  disabled?: boolean;
}) {
  const groups = useMemo(() => groupCatalog(catalog), [catalog]);

  function toggle(code: string) {
    if (disabled) return;
    const next = new Set(selected);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    onChange(next);
  }

  function toggleGroup(items: FunctionCatalogItem[]) {
    if (disabled) return;
    const allOn = items.every((i) => selected.has(i.code));
    const next = new Set(selected);
    for (const i of items) {
      if (allOn) next.delete(i.code);
      else next.add(i.code);
    }
    onChange(next);
  }

  return (
    <div className="flex flex-col gap-[18px]">
      {groups.map(({ group, items }) => {
        const on = items.filter((i) => selected.has(i.code)).length;
        const allOn = on === items.length;
        return (
          <section key={group}>
            <div className="flex items-center justify-between mb-[6px]">
              <h4 className="text-[13px] font-semibold uppercase tracking-wide text-primary/50">
                {group} <span className="font-normal normal-case text-primary/40">· {on} из {items.length}</span>
              </h4>
              {!disabled && (
                <button
                  type="button"
                  onClick={() => toggleGroup(items)}
                  className="text-[12px] font-medium text-cta hover:underline"
                >
                  {allOn ? "Снять все" : "Выбрать все"}
                </button>
              )}
            </div>
            <ul className="flex flex-col">
              {items.map((f) => {
                const checked = selected.has(f.code);
                return (
                  <li key={f.code}>
                    <label
                      className={`flex items-start gap-3 rounded-[8px] px-2 py-[7px] ${
                        disabled ? "cursor-default" : "cursor-pointer hover:bg-mainbg/60"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={disabled}
                        onChange={() => toggle(f.code)}
                        className="mt-[3px] h-4 w-4 accent-[#35A7FF]"
                      />
                      <span className="min-w-0">
                        <span className={`block text-[14px] ${checked ? "text-primary" : "text-primary/60"}`}>
                          {f.label}
                        </span>
                        <span className="block text-[12px] text-primary/40">{f.description}</span>
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function sameSet(a: Set<string>, b: Set<string>) {
  return a.size === b.size && [...a].every((x) => b.has(x));
}

/** Expanded panel under a role row: its functions with checkboxes + save. */
export function RoleFunctionsPanel({ role }: { role: Role }) {
  const isPlatformAdmin = useAuthStore((s) => s.user?.roles.some((r) => r.id === "platform_admin") ?? false);
  const catalogQ = useFunctionCatalog();
  const fnQ = useRoleFunctions(role.id);
  const save = useSaveRoleFunctions();

  const [draft, setDraft] = useState<Set<string>>(new Set());
  const [loadedFor, setLoadedFor] = useState<string | null>(null);

  // (Re)load the draft whenever the saved state for this role changes.
  useEffect(() => {
    if (fnQ.data) {
      setDraft(new Set(fnQ.data.allowed));
      setLoadedFor(role.id);
    }
  }, [fnQ.data, role.id]);

  if (catalogQ.isLoading || fnQ.isLoading || loadedFor !== role.id) {
    return <p className="text-[13px] text-primary/40 py-3">Загрузка функций…</p>;
  }
  if (catalogQ.isError || fnQ.isError || !catalogQ.data || !fnQ.data) {
    return <p className="text-[13px] text-[#C22A2A] py-3">Не удалось загрузить функции роли.</p>;
  }

  const saved = new Set(fnQ.data.allowed);
  const defaults = new Set(fnQ.data.defaults);
  const locked = fnQ.data.locked;
  // org_admin may edit custom roles of their own org, but not system roles.
  const readOnly = locked || (role.is_system && !isPlatformAdmin);
  const dirty = !sameSet(draft, saved);
  const isDefault = sameSet(draft, defaults);

  return (
    <div className="px-2 pb-2">
      {locked && (
        <p className="mb-3 rounded-[8px] bg-cta/10 px-3 py-2 text-[13px] text-primary">
          🔒 Администратор платформы всегда имеет все функции, это нельзя изменить.
        </p>
      )}
      {!locked && readOnly && (
        <p className="mb-3 rounded-[8px] bg-mainbg px-3 py-2 text-[13px] text-primary/70">
          Функции системных ролей может менять только администратор платформы.
        </p>
      )}

      <FunctionChecklist catalog={catalogQ.data} selected={draft} onChange={setDraft} disabled={readOnly} />

      {save.isError && (
        <p className="mt-3 rounded-[8px] bg-[#FFF0F0] px-3 py-2 text-[13px] text-[#C22A2A]">
          Не удалось сохранить. Проверьте права и попробуйте ещё раз.
        </p>
      )}

      {!readOnly && (
        <div className="mt-4 flex flex-wrap items-center gap-[10px]">
          <button
            type="button"
            disabled={!dirty || save.isPending}
            onClick={() => save.mutate({ roleId: role.id, allowed: [...draft] })}
            className="h-[38px] rounded-[20px] bg-cta px-5 text-[14px] font-semibold text-white transition-colors hover:bg-active disabled:opacity-40"
          >
            {save.isPending ? "Сохранение…" : "Сохранить"}
          </button>
          <button
            type="button"
            disabled={!dirty}
            onClick={() => setDraft(new Set(saved))}
            className="h-[38px] rounded-[20px] border-2 border-primary/20 px-5 text-[14px] text-primary transition-colors hover:bg-mainbg disabled:opacity-40"
          >
            Отменить изменения
          </button>
          <button
            type="button"
            disabled={isDefault}
            onClick={() => setDraft(new Set(defaults))}
            className="text-[13px] font-medium text-cta hover:underline disabled:opacity-40"
          >
            Вернуть значения по умолчанию
          </button>
          {save.isSuccess && !dirty && <span className="text-[13px] text-[#20BE4F]">Сохранено</span>}
        </div>
      )}
    </div>
  );
}
