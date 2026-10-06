import { useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Overlay, CloseBtn, BlueField, ModalButtons, ModalError } from "./primitives";

export { Overlay, CloseBtn, BlueField, ModalButtons, ModalError };

/* ── Simple Select ── */
function SimpleSelect({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
  placeholder?: string;
}) {
  return (
    <BlueField>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-transparent outline-none text-[16px] text-primary cursor-pointer appearance-none"
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
      <span className="absolute right-4 text-primary/50 text-xs pointer-events-none">▾</span>
    </BlueField>
  );
}

/* ── Toggle ── */
function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={cn(
        "relative w-[38px] h-[21px] rounded-full transition-colors shrink-0",
        checked ? "bg-cta" : "bg-cardbg border border-primary/20"
      )}
    >
      <span
        className={cn(
          "absolute top-[2px] w-[17px] h-[17px] rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-[19px]" : "translate-x-[2px]"
        )}
      />
    </button>
  );
}

/* ── Field Label ── */
function FieldLabel({ children }: { children: ReactNode }) {
  return <label className="text-[14px] font-medium text-primary">{children}</label>;
}

/* ── Drag Handle Icon ── */
function DragHandle() {
  return (
    <span className="w-4 h-4 text-primary/30 shrink-0 cursor-grab">
      <svg viewBox="0 0 16 16" fill="none" className="w-full h-full">
        <circle cx="6" cy="4" r="1.2" fill="currentColor" />
        <circle cx="10" cy="4" r="1.2" fill="currentColor" />
        <circle cx="6" cy="8" r="1.2" fill="currentColor" />
        <circle cx="10" cy="8" r="1.2" fill="currentColor" />
        <circle cx="6" cy="12" r="1.2" fill="currentColor" />
        <circle cx="10" cy="12" r="1.2" fill="currentColor" />
      </svg>
    </span>
  );
}

/* ─────────────────────────────────────────────────
   1. NewActionModal
───────────────────────────────────────────────── */

const ACTION_TYPES = [
  "Добавить строку",
  "Удалить строку",
  "Изменить строку",
  "Отправить уведомление",
  "Запустить процесс",
  "Открыть URL",
];

const ACTION_SCOPES = ["Всем строкам", "Выбранным строкам", "Текущей строке"];

export function NewActionModal({
  onClose,
  onConfirm,
}: {
  onClose: () => void;
  onConfirm: (name: string, type: string, condition: string, scope: string) => void;
}) {
  const [name, setName] = useState("");
  const [type, setType] = useState(ACTION_TYPES[0]);
  const [condition, setCondition] = useState("");
  const [scope, setScope] = useState(ACTION_SCOPES[0]);
  const [confirmEnabled, setConfirmEnabled] = useState(false);
  const [confirmText, setConfirmText] = useState("");

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 480 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Новое действие</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Название действия</FieldLabel>
          <BlueField>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Введите название..."
              className="w-full bg-transparent outline-none text-[16px] text-primary placeholder-primary/40"
            />
          </BlueField>
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Тип действия</FieldLabel>
          <SimpleSelect value={type} onChange={setType} options={ACTION_TYPES} />
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Условие</FieldLabel>
          <BlueField>
            <span className="text-primary/40 mr-2 text-[14px] shrink-0">= формула</span>
            <input
              value={condition}
              onChange={(e) => setCondition(e.target.value)}
              placeholder="Условие выполнения..."
              className="flex-1 bg-transparent outline-none text-[16px] text-primary placeholder-primary/40"
            />
          </BlueField>
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Применить к</FieldLabel>
          <SimpleSelect value={scope} onChange={setScope} options={ACTION_SCOPES} />
        </div>

        <div className="flex flex-col gap-[8px]">
          <div className="flex items-center justify-between">
            <FieldLabel>Подтверждение</FieldLabel>
            <Toggle checked={confirmEnabled} onChange={setConfirmEnabled} />
          </div>
          {confirmEnabled && (
            <BlueField>
              <input
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder="Текст подтверждения..."
                className="w-full bg-transparent outline-none text-[16px] text-primary placeholder-primary/40"
              />
            </BlueField>
          )}
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm(name, type, condition, scope)}
          confirmLabel="Создать"
          disabled={!name.trim()}
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   2. TableViewsModal
───────────────────────────────────────────────── */

const VIEW_TYPES = [
  { icon: "📋", label: "Таблица",          key: "grid",     desc: "Просмотр данных в виде таблицы" },
  { icon: "📅", label: "Календарь",        key: "calendar", desc: "Просмотр данных в виде календаря" },
  { icon: "🃏", label: "Колода",           key: "deck",     desc: "Просмотр данных в виде колоды" },
  { icon: "🖼️", label: "Галерея",          key: "gallery",  desc: "Просмотр данных в виде галереи" },
  { icon: "📊", label: "Диаграмма Ганта",  key: "gantt",    desc: "Просмотр данных в виде диаграммы Ганта" },
  { icon: "📍", label: "Карта",            key: "map",      desc: "Просмотр данных в виде карты" },
];

export function TableViewsModal({
  onClose,
  onAdd,
}: {
  onClose: () => void;
  onAdd: (type: string) => void;
}) {
  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 480 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Виды таблицы</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-3">
          {VIEW_TYPES.map((v) => (
            <div
              key={v.key}
              className="flex items-center gap-4 px-4 py-3 rounded-[10px] bg-mainbg hover:bg-cardbg transition-colors"
            >
              <span className="text-2xl shrink-0">{v.icon}</span>
              <div className="flex-1 min-w-0">
                <p className="text-[15px] font-semibold text-primary">{v.label}</p>
                <p className="text-[13px] text-primary/60 truncate">{v.desc}</p>
              </div>
              <button
                onClick={() => onAdd(v.key)}
                className="shrink-0 h-[30px] px-4 border-2 border-cta rounded-btn text-cta text-[13px] hover:bg-cta/10 transition-colors"
              >
                + Добавить
              </button>
            </div>
          ))}
        </div>
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   3. SortingModal
───────────────────────────────────────────────── */

type SortRule = { id: string; column: string; direction: "asc" | "desc" };

export function SortingModal({
  columns,
  rules: initialRules,
  onClose,
  onApply,
}: {
  columns: string[];
  rules: { column: string; direction: "asc" | "desc" }[];
  onClose: () => void;
  onApply: (rules: { column: string; direction: "asc" | "desc" }[]) => void;
}) {
  const [rules, setRules] = useState<SortRule[]>(
    initialRules.map((r, i) => ({ ...r, id: String(i) }))
  );

  function addRule() {
    setRules((prev) => [
      ...prev,
      { id: Date.now().toString(), column: columns[0] ?? "", direction: "asc" },
    ]);
  }

  function removeRule(id: string) {
    setRules((prev) => prev.filter((r) => r.id !== id));
  }

  function updateRule(id: string, patch: Partial<SortRule>) {
    setRules((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 520 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Сортировка</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-3">
          {rules.map((rule) => (
            <div key={rule.id} className="flex items-center gap-3">
              <DragHandle />

              <BlueField className="flex-1">
                <select
                  value={rule.column}
                  onChange={(e) => updateRule(rule.id, { column: e.target.value })}
                  className="w-full bg-transparent outline-none text-[15px] text-primary appearance-none cursor-pointer"
                >
                  {columns.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
                <span className="absolute right-4 text-primary/50 text-xs pointer-events-none">▾</span>
              </BlueField>

              {/* Direction toggle */}
              <div className="flex rounded-btn overflow-hidden border-2 border-cta shrink-0">
                {(["asc", "desc"] as const).map((dir) => (
                  <button
                    key={dir}
                    onClick={() => updateRule(rule.id, { direction: dir })}
                    className={cn(
                      "px-3 h-[37px] text-[13px] font-medium transition-colors",
                      rule.direction === dir ? "bg-cta text-white" : "bg-mainbg text-cta hover:bg-cta/10"
                    )}
                  >
                    {dir === "asc" ? "По возрастанию" : "По убыванию"}
                  </button>
                ))}
              </div>

              <button
                onClick={() => removeRule(rule.id)}
                className="w-7 h-7 shrink-0 text-primary/40 hover:text-primary/70 transition-colors flex items-center justify-center"
              >
                <svg viewBox="0 0 28 28" fill="none" className="w-5 h-5">
                  <line x1="7" y1="7" x2="21" y2="21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  <line x1="21" y1="7" x2="7" y2="21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          ))}

          <button
            onClick={addRule}
            className="flex items-center gap-2 text-cta text-[14px] hover:opacity-70 transition-opacity w-fit"
          >
            <svg viewBox="0 0 20 20" fill="none" className="w-4 h-4">
              <path d="M10 3v14M3 10h14" stroke="#35A7FF" strokeWidth="2" strokeLinecap="round" />
            </svg>
            Добавить правило
          </button>
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onApply(rules.map(({ column, direction }) => ({ column, direction })))}
          confirmLabel="Применить"
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   4. GroupingModal
───────────────────────────────────────────────── */

const GROUP_SORT_OPTIONS = ["А→Я", "Я→А", "По количеству"];

export function GroupingModal({
  columns,
  onClose,
  onApply,
  onReset,
}: {
  columns: string[];
  onClose: () => void;
  onApply: (settings: {
    groupBy: string;
    showTotals: boolean;
    sortGroups: string;
    collapseEmpty: boolean;
  }) => void;
  onReset: () => void;
}) {
  const [groupBy, setGroupBy] = useState(columns[0] ?? "");
  const [showTotals, setShowTotals] = useState(false);
  const [sortGroups, setSortGroups] = useState(GROUP_SORT_OPTIONS[0]);
  const [collapseEmpty, setCollapseEmpty] = useState(false);

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 480 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Группировка</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Группировать по</FieldLabel>
          <SimpleSelect value={groupBy} onChange={setGroupBy} options={columns} />
        </div>

        <div className="flex items-center justify-between">
          <FieldLabel>Показывать итоги</FieldLabel>
          <Toggle checked={showTotals} onChange={setShowTotals} />
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Сортировать группы</FieldLabel>
          <SimpleSelect value={sortGroups} onChange={setSortGroups} options={GROUP_SORT_OPTIONS} />
        </div>

        <div className="flex items-center justify-between">
          <FieldLabel>Свернуть пустые группы</FieldLabel>
          <Toggle checked={collapseEmpty} onChange={setCollapseEmpty} />
        </div>

        <div className="flex items-center justify-between pt-2">
          <button
            onClick={onReset}
            className="px-4 py-[3px] h-[34px] border-2 border-red-400 rounded-btn text-red-400 text-meta hover:bg-red-50 transition-colors"
          >
            Сбросить группировку
          </button>
          <ModalButtons
            onCancel={onClose}
            onConfirm={() => onApply({ groupBy, showTotals, sortGroups, collapseEmpty })}
            confirmLabel="Применить"
          />
        </div>
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   5. ViewExtensionsModal
───────────────────────────────────────────────── */

const VIEW_EXTENSIONS = [
  { key: "aggregates",   icon: "📊", label: "Агрегаты",               desc: "Суммы, подсчёт" },
  { key: "search",       icon: "🔍", label: "Быстрый поиск",           desc: "Поиск по данным" },
  { key: "pin",          icon: "📌", label: "Закрепить столбцы",       desc: "Фиксация столбцов при прокрутке" },
  { key: "color",        icon: "🎨", label: "Цветовое кодирование",    desc: "Подсветка строк по условию" },
  { key: "mobile",       icon: "📱", label: "Мобильная оптимизация",   desc: "Адаптация для малых экранов" },
  { key: "quickactions", icon: "⚡", label: "Быстрые действия",        desc: "Контекстные действия по строке" },
];

export function ViewExtensionsModal({ onClose }: { onClose: () => void }) {
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});

  function toggle(key: string) {
    setEnabled((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 480 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Расширения для представлений</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-3">
          {VIEW_EXTENSIONS.map((ext) => (
            <div
              key={ext.key}
              className="flex items-center gap-4 px-4 py-3 rounded-[10px] bg-mainbg"
            >
              <span className="text-2xl shrink-0">{ext.icon}</span>
              <div className="flex-1 min-w-0">
                <p className="text-[15px] font-semibold text-primary">{ext.label}</p>
                <p className="text-[13px] text-primary/60">{ext.desc}</p>
              </div>
              <Toggle checked={!!enabled[ext.key]} onChange={() => toggle(ext.key)} />
            </div>
          ))}
        </div>

        <div className="flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-[3px] h-[34px] bg-cta border-2 border-cta rounded-btn text-white text-meta hover:bg-active transition-colors"
          >
            Готово
          </button>
        </div>
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   6. AggregatesModal
───────────────────────────────────────────────── */

const AGGREGATE_TYPES = ["Нет", "Сумма", "Среднее", "Мин", "Макс", "Количество", "Уникальные"];

export function AggregatesModal({
  columns,
  onClose,
  onApply,
}: {
  columns: { name: string; type: string }[];
  onClose: () => void;
  onApply: (settings: Record<string, string>) => void;
}) {
  const [settings, setSettings] = useState<Record<string, string>>(() =>
    Object.fromEntries(columns.map((c) => [c.name, "Нет"]))
  );

  function setAgg(name: string, agg: string) {
    setSettings((prev) => ({ ...prev, [name]: agg }));
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 520 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Агрегаты по столбцам</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="rounded-[10px] overflow-hidden border border-cardbg">
          <table className="w-full text-[14px]">
            <thead>
              <tr className="bg-cardbg">
                <th className="text-left font-semibold text-primary px-4 py-2">Столбец</th>
                <th className="text-left font-semibold text-primary px-4 py-2">Тип агрегата</th>
              </tr>
            </thead>
            <tbody>
              {columns.map((col, i) => (
                <tr
                  key={col.name}
                  className={cn("border-t border-cardbg", i % 2 === 1 && "bg-mainbg")}
                >
                  <td className="px-4 py-2 text-primary">{col.name}</td>
                  <td className="px-4 py-2">
                    <BlueField className="h-[34px]">
                      <select
                        value={settings[col.name] ?? "Нет"}
                        onChange={(e) => setAgg(col.name, e.target.value)}
                        className="w-full bg-transparent outline-none text-[14px] text-primary appearance-none cursor-pointer"
                      >
                        {AGGREGATE_TYPES.map((t) => (
                          <option key={t} value={t}>
                            {t}
                          </option>
                        ))}
                      </select>
                      <span className="absolute right-4 text-primary/50 text-xs pointer-events-none">▾</span>
                    </BlueField>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onApply(settings)}
          confirmLabel="Применить"
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   7. DensityModal
───────────────────────────────────────────────── */

type Density = "compact" | "standard" | "spacious";

const DENSITY_OPTIONS: { key: Density; label: string; desc: string; strips: number; h: number }[] = [
  { key: "compact",  label: "Компактная", desc: "Маленькие строки",  strips: 5, h: 8 },
  { key: "standard", label: "Стандартная", desc: "Средние строки",   strips: 3, h: 14 },
  { key: "spacious", label: "Просторная",  desc: "Большие строки",   strips: 2, h: 20 },
];

export function DensityModal({
  current,
  onClose,
  onApply,
}: {
  current: Density;
  onClose: () => void;
  onApply: (density: Density) => void;
}) {
  const [selected, setSelected] = useState<Density>(current);

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 480 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Плотность строк</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex gap-4">
          {DENSITY_OPTIONS.map((opt) => (
            <button
              key={opt.key}
              onClick={() => setSelected(opt.key)}
              className={cn(
                "flex-1 flex flex-col items-center gap-3 p-4 rounded-[10px] border-2 transition-colors",
                selected === opt.key
                  ? "border-cta bg-cta/5"
                  : "border-cardbg bg-mainbg hover:border-cta/40"
              )}
            >
              {/* Preview strips */}
              <div className="w-full flex flex-col gap-[4px]">
                {Array.from({ length: opt.strips }).map((_, i) => (
                  <div
                    key={i}
                    className={cn("w-full rounded-[3px]", selected === opt.key ? "bg-cta/30" : "bg-cardbg")}
                    style={{ height: opt.h }}
                  />
                ))}
              </div>
              <p className={cn("text-[14px] font-semibold", selected === opt.key ? "text-cta" : "text-primary")}>
                {opt.label}
              </p>
              <p className="text-[12px] text-primary/60">{opt.desc}</p>
            </button>
          ))}
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onApply(selected)}
          confirmLabel="Применить"
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   8. LayoutModal
───────────────────────────────────────────────── */

export function LayoutModal({
  onClose,
  onApply,
}: {
  onClose: () => void;
  onApply: (settings: {
    pinnedColumns: number;
    rowHeightMode: "auto" | "fixed";
    rowHeightPx: number;
    wrapText: boolean;
    rowNumbers: boolean;
    alternatingRows: boolean;
  }) => void;
}) {
  const [pinnedColumns, setPinnedColumns] = useState(0);
  const [rowHeightMode, setRowHeightMode] = useState<"auto" | "fixed">("auto");
  const [rowHeightPx, setRowHeightPx] = useState(40);
  const [wrapText, setWrapText] = useState(false);
  const [rowNumbers, setRowNumbers] = useState(false);
  const [alternatingRows, setAlternatingRows] = useState(false);

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 480 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Настройки отображения</h2>
          <CloseBtn onClick={onClose} />
        </div>

        {/* Pinned columns */}
        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Закреплённые столбцы (первых N)</FieldLabel>
          <BlueField className="w-32">
            <input
              type="number"
              min={0}
              value={pinnedColumns}
              onChange={(e) => setPinnedColumns(Number(e.target.value))}
              className="w-full bg-transparent outline-none text-[16px] text-primary"
            />
          </BlueField>
        </div>

        {/* Row height */}
        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Высота строк</FieldLabel>
          <div className="flex gap-4 items-center">
            {(["auto", "fixed"] as const).map((mode) => (
              <label key={mode} className="flex items-center gap-2 cursor-pointer text-[14px] text-primary">
                <input
                  type="radio"
                  checked={rowHeightMode === mode}
                  onChange={() => setRowHeightMode(mode)}
                  className="accent-cta"
                />
                {mode === "auto" ? "Авто" : "Фиксированная"}
              </label>
            ))}
            {rowHeightMode === "fixed" && (
              <BlueField className="w-28 h-[34px]">
                <input
                  type="number"
                  min={20}
                  max={200}
                  value={rowHeightPx}
                  onChange={(e) => setRowHeightPx(Number(e.target.value))}
                  className="w-full bg-transparent outline-none text-[15px] text-primary"
                />
                <span className="absolute right-4 text-primary/50 text-[13px] pointer-events-none">px</span>
              </BlueField>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between">
          <FieldLabel>Перенос текста</FieldLabel>
          <Toggle checked={wrapText} onChange={setWrapText} />
        </div>

        <div className="flex items-center justify-between">
          <FieldLabel>Нумерация строк</FieldLabel>
          <Toggle checked={rowNumbers} onChange={setRowNumbers} />
        </div>

        <div className="flex items-center justify-between">
          <FieldLabel>Чередование цветов строк</FieldLabel>
          <Toggle checked={alternatingRows} onChange={setAlternatingRows} />
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() =>
            onApply({ pinnedColumns, rowHeightMode, rowHeightPx, wrapText, rowNumbers, alternatingRows })
          }
          confirmLabel="Применить"
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   9. ColumnTypesModal
───────────────────────────────────────────────── */

const COLUMN_TYPES = [
  { key: "text",       label: "Текст",          desc: "Строки текста",         icon: "T" },
  { key: "number",     label: "Число",           desc: "Числовые значения",     icon: "#" },
  { key: "datetime",   label: "Дата и время",    desc: "Дата, время или оба",   icon: "📅" },
  { key: "image",      label: "Изображение",     desc: "Файлы изображений",     icon: "🖼️" },
  { key: "app",        label: "Приложение",      desc: "Ссылка на приложение",  icon: "📱" },
  { key: "list",       label: "Список",          desc: "Перечисление значений", icon: "≡" },
  { key: "link",       label: "Ссылка",          desc: "URL, email, телефон",   icon: "🔗" },
  { key: "location",   label: "Расположение",    desc: "Координаты или адрес",  icon: "📍" },
  { key: "attachment", label: "Вложения",        desc: "Файлы разных типов",    icon: "📎" },
  { key: "meta",       label: "Метаданные",      desc: "Служебные данные",      icon: "ℹ️" },
  { key: "boolean",    label: "Да/Нет",          desc: "Булево значение",       icon: "✓" },
  { key: "email",      label: "Email",           desc: "Адрес электронной почты", icon: "@" },
  { key: "phone",      label: "Телефон",         desc: "Номер телефона",        icon: "📞" },
  { key: "url",        label: "URL",             desc: "Веб-адрес",             icon: "🌐" },
  { key: "rating",     label: "Оценка (1-5)",    desc: "Рейтинг звёздами",      icon: "⭐" },
];

export function ColumnTypesModal({
  columnName,
  currentType,
  onClose,
  onApply,
}: {
  columnName: string;
  currentType: string;
  onClose: () => void;
  onApply: (type: string, options: Record<string, unknown>) => void;
}) {
  const [selected, setSelected] = useState(currentType);
  const [options, setOptions] = useState<Record<string, unknown>>({});

  function setOpt(key: string, value: unknown) {
    setOptions((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 560 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Тип столбца: {columnName}</h2>
          <CloseBtn onClick={onClose} />
        </div>

        {/* Grid 3 columns */}
        <div className="grid grid-cols-3 gap-3">
          {COLUMN_TYPES.map((ct) => (
            <button
              key={ct.key}
              onClick={() => {
                setSelected(ct.key);
                setOptions({});
              }}
              className={cn(
                "flex flex-col items-center gap-2 px-3 py-4 rounded-[10px] border-2 transition-colors text-center",
                selected === ct.key
                  ? "border-cta bg-cta/10"
                  : "border-cardbg bg-mainbg hover:border-cta/40"
              )}
            >
              <span className="text-2xl leading-none">{ct.icon}</span>
              <span className={cn("text-[13px] font-semibold", selected === ct.key ? "text-cta" : "text-primary")}>
                {ct.label}
              </span>
              <span className="text-[11px] text-primary/60 leading-tight">{ct.desc}</span>
            </button>
          ))}
        </div>

        {/* Sub-options */}
        {selected === "list" && (
          <div className="flex flex-col gap-3 p-4 rounded-[10px] bg-mainbg">
            <FieldLabel>Вариант списка</FieldLabel>
            {["Перечисление", "Ссылка на другую таблицу"].map((v) => (
              <label key={v} className="flex items-center gap-2 cursor-pointer text-[14px] text-primary">
                <input
                  type="radio"
                  checked={options["listType"] === v}
                  onChange={() => setOpt("listType", v)}
                  className="accent-cta"
                />
                {v}
              </label>
            ))}
          </div>
        )}

        {selected === "attachment" && (
          <div className="flex flex-col gap-2 p-4 rounded-[10px] bg-mainbg">
            <FieldLabel>Поддерживаемые типы файлов</FieldLabel>
            {["Изображения", "Документы", "Видео", "Аудио"].map((ft) => (
              <label key={ft} className="flex items-center gap-2 cursor-pointer text-[14px] text-primary">
                <input
                  type="checkbox"
                  checked={!!(options[`file_${ft}`] ?? true)}
                  onChange={(e) => setOpt(`file_${ft}`, e.target.checked)}
                  className="accent-cta"
                />
                {ft}
              </label>
            ))}
          </div>
        )}

        {selected === "datetime" && (
          <div className="flex flex-col gap-3 p-4 rounded-[10px] bg-mainbg">
            <div className="flex flex-col gap-[6px]">
              <FieldLabel>Формат даты</FieldLabel>
              <SimpleSelect
                value={(options["dateFormat"] as string) || "DD.MM.YYYY"}
                onChange={(v) => setOpt("dateFormat", v)}
                options={["DD.MM.YYYY", "MM/DD/YYYY", "YYYY-MM-DD", "D MMMM YYYY"]}
              />
            </div>
            <div className="flex items-center justify-between">
              <FieldLabel>Включить время</FieldLabel>
              <Toggle
                checked={!!(options["includeTime"])}
                onChange={(v) => setOpt("includeTime", v)}
              />
            </div>
          </div>
        )}

        {selected === "location" && (
          <div className="flex gap-4 p-4 rounded-[10px] bg-mainbg">
            {["Координаты", "Адрес"].map((lt) => (
              <label key={lt} className="flex items-center gap-2 cursor-pointer text-[14px] text-primary">
                <input
                  type="radio"
                  checked={(options["locationType"] || "Координаты") === lt}
                  onChange={() => setOpt("locationType", lt)}
                  className="accent-cta"
                />
                {lt}
              </label>
            ))}
          </div>
        )}

        {selected === "link" && (
          <div className="flex gap-4 p-4 rounded-[10px] bg-mainbg">
            {["URL", "Email", "Телефон"].map((lt) => (
              <label key={lt} className="flex items-center gap-2 cursor-pointer text-[14px] text-primary">
                <input
                  type="radio"
                  checked={(options["linkType"] || "URL") === lt}
                  onChange={() => setOpt("linkType", lt)}
                  className="accent-cta"
                />
                {lt}
              </label>
            ))}
          </div>
        )}

        {selected === "meta" && (
          <div className="flex flex-col gap-[6px] p-4 rounded-[10px] bg-mainbg">
            <FieldLabel>Тип метаданных</FieldLabel>
            <SimpleSelect
              value={(options["metaType"] as string) || "Создан"}
              onChange={(v) => setOpt("metaType", v)}
              options={["Создан", "Изменён", "Создал", "Изменил", "Идентификатор"]}
            />
          </div>
        )}

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onApply(selected, options)}
          confirmLabel="Применить"
        />
      </div>
    </Overlay>
  );
}
