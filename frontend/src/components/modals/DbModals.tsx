import { useState, useRef, useEffect, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Overlay, CloseBtn, BlueField, ModalButtons, ModalError } from "./primitives";

export { Overlay, CloseBtn, BlueField, ModalButtons, ModalError };

/* ─────────────────────────────────────────────────
   SHARED HELPERS
───────────────────────────────────────────────── */

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={cn(
        "relative w-[38px] h-[21px] rounded-full transition-colors shrink-0",
        checked ? "bg-cta" : "bg-cardbg"
      )}
    >
      <div
        className={cn(
          "absolute top-0 w-[21px] h-[21px] rounded-full bg-white border border-white/60 shadow transition-transform",
          checked ? "translate-x-[17px]" : "translate-x-0"
        )}
      />
    </button>
  );
}

function SimpleDropdown({
  value,
  options,
  onChange,
  placeholder,
}: {
  value: string;
  options: string[];
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  return (
    <div ref={ref} className="relative w-full">
      <BlueField>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="w-full flex items-center justify-between text-[18px] text-primary cursor-pointer pr-1"
        >
          <span className={cn(!value && "opacity-50")}>{value || placeholder || "Выбрать..."}</span>
          <span className={cn("text-xs transition-transform", open && "rotate-180")}>▾</span>
        </button>
      </BlueField>
      {open && (
        <div
          className="absolute left-0 top-full mt-2 z-30 w-full bg-white rounded-[25px] p-[5px] flex flex-col"
          style={{ boxShadow: "10px 10px 20px rgba(0,0,0,0.25), -10px -10px 20px rgba(0,0,0,0.25)" }}
        >
          {options.map((opt, i) => (
            <button
              key={opt}
              type="button"
              onClick={() => { onChange(opt); setOpen(false); }}
              className={cn(
                "w-full h-11 shrink-0 flex items-center px-[30px] border-2 border-white rounded-btn",
                "text-meta font-medium text-primary text-left transition-colors",
                value === opt ? "bg-selected" : "bg-mainbg hover:bg-cardbg"
              )}
              style={{ marginTop: i === 0 ? 0 : -2 }}
            >
              {opt}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function OutlineBtn({ onClick, children }: { onClick?: () => void; children: ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="px-4 py-[3px] h-[34px] border-2 border-cta rounded-btn text-cta text-meta
                 hover:bg-cta/10 transition-colors whitespace-nowrap"
    >
      {children}
    </button>
  );
}

function PrimaryBtn({ onClick, children }: { onClick?: () => void; children: ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="px-5 py-[3px] h-[34px] bg-cta border-2 border-cta rounded-btn text-white text-meta
                 hover:bg-active transition-colors"
    >
      {children}
    </button>
  );
}

const COLUMN_TYPES = ["Текст", "Длинный текст", "Число", "Дробное", "Дата", "Дата и время", "Чекбокс", "Список", "Email", "Телефон", "URL", "Изображение", "JSON", "Связь"];

export const COLUMN_TYPE_TO_FIELD_TYPE: Record<string, string> = {
  "Текст": "text",
  "Длинный текст": "long_text",
  "Число": "number",
  "Дробное": "decimal",
  "Дата": "date",
  "Дата и время": "datetime",
  "Чекбокс": "boolean",
  "Список": "select",
  "Email": "email",
  "Телефон": "phone",
  "URL": "url",
  "Изображение": "image",
  "JSON": "json",
  "Связь": "relation",
};

export const FIELD_TYPE_TO_COLUMN_TYPE: Record<string, string> = Object.fromEntries(
  Object.entries(COLUMN_TYPE_TO_FIELD_TYPE).map(([k, v]) => [v, k])
);

/* ─────────────────────────────────────────────────
   1. EditTableModal
───────────────────────────────────────────────── */

export interface TableColumn {
  id: string;
  name: string;
  type: string;
  isKey?: boolean;
  isLabel?: boolean;
}

export function EditTableModal({
  tableName,
  columns,
  onClose,
  onAddVirtual,
  onGoToData,
  onDone,
}: {
  tableName: string;
  columns: TableColumn[];
  onClose: () => void;
  onAddVirtual?: () => void;
  onGoToData?: () => void;
  onDone?: (name: string, cols: TableColumn[]) => void;
}) {
  const [name, setName] = useState(tableName);
  const [cols, setCols] = useState<TableColumn[]>(columns);
  const [formulaColId, setFormulaColId] = useState<string | null>(null);

  function addVirtualColumn() {
    const newCol: TableColumn = {
      id: `col_${Date.now()}`,
      name: "Новое поле",
      type: "Текст",
    };
    setCols((prev) => [...prev, newCol]);
    onAddVirtual?.();
  }

  function deleteCol(id: string) {
    setCols((prev) => prev.filter((c) => c.id !== id));
  }

  function updateCol(id: string, patch: Partial<TableColumn>) {
    setCols((prev) => prev.map((c) => (c.id === id ? { ...c, ...patch } : c)));
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 700 }} className="px-10 pb-8">
        {/* Header */}
        <div className="flex items-start justify-between pt-[30px] mb-2">
          <div>
            <h2 className="text-[20px] font-bold text-primary flex items-center gap-2">
              Таблица:{" "}
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="bg-transparent border-b border-cardbg outline-none text-primary focus:border-cta"
              />
            </h2>
            <p className="text-[14px] text-primary/60 mt-1">
              {cols.length} колонок:{" "}
              <span className="inline-flex items-center gap-1">
                <KeyIcon /> Row ID
              </span>{" "}
              <span className="inline-flex items-center gap-1">
                <TagIcon /> Модуль
              </span>
            </p>
          </div>
          <CloseBtn onClick={onClose} />
        </div>

        {/* Action buttons */}
        <div className="flex flex-wrap gap-[10px] mb-5">
          <OutlineBtn onClick={onGoToData}>Перейти к данным</OutlineBtn>
          <OutlineBtn onClick={() => alert("Просмотр исходного кода будет доступен после сохранения таблицы")}>
            Перейти к исх. коду
          </OutlineBtn>
          <OutlineBtn onClick={addVirtualColumn}>Добавить вирт. столбец</OutlineBtn>
          <PrimaryBtn onClick={() => onDone?.(name, cols)}>Готово</PrimaryBtn>
        </div>

        {/* Table */}
        <div className="rounded-[10px] overflow-hidden border border-white/30 mb-6">
          <table className="w-full text-[13px]">
            <thead className="bg-cardbg">
              <tr>
                <th className="text-left font-semibold text-primary px-4 py-3 w-[200px]">Название</th>
                <th className="text-left font-semibold text-primary px-4 py-3 w-[140px]">Тип</th>
                <th className="text-center font-semibold text-primary px-4 py-3 w-[60px]">Ключ</th>
                <th className="text-center font-semibold text-primary px-4 py-3 w-[60px]">Метка</th>
                <th className="text-center font-semibold text-primary px-4 py-3 w-[60px]">Формула</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {cols.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-[13px] text-primary/40">
                    Нет полей. Нажмите «Добавить вирт. столбец» чтобы добавить.
                  </td>
                </tr>
              )}
              {cols.map((col, i) => (
                <tr key={col.id} className={cn("border-t border-white/30", i % 2 === 0 ? "bg-mainbg" : "bg-mainbg/60")}>
                  <td className="px-4 py-2">
                    <input
                      value={col.name}
                      onChange={(e) => updateCol(col.id, { name: e.target.value })}
                      className="w-full bg-transparent outline-none text-[14px] text-primary"
                    />
                  </td>
                  <td className="px-4 py-2">
                    <InlineTypeDropdown
                      value={col.type}
                      onChange={(v) => updateCol(col.id, { type: v })}
                    />
                  </td>
                  <td className="px-4 py-2 text-center">
                    <CircleCheck
                      checked={!!col.isKey}
                      onChange={(v) => updateCol(col.id, { isKey: v })}
                    />
                  </td>
                  <td className="px-4 py-2 text-center">
                    <CircleCheck
                      checked={!!col.isLabel}
                      onChange={(v) => updateCol(col.id, { isLabel: v })}
                    />
                  </td>
                  <td className="px-4 py-2 text-center">
                    <button
                      onClick={() => setFormulaColId(col.id)}
                      className={cn(
                        "w-7 h-7 rounded border text-[13px] font-medium transition-colors",
                        formulaColId === col.id
                          ? "border-cta bg-cta text-white"
                          : "border-cta/40 text-cta hover:bg-cta/10"
                      )}
                    >
                      =
                    </button>
                  </td>
                  <td className="px-2 py-2 text-center">
                    <button
                      onClick={() => deleteCol(col.id)}
                      className="w-6 h-6 flex items-center justify-center text-primary/30 hover:text-red-400 transition-colors mx-auto"
                      title="Удалить поле"
                    >
                      <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5">
                        <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                      </svg>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {formulaColId && (() => {
        const col = cols.find((c) => c.id === formulaColId);
        return (
          <FormulaAssistantInline
            columnName={col?.name ?? ""}
            availableColumns={cols.filter((c) => c.id !== formulaColId).map((c) => c.name)}
            onClose={() => setFormulaColId(null)}
            onSave={(expr) => {
              updateCol(formulaColId, { formula: expr } as Partial<TableColumn>);
              setFormulaColId(null);
            }}
          />
        );
      })()}
    </Overlay>
  );
}

function InlineTypeDropdown({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-[13px] text-primary hover:text-cta transition-colors"
      >
        {value} <span className={cn("text-[10px] transition-transform", open && "rotate-180")}>▾</span>
      </button>
      {open && (
        <div
          className="absolute left-0 top-full mt-1 z-30 bg-white rounded-[15px] p-[4px] flex flex-col min-w-[130px]"
          style={{ boxShadow: "6px 6px 16px rgba(0,0,0,0.2)" }}
        >
          {COLUMN_TYPES.map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => { onChange(opt); setOpen(false); }}
              className={cn(
                "w-full h-9 flex items-center px-4 rounded-btn text-[13px] text-left transition-colors",
                value === opt ? "bg-cta/10 text-cta" : "text-primary hover:bg-mainbg"
              )}
            >
              {opt}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function CircleCheck({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={cn(
        "w-5 h-5 rounded-full border-2 mx-auto flex items-center justify-center transition-colors",
        checked ? "border-cta bg-cta" : "border-primary/30 bg-transparent"
      )}
    >
      {checked && (
        <svg viewBox="0 0 10 10" fill="none" className="w-3 h-3">
          <path d="M2 5L4 7L8 3" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  );
}

/* ─────────────────────────────────────────────────
   2. EditColumnModal
───────────────────────────────────────────────── */

export interface ColumnOptions {
  formula: string;
  isRequired: boolean;
  isUnique: boolean;
  formVisible: boolean;
  defaultValue: string;
  autoUpdateDate: boolean;
  choices: { value: string; label: string }[];
  minValue: string;
  maxValue: string;
  maxLength: string;
  // relation-specific
  targetEntityId: string;
  relationType: string;
}

export function EditColumnModal({
  source,
  columnName,
  columnType,
  entities,
  availableColumns = [],
  onClose,
  onGoToData,
  onDone,
}: {
  source: string;
  columnName: string;
  columnType: string;
  entities?: { id: string; display_name: string }[];
  availableColumns?: string[];
  onClose: () => void;
  onGoToData?: () => void;
  onDone?: (name: string, type: string, opts: ColumnOptions) => void;
}) {
  const [name, setName] = useState(columnName);
  const [type, setType] = useState(columnType);
  const [formula, setFormula] = useState("");
  const [showFormula, setShowFormula] = useState(false);
  const [openSection, setOpenSection] = useState<string | null>(null);

  // validation
  const [isRequired, setIsRequired] = useState(false);
  const [isUnique, setIsUnique] = useState(false);
  const [minValue, setMinValue] = useState("");
  const [maxValue, setMaxValue] = useState("");
  const [maxLength, setMaxLength] = useState("");

  // display
  const [formVisible, setFormVisible] = useState(true);

  // auto-compute
  const [defaultValue, setDefaultValue] = useState("");
  const [autoUpdateDate, setAutoUpdateDate] = useState(false);

  // choices (for select)
  const [choices, setChoices] = useState<{ value: string; label: string }[]>([]);
  const [newChoiceLabel, setNewChoiceLabel] = useState("");

  // relation
  const [targetEntityId, setTargetEntityId] = useState("");
  const [relationType, setRelationType] = useState("one_to_many");

  function addChoice() {
    const label = newChoiceLabel.trim();
    if (!label) return;
    const value = label.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "");
    setChoices((prev) => [...prev, { value: value || `opt_${prev.length + 1}`, label }]);
    setNewChoiceLabel("");
  }

  function removeChoice(idx: number) {
    setChoices((prev) => prev.filter((_, i) => i !== idx));
  }

  const fieldType = COLUMN_TYPE_TO_FIELD_TYPE[type] ?? "text";
  const isSelectType = fieldType === "select" || fieldType === "multi_select";
  const isNumericType = fieldType === "number" || fieldType === "decimal";
  const isTextType = fieldType === "text" || fieldType === "long_text";
  const isDateType = fieldType === "date" || fieldType === "datetime";

  const isRelationType = fieldType === "relation";

  function getOpts(): ColumnOptions {
    return { formula, isRequired, isUnique, formVisible, defaultValue, autoUpdateDate, choices, minValue, maxValue, maxLength, targetEntityId, relationType };
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 580 }} className="px-10 pb-8 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-start justify-between pt-[30px] mb-2">
          <div>
            <h2 className="text-[20px] font-bold text-primary">
              {source}: {name || columnName}
            </h2>
            <p className="text-[14px] text-primary/60 mt-1">Тип: {type}</p>
          </div>
          <CloseBtn onClick={onClose} />
        </div>

        {/* Action buttons */}
        <div className="flex gap-[10px] mb-6">
          <OutlineBtn onClick={onGoToData}>Перейти к данным</OutlineBtn>
          <PrimaryBtn onClick={() => onDone?.(name, type, getOpts())}>Готово</PrimaryBtn>
        </div>

        {/* Fields */}
        <div className="flex flex-col gap-4 mb-6">
          {/* Название */}
          <div className="flex items-center gap-4">
            <span className="text-[14px] text-primary/70 w-[160px] shrink-0">Название столбца</span>
            <BlueField>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full bg-transparent outline-none text-[16px] text-primary"
              />
            </BlueField>
          </div>

          {/* Формула */}
          <div className="flex items-center gap-4">
            <span className="text-[14px] text-primary/70 w-[160px] shrink-0">Формула</span>
            <BlueField className="flex-1">
              <button
                type="button"
                onClick={() => setShowFormula(true)}
                className="w-full flex items-center justify-between text-[16px] text-left"
              >
                <span className={formula ? "text-primary font-mono text-[13px]" : "text-primary/40"}>
                  {formula || "= Нажмите для ввода формулы"}
                </span>
                <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-primary/40">
                  <path d="M2 4h12M5 8h6M7 12h2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
              </button>
            </BlueField>
          </div>

          {/* Показать в форме */}
          <div className="flex items-center gap-4">
            <span className="text-[14px] text-primary/70 w-[160px] shrink-0">Показать в форме</span>
            <div className="flex items-center gap-3 h-[41px] bg-cardbg rounded-btn px-5 flex-1">
              <Toggle checked={formVisible} onChange={setFormVisible} />
              <span className="text-[13px] text-primary/50 ml-2">
                {formVisible ? "Отображается в форме создания" : "Скрыто в форме"}
              </span>
            </div>
          </div>

          {/* Тип */}
          <div className="flex items-center gap-4">
            <span className="text-[14px] text-primary/70 w-[160px] shrink-0">Тип</span>
            <div className="flex-1">
              <SimpleDropdown value={type} options={COLUMN_TYPES} onChange={setType} />
            </div>
          </div>
        </div>

        {/* Accordion sections */}
        <div className="flex flex-col gap-[2px]">

          {/* 1. Сведения о типе данных */}
          <AccordionSection
            title="Сведения о типе данных"
            open={openSection === "Сведения о типе данных"}
            onToggle={() => setOpenSection(openSection === "Сведения о типе данных" ? null : "Сведения о типе данных")}
          >
            {isSelectType && (
              <div className="flex flex-col gap-3">
                <p className="text-[13px] text-primary/60">Варианты списка:</p>
                <div className="flex flex-col gap-2">
                  {choices.map((c, i) => (
                    <div key={i} className="flex items-center gap-2 bg-cardbg rounded-[8px] px-3 py-2">
                      <span className="flex-1 text-[13px] text-primary">{c.label}</span>
                      <span className="text-[11px] text-primary/40 font-mono">{c.value}</span>
                      <button onClick={() => removeChoice(i)} className="text-primary/30 hover:text-red-400 transition-colors ml-1">
                        <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5">
                          <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
                <div className="flex gap-2">
                  <BlueField className="flex-1">
                    <input
                      value={newChoiceLabel}
                      onChange={(e) => setNewChoiceLabel(e.target.value)}
                      placeholder="Новый вариант"
                      className="w-full bg-transparent outline-none text-[14px] text-primary placeholder-primary/40"
                      onKeyDown={(e) => e.key === "Enter" && addChoice()}
                    />
                  </BlueField>
                  <button onClick={addChoice}
                    className="px-4 h-[41px] bg-cta rounded-btn text-white text-[13px] hover:bg-active transition-colors whitespace-nowrap">
                    + Добавить
                  </button>
                </div>
              </div>
            )}
            {isNumericType && (
              <div className="flex flex-col gap-3">
                <p className="text-[13px] text-primary/60">Числовое поле. Хранит целые{fieldType === "decimal" ? " и дробные" : ""} значения.</p>
              </div>
            )}
            {isDateType && (
              <p className="text-[13px] text-primary/60">
                {fieldType === "date" ? "Хранит дату в формате YYYY-MM-DD." : "Хранит дату и время с временной зоной."}
              </p>
            )}
            {fieldType === "boolean" && (
              <p className="text-[13px] text-primary/60">Логическое поле — Да / Нет.</p>
            )}
            {isRelationType && (
              <div className="flex flex-col gap-4">
                <div className="flex flex-col gap-[6px]">
                  <label className="text-[13px] text-primary/70">Целевая таблица</label>
                  <SimpleDropdown
                    value={(entities ?? []).find((e) => e.id === targetEntityId)?.display_name ?? ""}
                    options={(entities ?? []).map((e) => e.display_name)}
                    onChange={(name) => {
                      const found = (entities ?? []).find((e) => e.display_name === name);
                      if (found) setTargetEntityId(found.id);
                    }}
                    placeholder="Выберите таблицу..."
                  />
                </div>
                <div className="flex flex-col gap-[6px]">
                  <label className="text-[13px] text-primary/70">Тип связи</label>
                  <SimpleDropdown
                    value={{ one_to_one: "Один к одному", one_to_many: "Один ко многим", many_to_many: "Многие ко многим" }[relationType] ?? relationType}
                    options={["Один к одному", "Один ко многим", "Многие ко многим"]}
                    onChange={(label) => {
                      const map: Record<string, string> = { "Один к одному": "one_to_one", "Один ко многим": "one_to_many", "Многие ко многим": "many_to_many" };
                      setRelationType(map[label] ?? "one_to_many");
                    }}
                  />
                </div>
                <p className="text-[12px] text-primary/50 leading-relaxed">
                  Связь создаёт поле-ссылку между таблицами. Значения записываются как ID связанной записи.
                </p>
              </div>
            )}
            {!isSelectType && !isNumericType && !isDateType && fieldType !== "boolean" && !isRelationType && (
              <p className="text-[13px] text-primary/60">Текстовое поле типа «{type}».</p>
            )}
          </AccordionSection>

          {/* 2. Автоматическое вычисление */}
          <AccordionSection
            title="Автоматическое вычисление"
            open={openSection === "Автоматическое вычисление"}
            onToggle={() => setOpenSection(openSection === "Автоматическое вычисление" ? null : "Автоматическое вычисление")}
          >
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-[6px]">
                <label className="text-[13px] text-primary/70">Значение по умолчанию</label>
                <BlueField>
                  <input
                    value={defaultValue}
                    onChange={(e) => setDefaultValue(e.target.value)}
                    placeholder={isDateType ? "now()" : isNumericType ? "0" : "пусто"}
                    className="w-full bg-transparent outline-none text-[14px] text-primary placeholder-primary/40"
                  />
                </BlueField>
              </div>
              {isDateType && (
                <div className="flex items-center justify-between">
                  <span className="text-[13px] text-primary">Обновлять дату при изменении записи</span>
                  <Toggle checked={autoUpdateDate} onChange={setAutoUpdateDate} />
                </div>
              )}
              <div className="flex flex-col gap-[6px]">
                <label className="text-[13px] text-primary/70">Формула вычисления</label>
                <button
                  type="button"
                  onClick={() => setShowFormula(true)}
                  className="w-full h-[41px] bg-cardbg rounded-btn px-5 flex items-center justify-between text-[14px] text-primary/40 hover:text-primary transition-colors"
                >
                  <span>{formula || "= Не задана"}</span>
                  <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4">
                    <path d="M2 4h12M5 8h6M7 12h2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                  </svg>
                </button>
              </div>
            </div>
          </AccordionSection>

          {/* 3. Обновлённое поведение */}
          <AccordionSection
            title="Обновлённое поведение"
            open={openSection === "Обновлённое поведение"}
            onToggle={() => setOpenSection(openSection === "Обновлённое поведение" ? null : "Обновлённое поведение")}
          >
            <div className="flex flex-col gap-3">
              {isDateType && (
                <div className="flex items-center justify-between">
                  <span className="text-[13px] text-primary">Устанавливать текущую дату/время при обновлении</span>
                  <Toggle checked={autoUpdateDate} onChange={setAutoUpdateDate} />
                </div>
              )}
              {!isDateType && (
                <p className="text-[13px] text-primary/50">Для этого типа поля особое поведение при обновлении не предусмотрено.</p>
              )}
            </div>
          </AccordionSection>

          {/* 4. Валидность данных */}
          <AccordionSection
            title="Валидность данных"
            open={openSection === "Валидность данных"}
            onToggle={() => setOpenSection(openSection === "Валидность данных" ? null : "Валидность данных")}
          >
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-primary">Обязательное поле</span>
                <Toggle checked={isRequired} onChange={setIsRequired} />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-primary">Уникальное значение</span>
                <Toggle checked={isUnique} onChange={setIsUnique} />
              </div>
              {isNumericType && (
                <>
                  <div className="flex items-center gap-3">
                    <label className="text-[13px] text-primary/70 w-[80px] shrink-0">Минимум</label>
                    <BlueField>
                      <input type="number" value={minValue} onChange={(e) => setMinValue(e.target.value)}
                        placeholder="без ограничения"
                        className="w-full bg-transparent outline-none text-[14px] text-primary placeholder-primary/40" />
                    </BlueField>
                  </div>
                  <div className="flex items-center gap-3">
                    <label className="text-[13px] text-primary/70 w-[80px] shrink-0">Максимум</label>
                    <BlueField>
                      <input type="number" value={maxValue} onChange={(e) => setMaxValue(e.target.value)}
                        placeholder="без ограничения"
                        className="w-full bg-transparent outline-none text-[14px] text-primary placeholder-primary/40" />
                    </BlueField>
                  </div>
                </>
              )}
              {isTextType && (
                <div className="flex items-center gap-3">
                  <label className="text-[13px] text-primary/70 w-[80px] shrink-0">Макс. длина</label>
                  <BlueField>
                    <input type="number" value={maxLength} onChange={(e) => setMaxLength(e.target.value)}
                      placeholder="без ограничения"
                      className="w-full bg-transparent outline-none text-[14px] text-primary placeholder-primary/40" />
                  </BlueField>
                </div>
              )}
            </div>
          </AccordionSection>

          {/* 5. Отображение */}
          <AccordionSection
            title="Отображение"
            open={openSection === "Отображение"}
            onToggle={() => setOpenSection(openSection === "Отображение" ? null : "Отображение")}
          >
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-primary">Видимость в форме создания / редактирования</span>
                <Toggle checked={formVisible} onChange={setFormVisible} />
              </div>
              <p className="text-[12px] text-primary/50">
                Управляет показом поля в форме. Тонкая настройка типа отображения — в разделе «Источники данных».
              </p>
            </div>
          </AccordionSection>

        </div>
      </div>

      {showFormula && (
        <FormulaAssistantInline
          columnName={name || columnName}
          availableColumns={availableColumns}
          onClose={() => setShowFormula(false)}
          onSave={(expr) => { setFormula(expr); setShowFormula(false); }}
        />
      )}
    </Overlay>
  );
}

function AccordionSection({
  title, open, onToggle, children,
}: {
  title: string; open: boolean; onToggle: () => void; children: React.ReactNode;
}) {
  return (
    <div className="border-t border-white/30">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between py-3 text-[14px] font-medium text-primary hover:text-cta transition-colors"
      >
        <span>{title}</span>
        <span className={cn("text-[10px] transition-transform", open && "rotate-90")}>▶</span>
      </button>
      {open && <div className="pb-4 px-1">{children}</div>}
    </div>
  );
}

/* ─────────────────────────────────────────────────
   4. AddDataModal
───────────────────────────────────────────────── */

export function AddDataModal({
  onClose,
  onImport,
  onConnect,
  onManual,
}: {
  onClose: () => void;
  onImport?: () => void;
  onConnect?: () => void;
  onManual?: () => void;
}) {
  const options = [
    { icon: "📊", label: "Импортировать из CSV / Excel", onClick: onImport },
    { icon: "🔗", label: "Подключить внешний источник", onClick: onConnect },
    { icon: "✏️", label: "Ввести вручную", onClick: onManual },
  ];

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 505 }} className="px-10 pb-8">
        <div className="flex items-center justify-between pt-[30px] mb-6">
          <h2 className="text-[18px] font-bold text-primary">Добавить данные</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-3 mb-2">
          {options.map((opt) => (
            <button
              key={opt.label}
              onClick={() => { opt.onClick?.(); onClose(); }}
              className="flex items-center gap-4 px-5 py-4 rounded-[10px] bg-mainbg hover:bg-cardbg transition-colors text-left"
            >
              <span className="text-2xl">{opt.icon}</span>
              <span className="text-[16px] font-medium text-primary">{opt.label}</span>
            </button>
          ))}
        </div>
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   5. NewDataResourceModal
───────────────────────────────────────────────── */

const SOURCE_TYPES = ["Google Sheets", "Excel", "CSV", "REST API", "Другое"];
const NO_URL_TYPES = ["Excel", "CSV"];

export function NewDataResourceModal({
  onClose,
  onConfirm,
}: {
  onClose: () => void;
  onConfirm: (name: string, type: string, url: string) => void;
}) {
  const [name, setName] = useState("");
  const [type, setType] = useState("");
  const [url, setUrl] = useState("");

  const showUrl = type && !NO_URL_TYPES.includes(type);

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 505 }} className="px-10 pb-8">
        <div className="flex items-center justify-between pt-[30px] mb-6">
          <h2 className="text-[18px] font-bold text-primary">Новый источник данных</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-4 mb-6">
          <div className="flex flex-col gap-[8px]">
            <label className="text-[14px] text-primary font-medium">Название источника</label>
            <BlueField>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Мой источник данных"
                className="w-full bg-transparent outline-none text-[16px] text-primary placeholder-primary/40"
              />
            </BlueField>
          </div>

          <div className="flex flex-col gap-[8px]">
            <label className="text-[14px] text-primary font-medium">Тип источника</label>
            <SimpleDropdown value={type} options={SOURCE_TYPES} onChange={setType} placeholder="Выберите тип..." />
          </div>

          {showUrl && (
            <div className="flex flex-col gap-[8px]">
              <label className="text-[14px] text-primary font-medium">URL / путь</label>
              <BlueField>
                <input
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://..."
                  className="w-full bg-transparent outline-none text-[16px] text-primary placeholder-primary/40"
                />
              </BlueField>
            </div>
          )}
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm(name, type, url)}
          confirmLabel="Добавить источник"
          disabled={!name.trim() || !type}
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   6. AttachmentTemplateModal
───────────────────────────────────────────────── */

const FILE_TYPES = ["Изображения", "PDF", "Документы", "Видео", "Аудио"];

export function AttachmentTemplateModal({
  onClose,
  onConfirm,
}: {
  onClose: () => void;
  onConfirm?: (data: { templateName: string; fileTypes: string[]; maxSizeMb: string; multiple: boolean }) => void;
}) {
  const [templateName, setTemplateName] = useState("");
  const [fileTypes, setFileTypes] = useState<string[]>([]);
  const [maxSize, setMaxSize] = useState("10");
  const [multiple, setMultiple] = useState(false);

  function toggleFileType(ft: string) {
    setFileTypes((prev) => prev.includes(ft) ? prev.filter((x) => x !== ft) : [...prev, ft]);
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 505 }} className="px-10 pb-8">
        <div className="flex items-center justify-between pt-[30px] mb-6">
          <h2 className="text-[18px] font-bold text-primary">Шаблон вложений</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-4 mb-6">
          <div className="flex flex-col gap-[8px]">
            <label className="text-[14px] text-primary font-medium">Название шаблона</label>
            <BlueField>
              <input
                value={templateName}
                onChange={(e) => setTemplateName(e.target.value)}
                placeholder="Шаблон вложений"
                className="w-full bg-transparent outline-none text-[16px] text-primary placeholder-primary/40"
              />
            </BlueField>
          </div>

          <div className="flex flex-col gap-[10px]">
            <label className="text-[14px] text-primary font-medium">Тип файлов</label>
            <div className="flex flex-wrap gap-[8px]">
              {FILE_TYPES.map((ft) => (
                <button
                  key={ft}
                  type="button"
                  onClick={() => toggleFileType(ft)}
                  className={cn(
                    "px-4 h-[34px] rounded-btn border-2 text-[13px] font-medium transition-colors",
                    fileTypes.includes(ft)
                      ? "border-cta bg-cta/10 text-cta"
                      : "border-primary/20 text-primary/60 hover:border-cta/50"
                  )}
                >
                  {ft}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-[8px]">
            <label className="text-[14px] text-primary font-medium">Максимальный размер</label>
            <BlueField>
              <input
                value={maxSize}
                onChange={(e) => setMaxSize(e.target.value)}
                type="number"
                min="1"
                className="w-full bg-transparent outline-none text-[16px] text-primary"
              />
              <span className="text-[14px] text-primary/50 shrink-0">МБ</span>
            </BlueField>
          </div>

          <div className="flex items-center justify-between">
            <label className="text-[14px] text-primary font-medium">Разрешить несколько файлов</label>
            <Toggle checked={multiple} onChange={setMultiple} />
          </div>
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm?.({ templateName, fileTypes, maxSizeMb: maxSize, multiple })}
          confirmLabel="Сохранить"
          disabled={!templateName.trim()}
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   7. TableSettingsModal
───────────────────────────────────────────────── */

export function TableSettingsModal({
  tableName,
  onClose,
  onConfirm,
  onDelete,
}: {
  tableName: string;
  onClose: () => void;
  onConfirm?: (data: { name: string; description: string; requireAuth: boolean; readOnly: boolean }) => void;
  onDelete?: () => void;
}) {
  const [name, setName] = useState(tableName);
  const [description, setDescription] = useState("");
  const [requireAuth, setRequireAuth] = useState(false);
  const [readOnly, setReadOnly] = useState(false);

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 505 }} className="px-10 pb-8">
        <div className="flex items-center justify-between pt-[30px] mb-6">
          <h2 className="text-[18px] font-bold text-primary">Настройки таблицы: {tableName}</h2>
          <CloseBtn onClick={onClose} />
        </div>

        {/* Общие */}
        <div className="mb-5">
          <h3 className="text-[15px] font-semibold text-primary mb-3">Общие</h3>
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-[6px]">
              <label className="text-[13px] text-primary/70">Имя таблицы</label>
              <BlueField>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full bg-transparent outline-none text-[16px] text-primary"
                />
              </BlueField>
            </div>
            <div className="flex flex-col gap-[6px]">
              <label className="text-[13px] text-primary/70">Описание</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                className="w-full bg-cardbg rounded-[10px] px-5 py-3 text-[15px] text-primary outline-none resize-none placeholder-primary/40"
                placeholder="Описание таблицы..."
              />
            </div>
          </div>
        </div>

        {/* Безопасность */}
        <div className="mb-5">
          <h3 className="text-[15px] font-semibold text-primary mb-3">Безопасность</h3>
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-[14px] text-primary">Требовать аутентификацию</span>
              <Toggle checked={requireAuth} onChange={setRequireAuth} />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[14px] text-primary">Только для чтения</span>
              <Toggle checked={readOnly} onChange={setReadOnly} />
            </div>
          </div>
        </div>

        {/* Удаление */}
        <div className="mb-6">
          <h3 className="text-[15px] font-semibold text-primary mb-3">Удаление</h3>
          <button
            onClick={onDelete}
            className="px-4 h-[34px] border-2 border-red-400 rounded-btn text-red-500 text-[13px] font-medium hover:bg-red-50 transition-colors"
          >
            Удалить таблицу
          </button>
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm?.({ name, description, requireAuth, readOnly })}
          confirmLabel="Сохранить"
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   8. DbDescriptionModal
───────────────────────────────────────────────── */

export function DbDescriptionModal({
  name: initialName,
  description: initialDescription,
  onClose,
  onConfirm,
}: {
  name: string;
  description: string;
  onClose: () => void;
  onConfirm?: (name: string, description: string, tags: string) => void;
}) {
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription);
  const [tags, setTags] = useState("");

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 505 }} className="px-10 pb-8">
        <div className="flex items-center justify-between pt-[30px] mb-6">
          <h2 className="text-[18px] font-bold text-primary">Описание базы данных</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-4 mb-6">
          <div className="flex flex-col gap-[8px]">
            <label className="text-[14px] text-primary font-medium">Название</label>
            <BlueField>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full bg-transparent outline-none text-[16px] text-primary"
              />
            </BlueField>
          </div>

          <div className="flex flex-col gap-[8px]">
            <label className="text-[14px] text-primary font-medium">Описание</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full bg-cardbg rounded-[10px] px-5 py-3 text-[15px] text-primary outline-none resize-none placeholder-primary/40"
              placeholder="Краткое описание базы данных..."
            />
          </div>

          <div className="flex flex-col gap-[8px]">
            <label className="text-[14px] text-primary font-medium">Теги</label>
            <BlueField>
              <input
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="тег1, тег2, тег3"
                className="w-full bg-transparent outline-none text-[16px] text-primary placeholder-primary/40"
              />
            </BlueField>
          </div>
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm?.(name, description, tags)}
          confirmLabel="Сохранить"
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   9. ChangeDbOwnerModal
───────────────────────────────────────────────── */

export function ChangeDbOwnerModal({
  currentOwner,
  onClose,
  onConfirm,
}: {
  currentOwner: string;
  onClose: () => void;
  onConfirm?: (email: string) => void;
}) {
  const [email, setEmail] = useState("");

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 505 }} className="px-10 pb-8">
        <div className="flex items-center justify-between pt-[30px] mb-4">
          <h2 className="text-[18px] font-bold text-primary">Изменить владельца</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <p className="text-[14px] text-primary/60 mb-5">
          Текущий владелец: <span className="font-medium text-primary">{currentOwner}</span>
        </p>

        <div className="flex flex-col gap-[8px] mb-5">
          <label className="text-[14px] text-primary font-medium">Email нового владельца</label>
          <BlueField>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              placeholder="email@example.com"
              className="w-full bg-transparent outline-none text-[16px] text-primary placeholder-primary/40"
            />
          </BlueField>
        </div>

        <div
          className="flex items-start gap-3 rounded-[10px] px-4 py-3 mb-6"
          style={{ background: "#EBF4FF" }}
        >
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 shrink-0 mt-0.5 text-cta">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
          </svg>
          <p className="text-[14px] text-cta leading-[1.5]">
            Текущий владелец потеряет права администратора
          </p>
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm?.(email)}
          confirmLabel="Передать права"
          disabled={!email.trim()}
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   10. CopyDbModal
───────────────────────────────────────────────── */

export function CopyDbModal({
  name,
  onClose,
  onConfirm,
}: {
  name: string;
  onClose: () => void;
  onConfirm?: (newName: string, withData: boolean, withSecurity: boolean) => void;
}) {
  const [newName, setNewName] = useState(`${name} — копия`);
  const [withData, setWithData] = useState(true);
  const [withSecurity, setWithSecurity] = useState(true);

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 505 }} className="px-10 pb-8">
        <div className="flex items-center justify-between pt-[30px] mb-6">
          <h2 className="text-[18px] font-bold text-primary">Копировать базу данных</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-4 mb-6">
          <div className="flex flex-col gap-[8px]">
            <label className="text-[14px] text-primary font-medium">Название копии</label>
            <BlueField>
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="w-full bg-transparent outline-none text-[16px] text-primary"
              />
            </BlueField>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-[14px] text-primary font-medium">Включить данные</span>
            <Toggle checked={withData} onChange={setWithData} />
          </div>

          <div className="flex items-center justify-between">
            <span className="text-[14px] text-primary font-medium">Включить настройки безопасности</span>
            <Toggle checked={withSecurity} onChange={setWithSecurity} />
          </div>
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm?.(newName, withData, withSecurity)}
          confirmLabel="Копировать"
          disabled={!newName.trim()}
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   11. ConfigurationModal
───────────────────────────────────────────────── */

type ConfigSection = "Общие" | "Безопасность" | "Производительность" | "Уведомления";

const CONFIG_SECTIONS: ConfigSection[] = ["Общие", "Безопасность", "Производительность", "Уведомления"];

const CONFIG_TOGGLES: Record<ConfigSection, string[]> = {
  "Общие": ["Публичный доступ", "Логирование"],
  "Безопасность": ["Шифрование", "Двухфакторная аутентификация"],
  "Производительность": ["Кэширование", "CDN"],
  "Уведомления": ["Email уведомления", "Webhook"],
};

export function ConfigurationModal({ onClose }: { onClose: () => void }) {
  const [activeSection, setActiveSection] = useState<ConfigSection>("Общие");
  const [toggles, setToggles] = useState<Record<string, boolean>>({});

  function setToggle(key: string, val: boolean) {
    setToggles((prev) => ({ ...prev, [key]: val }));
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 620 }} className="pb-8">
        <div className="flex items-center justify-between pt-[30px] px-10 mb-6">
          <h2 className="text-[18px] font-bold text-primary">Конфигурация</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex">
          {/* Left nav */}
          <div className="w-[160px] shrink-0 border-r border-white/30 flex flex-col gap-[2px] px-3 pb-6">
            {CONFIG_SECTIONS.map((section) => (
              <button
                key={section}
                onClick={() => setActiveSection(section)}
                className={cn(
                  "w-full text-left px-3 py-2 rounded-btn text-[14px] font-medium transition-colors",
                  activeSection === section
                    ? "bg-cta/10 text-cta"
                    : "text-primary/70 hover:bg-mainbg hover:text-primary"
                )}
              >
                {section}
              </button>
            ))}
          </div>

          {/* Right content */}
          <div className="flex-1 px-8">
            <h3 className="text-[15px] font-semibold text-primary mb-4">{activeSection}</h3>
            <div className="flex flex-col gap-4">
              {CONFIG_TOGGLES[activeSection].map((label) => (
                <div key={label} className="flex items-center justify-between">
                  <span className="text-[14px] text-primary">{label}</span>
                  <Toggle
                    checked={!!toggles[label]}
                    onChange={(v) => setToggle(label, v)}
                  />
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="flex justify-end px-10 mt-6">
          <PrimaryBtn onClick={onClose}>Готово</PrimaryBtn>
        </div>
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   12. ColumnsModal
───────────────────────────────────────────────── */

export interface ColumnItem {
  id: string;
  name: string;
  visible: boolean;
}

export function ColumnsModal({
  columns: initialColumns,
  onClose,
  onSave,
}: {
  columns: ColumnItem[];
  onClose: () => void;
  onSave?: (columns: ColumnItem[]) => void;
}) {
  const [columns, setColumns] = useState<ColumnItem[]>(initialColumns);

  function toggleVisible(id: string) {
    setColumns((prev) => prev.map((c) => (c.id === id ? { ...c, visible: !c.visible } : c)));
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 505 }} className="px-10 pb-8">
        <div className="flex items-center justify-between pt-[30px] mb-6">
          <h2 className="text-[18px] font-bold text-primary">Управление столбцами</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-[4px] mb-5">
          {columns.map((col) => (
            <div
              key={col.id}
              className="flex items-center gap-3 h-[44px] px-3 rounded-[8px] bg-mainbg hover:bg-cardbg/60 transition-colors cursor-grab"
            >
              {/* Drag handle */}
              <span className="w-4 h-4 text-primary/30 shrink-0">
                <svg viewBox="0 0 16 16" fill="none" className="w-full h-full">
                  <circle cx="6"  cy="4"  r="1.2" fill="currentColor" />
                  <circle cx="10" cy="4"  r="1.2" fill="currentColor" />
                  <circle cx="6"  cy="8"  r="1.2" fill="currentColor" />
                  <circle cx="10" cy="8"  r="1.2" fill="currentColor" />
                  <circle cx="6"  cy="12" r="1.2" fill="currentColor" />
                  <circle cx="10" cy="12" r="1.2" fill="currentColor" />
                </svg>
              </span>
              <Toggle checked={col.visible} onChange={() => toggleVisible(col.id)} />
              <span className="flex-1 text-[14px] text-primary">{col.name}</span>
            </div>
          ))}
        </div>

        <button className="w-full flex items-center gap-2 h-[41px] border-2 border-dashed border-cta/40 rounded-btn text-cta/70 text-[14px] hover:border-cta hover:text-cta transition-colors mb-6 justify-center">
          <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4">
            <path d="M8 2v12M2 8h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          Добавить столбец
        </button>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onSave?.(columns)}
          confirmLabel="Сохранить"
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   13. NewSliceModal
───────────────────────────────────────────────── */

export function NewSliceModal({
  tables,
  columns,
  onClose,
  onConfirm,
}: {
  tables: string[];
  columns: string[];
  onClose: () => void;
  onConfirm?: (name: string, source: string, filter: string, selectedColumns: string[]) => void;
}) {
  const [name, setName] = useState("");
  const [source, setSource] = useState("");
  const [filter, setFilter] = useState("=");
  const [selectedCols, setSelectedCols] = useState<string[]>([]);

  function toggleCol(col: string) {
    setSelectedCols((prev) => prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col]);
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 505 }} className="px-10 pb-8">
        <div className="flex items-center justify-between pt-[30px] mb-6">
          <h2 className="text-[18px] font-bold text-primary">Новый срез данных</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-4 mb-6">
          <div className="flex flex-col gap-[8px]">
            <label className="text-[14px] text-primary font-medium">Название среза</label>
            <BlueField>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Мой срез"
                className="w-full bg-transparent outline-none text-[16px] text-primary placeholder-primary/40"
              />
            </BlueField>
          </div>

          <div className="flex flex-col gap-[8px]">
            <label className="text-[14px] text-primary font-medium">Источник данных</label>
            <SimpleDropdown
              value={source}
              options={tables}
              onChange={setSource}
              placeholder="Выберите таблицу..."
            />
          </div>

          <div className="flex flex-col gap-[8px]">
            <label className="text-[14px] text-primary font-medium">Условие фильтра</label>
            <BlueField>
              <input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="w-full bg-transparent outline-none text-[16px] text-primary font-mono"
              />
            </BlueField>
          </div>

          {columns.length > 0 && (
            <div className="flex flex-col gap-[10px]">
              <label className="text-[14px] text-primary font-medium">Столбцы</label>
              <div className="flex flex-col gap-[6px] max-h-[160px] overflow-y-auto">
                {columns.map((col) => (
                  <label key={col} className="flex items-center gap-3 cursor-pointer hover:text-cta transition-colors">
                    <input
                      type="checkbox"
                      checked={selectedCols.includes(col)}
                      onChange={() => toggleCol(col)}
                      className="w-4 h-4 accent-cta"
                    />
                    <span className="text-[14px] text-primary">{col}</span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm?.(name, source, filter, selectedCols)}
          confirmLabel="Создать"
          disabled={!name.trim() || !source}
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   14. DbSettingsModal
───────────────────────────────────────────────── */

type DbSettingsTab = "Общие" | "Безопасность" | "Дополнительно";
const DB_SETTINGS_TABS: DbSettingsTab[] = ["Общие", "Безопасность", "Дополнительно"];

export function DbSettingsModal({
  name: initialName,
  onClose,
  onSave,
}: {
  name: string;
  onClose: () => void;
  onSave?: (data: Record<string, unknown>) => void;
}) {
  const [tab, setTab] = useState<DbSettingsTab>("Общие");
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState("");
  const [emoji, setEmoji] = useState("🗄️");
  const [auth, setAuth] = useState(false);
  const [ssl, setSsl] = useState(true);
  const [audit, setAudit] = useState(false);
  const [rowLimit, setRowLimit] = useState("10000");
  const [retention, setRetention] = useState("365");

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 580 }} className="px-10 pb-8">
        <div className="flex items-center justify-between pt-[30px] mb-5">
          <h2 className="text-[18px] font-bold text-primary">Настройки базы данных</h2>
          <CloseBtn onClick={onClose} />
        </div>

        {/* Tabs */}
        <div className="flex gap-[6px] mb-6">
          {DB_SETTINGS_TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "px-5 h-[34px] rounded-btn text-[14px] font-medium transition-colors",
                tab === t ? "bg-cta text-white" : "bg-mainbg text-primary hover:bg-cardbg"
              )}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {tab === "Общие" && (
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-[8px]">
              <label className="text-[14px] text-primary font-medium">Иконка</label>
              <BlueField className="w-[80px]">
                <input
                  value={emoji}
                  onChange={(e) => setEmoji(e.target.value)}
                  className="w-full bg-transparent outline-none text-[22px] text-center"
                />
              </BlueField>
            </div>
            <div className="flex flex-col gap-[8px]">
              <label className="text-[14px] text-primary font-medium">Имя</label>
              <BlueField>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full bg-transparent outline-none text-[16px] text-primary"
                />
              </BlueField>
            </div>
            <div className="flex flex-col gap-[8px]">
              <label className="text-[14px] text-primary font-medium">Описание</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                className="w-full bg-cardbg rounded-[10px] px-5 py-3 text-[15px] text-primary outline-none resize-none placeholder-primary/40"
                placeholder="Описание базы данных..."
              />
            </div>
          </div>
        )}

        {tab === "Безопасность" && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <span className="text-[14px] text-primary">Аутентификация</span>
              <Toggle checked={auth} onChange={setAuth} />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[14px] text-primary">SSL</span>
              <Toggle checked={ssl} onChange={setSsl} />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[14px] text-primary">Аудит доступа</span>
              <Toggle checked={audit} onChange={setAudit} />
            </div>
          </div>
        )}

        {tab === "Дополнительно" && (
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-[8px]">
              <label className="text-[14px] text-primary font-medium">Лимит строк</label>
              <BlueField>
                <input
                  value={rowLimit}
                  onChange={(e) => setRowLimit(e.target.value)}
                  type="number"
                  min="1"
                  className="w-full bg-transparent outline-none text-[16px] text-primary"
                />
              </BlueField>
            </div>
            <div className="flex flex-col gap-[8px]">
              <label className="text-[14px] text-primary font-medium">Время хранения (дней)</label>
              <BlueField>
                <input
                  value={retention}
                  onChange={(e) => setRetention(e.target.value)}
                  type="number"
                  min="1"
                  className="w-full bg-transparent outline-none text-[16px] text-primary"
                />
              </BlueField>
            </div>
          </div>
        )}

        <div className="mt-6">
          <ModalButtons
            onCancel={onClose}
            onConfirm={() => onSave?.({ name, description, emoji, auth, ssl, audit, rowLimit, retention })}
            confirmLabel="Сохранить"
          />
        </div>
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   15. DbRolesModal
───────────────────────────────────────────────── */

export interface DbMember {
  email: string;
  role: string;
}

const DB_ROLES = ["Владелец", "Редактор", "Читатель"];

export function DbRolesModal({
  members: initialMembers,
  onClose,
  onSave,
}: {
  members: DbMember[];
  onClose: () => void;
  onSave?: (members: DbMember[]) => void;
}) {
  const [members, setMembers] = useState<DbMember[]>(initialMembers);
  const [newEmail, setNewEmail] = useState("");
  const [newRole, setNewRole] = useState("Редактор");

  function updateRole(email: string, role: string) {
    setMembers((prev) => prev.map((m) => (m.email === email ? { ...m, role } : m)));
  }

  function removeMember(email: string) {
    setMembers((prev) => prev.filter((m) => m.email !== email));
  }

  function addMember() {
    if (!newEmail.trim()) return;
    setMembers((prev) => [...prev, { email: newEmail.trim(), role: newRole }]);
    setNewEmail("");
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 620 }} className="px-10 pb-8">
        <div className="flex items-center justify-between pt-[30px] mb-6">
          <h2 className="text-[18px] font-bold text-primary">Роли в базе данных</h2>
          <CloseBtn onClick={onClose} />
        </div>

        {/* Members table */}
        <div className="flex flex-col gap-[4px] mb-5">
          {members.length === 0 && (
            <p className="text-[14px] text-primary/50 text-center py-4">Участников пока нет</p>
          )}
          {members.map((m) => (
            <div key={m.email} className="flex items-center gap-3 h-[44px] px-3 rounded-[8px] bg-mainbg">
              <div className="w-[28px] h-[28px] bg-cardbg rounded-full flex items-center justify-center text-[13px] font-medium text-cta shrink-0">
                {m.email[0].toUpperCase()}
              </div>
              <span className="flex-1 text-[14px] text-primary truncate">{m.email}</span>
              <div className="w-[130px] shrink-0">
                <InlineRoleDropdown value={m.role} onChange={(v) => updateRole(m.email, v)} />
              </div>
              <button
                onClick={() => removeMember(m.email)}
                className="w-6 h-6 flex items-center justify-center text-red-400 hover:text-red-600 transition-colors shrink-0"
              >
                <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4">
                  <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          ))}
        </div>

        {/* Add new member */}
        <div className="flex gap-[10px] items-center mb-6">
          <BlueField className="flex-1">
            <input
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              placeholder="email@example.com"
              className="w-full bg-transparent outline-none text-[15px] text-primary placeholder-primary/40"
              onKeyDown={(e) => e.key === "Enter" && addMember()}
            />
          </BlueField>
          <div className="w-[130px] shrink-0">
            <SimpleDropdown value={newRole} options={DB_ROLES} onChange={setNewRole} />
          </div>
          <button
            onClick={addMember}
            className="px-4 h-[41px] bg-cta rounded-btn text-white text-[14px] font-medium hover:bg-active transition-colors whitespace-nowrap"
          >
            + Добавить
          </button>
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onSave?.(members)}
          confirmLabel="Сохранить"
        />
      </div>
    </Overlay>
  );
}

function InlineRoleDropdown({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-[13px] text-primary hover:text-cta transition-colors"
      >
        {value} <span className={cn("text-[10px] transition-transform", open && "rotate-180")}>▾</span>
      </button>
      {open && (
        <div
          className="absolute right-0 top-full mt-1 z-30 bg-white rounded-[15px] p-[4px] flex flex-col min-w-[130px]"
          style={{ boxShadow: "6px 6px 16px rgba(0,0,0,0.2)" }}
        >
          {DB_ROLES.map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => { onChange(opt); setOpen(false); }}
              className={cn(
                "w-full h-9 flex items-center px-4 rounded-btn text-[13px] text-left transition-colors",
                value === opt ? "bg-cta/10 text-cta" : "text-primary hover:bg-mainbg"
              )}
            >
              {opt}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────
   16. ShareDbModal
───────────────────────────────────────────────── */

export function ShareDbModal({
  dbName,
  onClose,
}: {
  dbName: string;
  onClose: () => void;
}) {
  const [email, setEmail] = useState("");
  const [users, setUsers] = useState<DbMember[]>([]);
  const [linkCopied, setLinkCopied] = useState(false);

  function addUser() {
    if (!email.trim()) return;
    setUsers((prev) => [...prev, { email: email.trim(), role: "Редактор" }]);
    setEmail("");
  }

  function copyLink() {
    const url = typeof window !== "undefined" ? `${window.location.origin}/db/${encodeURIComponent(dbName)}` : "";
    void navigator.clipboard?.writeText(url).then(() => {
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 1500);
    });
  }

  return (
    <Overlay onClose={onClose} alignTop topOffset={85}>
      <div style={{ width: 620 }} className="px-10 flex flex-col gap-5">
        {/* Header */}
        <div className="flex flex-col gap-[10px] border-b-2 border-white pb-[5px]">
          <div className="flex justify-between items-start pt-[30px]">
            <div>
              <p className="text-[20px] font-bold text-primary leading-[150%]">
                Поделиться «{dbName}»
              </p>
              <p className="text-meta text-primary/70">{users.length} пользователей</p>
            </div>
            <CloseBtn onClick={onClose} />
          </div>

          {/* Email input */}
          <div className="flex gap-[10px]">
            <BlueField className="flex-1">
              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Добавить email"
                className="w-full bg-transparent outline-none text-[18px] text-primary placeholder-primary/50"
                onKeyDown={(e) => e.key === "Enter" && addUser()}
              />
            </BlueField>
            <button
              onClick={addUser}
              className="px-4 h-[41px] bg-cta rounded-btn text-white text-[14px] font-medium hover:bg-active transition-colors"
            >
              Пригласить
            </button>
          </div>
        </div>

        {/* Users list */}
        <div className="flex flex-col gap-[10px] min-h-[60px]">
          {users.length === 0 && (
            <p className="text-[14px] text-primary/40 text-center py-2">Добавьте участников выше</p>
          )}
          {users.map((u) => (
            <div key={u.email} className="flex justify-between items-center h-[34px]">
              <div className="flex items-center gap-[15px]">
                <div className="w-[34px] h-[34px] bg-cardbg rounded-full flex items-center justify-center text-[15px] font-medium text-cta shrink-0">
                  {u.email[0].toUpperCase()}
                </div>
                <span className="text-meta text-primary">{u.email}</span>
              </div>
              <div className="flex items-center gap-[10px]">
                <span className="text-[14px] text-primary">{u.role}</span>
                <span className="text-primary text-[10px]">▾</span>
              </div>
            </div>
          ))}
        </div>

        {/* Bottom buttons */}
        <div className="flex justify-between items-center py-[30px]">
          <button
            onClick={copyLink}
            className="flex items-center gap-[10px] px-5 py-[3px] h-[34px]
                       border-2 border-cta rounded-btn text-cta text-meta hover:bg-cta/10 transition-colors"
          >
            <svg viewBox="0 0 25 25" fill="none" className="w-[25px] h-[25px]">
              <path d="M10 8 C7 8 4 10 4 13 C4 16 7 18 10 18 L13 18" stroke="#35A7FF" strokeWidth="1.72" strokeLinecap="round" />
              <path d="M15 18 C18 18 21 16 21 13 C21 10 18 8 15 8 L12 8" stroke="#35A7FF" strokeWidth="1.72" strokeLinecap="round" />
              <line x1="9" y1="13" x2="16" y2="13" stroke="#35A7FF" strokeWidth="1.72" strokeLinecap="round" />
            </svg>
            <span>{linkCopied ? "Скопировано" : "Скопировать ссылку"}</span>
          </button>
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
   FormulaAssistantInline — встроен в EditTableModal
───────────────────────────────────────────────── */

const FORMULA_FUNCTIONS = [
  { name: "IF()",        desc: "Условие" },
  { name: "AND()",       desc: "Логическое И" },
  { name: "OR()",        desc: "Логическое ИЛИ" },
  { name: "CONCATENATE()", desc: "Объединить текст" },
  { name: "LEN()",       desc: "Длина строки" },
  { name: "TRIM()",      desc: "Убрать пробелы" },
  { name: "TODAY()",     desc: "Сегодняшняя дата" },
  { name: "NOW()",       desc: "Текущее время" },
  { name: "SUM()",       desc: "Сумма" },
  { name: "AVERAGE()",   desc: "Среднее" },
  { name: "MAX()",       desc: "Максимум" },
  { name: "MIN()",       desc: "Минимум" },
];

function FormulaAssistantInline({
  columnName,
  availableColumns = [],
  onClose,
  onSave,
}: {
  columnName: string;
  availableColumns?: string[];
  onClose: () => void;
  onSave: (expr: string) => void;
}) {
  const [expr, setExpr] = useState("=");
  const [tab, setTab] = useState<"example" | "explorer">("example");
  const [valid, setValid] = useState(true);

  function validate() {
    setValid(expr.startsWith("=") && expr.length > 1);
  }

  return (
    <div
      className="absolute inset-0 z-[60] flex items-end justify-center pb-6"
      style={{ background: "rgba(0,32,95,0.35)" }}
      onClick={onClose}
    >
      <div
        style={{ width: 680 }}
        className="bg-mainbg rounded-[10px] shadow-[0_8px_32px_rgba(0,0,0,0.25)] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-8 pt-6 pb-4 border-b border-cardbg">
          <div>
            <h3 className="text-[18px] font-bold text-primary">Помощник по формуле</h3>
            <p className="text-[13px] text-primary/50 mt-0.5">= [{columnName}]</p>
          </div>
          <button onClick={onClose} className="w-7 h-7 hover:opacity-60 transition-opacity">
            <svg viewBox="0 0 28 28" fill="none" className="w-full h-full">
              <line x1="7" y1="7" x2="21" y2="21" stroke="#00205F" strokeWidth="2" strokeLinecap="round"/>
              <line x1="21" y1="7" x2="7" y2="21" stroke="#00205F" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        <div className="px-8 py-5 flex flex-col gap-4">
          {/* Expression input */}
          <textarea
            value={expr}
            onChange={(e) => { setExpr(e.target.value); setValid(true); }}
            onBlur={validate}
            rows={3}
            className={cn(
              "w-full bg-cardbg rounded-[10px] px-5 py-3 text-[16px] text-primary outline-none resize-none placeholder-primary/40 border-2 transition-colors",
              valid ? "border-transparent focus:border-cta/40" : "border-red-400"
            )}
            placeholder="Начните с = для ввода формулы…"
          />

          {/* Validate row */}
          <div className="flex items-center gap-3">
            {valid ? (
              <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 shrink-0 text-green-500">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd"/>
              </svg>
            ) : (
              <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 shrink-0 text-red-400">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm-1-9h2v4h-2V9zm0 6h2v2h-2v-2z" clipRule="evenodd"/>
              </svg>
            )}
            <span className={cn("text-[13px]", valid ? "text-primary/50" : "text-red-400")}>
              {valid ? "Формула корректна" : "Формула должна начинаться с ="}
            </span>
            <button onClick={validate} className="ml-auto text-[13px] text-cta hover:underline flex items-center gap-1">
              Тест
              <svg viewBox="0 0 16 16" fill="none" className="w-3 h-3">
                <path d="M10 3h3v3M13 3L4 12" stroke="#35A7FF" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>

          {/* Tabs */}
          <div className="flex items-center gap-2">
            {(["example", "explorer"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn(
                  "h-[28px] px-5 rounded-[20px] text-[13px] font-medium transition-colors",
                  tab === t ? "bg-cta text-white" : "bg-cardbg text-primary hover:bg-cardbg/80"
                )}
              >
                {t === "example" ? "Пример" : "Проводник"}
              </button>
            ))}
          </div>

          {/* Tab content */}
          {tab === "example" ? (
            <div className="grid grid-cols-3 gap-2 max-h-[160px] overflow-y-auto">
              {FORMULA_FUNCTIONS.map((fn) => (
                <button
                  key={fn.name}
                  onClick={() => setExpr((prev) => (prev === "=" ? `=${fn.name}` : prev + fn.name))}
                  className="flex flex-col items-start px-3 py-2 rounded-[8px] bg-cardbg hover:bg-cta/10 hover:border-cta border border-transparent transition-colors text-left"
                >
                  <span className="text-[13px] font-semibold text-cta">{fn.name}</span>
                  <span className="text-[11px] text-primary/50">{fn.desc}</span>
                </button>
              ))}
            </div>
          ) : availableColumns.length > 0 ? (
            <div className="grid grid-cols-3 gap-2 max-h-[160px] overflow-y-auto">
              {availableColumns.map((col) => (
                <button
                  key={col}
                  onClick={() => setExpr((prev) => prev + `[${col}]`)}
                  className="flex flex-col items-start px-3 py-2 rounded-[8px] bg-cardbg hover:bg-cta/10 hover:border-cta border border-transparent transition-colors text-left"
                >
                  <span className="text-[13px] font-semibold text-primary">[{col}]</span>
                  <span className="text-[11px] text-primary/50">поле</span>
                </button>
              ))}
            </div>
          ) : (
            <p className="text-[13px] text-primary/40 text-center py-6">Нет доступных полей</p>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-1">
            <button
              onClick={onClose}
              className="px-5 h-[34px] border-2 border-cta rounded-btn text-cta text-[13px] hover:bg-cta/10 transition-colors"
            >
              Отмена
            </button>
            <button
              onClick={() => { if (expr.startsWith("=")) onSave(expr); else setValid(false); }}
              className="px-5 h-[34px] bg-cta border-2 border-cta rounded-btn text-white text-[13px] hover:bg-active transition-colors"
            >
              Сохранить
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────
   VirtualColumnModal — обновлённый (Figma 2610596)
───────────────────────────────────────────────── */

export function VirtualColumnModal({
  tableName = "Таблица",
  availableColumns = [],
  onClose,
  onDelete,
  onGoToData,
  onConfirm,
}: {
  tableName?: string;
  availableColumns?: string[];
  onClose: () => void;
  onDelete?: () => void;
  onGoToData?: () => void;
  onConfirm: (name: string, type: string, formula: string) => void;
}) {
  const [name, setName] = useState("");
  const [type, setType] = useState(COLUMN_TYPES[0]);
  const [formula, setFormula] = useState("");
  const [show, setShow] = useState(true);
  const [showFormula, setShowFormula] = useState(false);

  const colOptions = availableColumns.length
    ? availableColumns
    : ["План маркетингового проекта", "ID", "Название", "Статус", "Дата создания"];

  function FieldRow({
    label,
    desc,
    children,
  }: {
    label: string;
    desc: string;
    children: React.ReactNode;
  }) {
    return (
      <div className="flex items-start gap-6 py-4 border-b border-cardbg last:border-0">
        <div className="w-[200px] shrink-0">
          <p className="text-[14px] font-semibold text-primary">{label}</p>
          <p className="text-[12px] text-primary/50 mt-0.5 leading-snug">{desc}</p>
        </div>
        <div className="flex-1">{children}</div>
      </div>
    );
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 620 }} className="px-8 pb-6">
        {/* Header */}
        <div className="flex items-start justify-between pt-6 pb-4 border-b border-cardbg">
          <div className="flex items-center gap-2">
            <svg viewBox="0 0 20 20" fill="none" className="w-5 h-5 shrink-0">
              <rect x="2" y="2" width="16" height="16" rx="2" stroke="#35A7FF" strokeWidth="1.5"/>
              <path d="M2 7h16M7 7v11" stroke="#35A7FF" strokeWidth="1.5"/>
            </svg>
            <div>
              <h2 className="text-[17px] font-bold text-primary leading-tight">
                {tableName}: Новый виртуальный столбец
              </h2>
              <p className="text-[12px] text-primary/50 mt-0.5">Тип: {type || "Текст"}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0 ml-4">
            {onGoToData && (
              <button
                onClick={onGoToData}
                className="h-[30px] px-4 border border-cta rounded-btn text-cta text-[12px] hover:bg-cta/10 transition-colors whitespace-nowrap"
              >
                Перейти к данным
              </button>
            )}
            {onDelete && (
              <button
                onClick={onDelete}
                className="h-[30px] px-4 border border-red-400 rounded-btn text-red-400 text-[12px] hover:bg-red-50 transition-colors"
              >
                Удалить
              </button>
            )}
            <CloseBtn onClick={onClose} />
          </div>
        </div>

        {/* Fields */}
        <div className="flex flex-col">
          <FieldRow label="Название столбца" desc="Как будет называться ваш виртуальный столбец.">
            <BlueField>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Текст"
                className="w-full bg-transparent outline-none text-[15px] text-primary placeholder-primary/40"
              />
            </BlueField>
          </FieldRow>

          <FieldRow label="Тип" desc="Тип данных виртуального столбца.">
            <SimpleDropdown value={type} options={COLUMN_TYPES} onChange={setType} />
          </FieldRow>

          <FieldRow
            label="Формула"
            desc="Вместо того чтобы разрешать пользователю вводить данные, вычислите значение для столбца."
          >
            <div className="flex items-center gap-2">
              <div className="flex-1 relative">
                <SimpleDropdown
                  value={formula}
                  options={colOptions}
                  onChange={setFormula}
                  placeholder="Выберите столбец или формулу…"
                />
              </div>
              <button
                onClick={() => setShowFormula(true)}
                title="Помощник формул"
                className="w-[41px] h-[41px] shrink-0 border border-cta/40 rounded-btn text-cta text-[14px] hover:bg-cta/10 transition-colors flex items-center justify-center"
              >
                <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4">
                  <path d="M2 4h12M5 8h6M7 12h2" stroke="#35A7FF" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
              </button>
            </div>
          </FieldRow>

          <FieldRow label="Показать" desc="Отображать столбец пользователям приложения.">
            <div className="flex justify-start">
              <Toggle checked={show} onChange={setShow} />
            </div>
          </FieldRow>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3 pt-4">
          <button
            onClick={onClose}
            className="px-5 h-[34px] border-2 border-cta rounded-btn text-cta text-[13px] hover:bg-cta/10 transition-colors"
          >
            Отмена
          </button>
          <button
            onClick={() => onConfirm(name, type, formula)}
            disabled={!name.trim()}
            className="px-5 h-[34px] bg-cta border-2 border-cta rounded-btn text-white text-[13px] hover:bg-active transition-colors disabled:opacity-60 disabled:cursor-default"
          >
            Добавить
          </button>
        </div>
      </div>

      {showFormula && (
        <FormulaAssistantInline
          columnName={name || "Новый столбец"}
          availableColumns={colOptions}
          onClose={() => setShowFormula(false)}
          onSave={(expr) => { setFormula(expr); setShowFormula(false); }}
        />
      )}
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   TableUsageModal — «Таблица X используется» (2611086)
───────────────────────────────────────────────── */

export function TableUsageModal({
  tableName,
  apps = [],
  onClose,
  onEdit,
  onPreview,
}: {
  tableName: string;
  apps?: { id: string; name: string; icon?: string }[];
  onClose: () => void;
  onEdit?: (appId: string) => void;
  onPreview?: (appId: string) => void;
}) {
  const displayApps = apps.length
    ? apps
    : [{ id: "demo", name: "Дикая Сибирь" }];

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 500, maxHeight: 600 }} className="flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-8 pt-6 pb-4 border-b border-cardbg shrink-0">
          <h2 className="text-[17px] font-bold text-primary">
            Таблица{" "}
            <span className="text-cta">{tableName}</span>{" "}
            используется
          </h2>
          <CloseBtn onClick={onClose} />
        </div>

        {/* App list */}
        <div className="flex-1 overflow-y-auto px-8 py-4 flex flex-col gap-3">
          {displayApps.map((app) => (
            <div
              key={app.id}
              className="flex items-center justify-between px-4 py-4 rounded-[10px] bg-cardbg"
            >
              <div className="flex items-center gap-3">
                {/* Лесовик logo placeholder */}
                <div className="w-10 h-10 rounded-[8px] bg-primary flex items-center justify-center shrink-0">
                  <span className="text-white text-[14px] font-bold">ЛВ</span>
                </div>
                <span className="text-[15px] font-semibold text-primary">{app.name}</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => onEdit?.(app.id)}
                  className="h-[30px] px-4 border border-cta rounded-btn text-cta text-[12px] hover:bg-cta/10 transition-colors"
                >
                  Редактировать
                </button>
                <button
                  onClick={() => onPreview?.(app.id)}
                  className="h-[30px] px-4 border border-cta rounded-btn text-cta text-[12px] hover:bg-cta/10 transition-colors"
                >
                  Предпросмотр
                </button>
              </div>
            </div>
          ))}

          {displayApps.length === 0 && (
            <p className="text-[14px] text-primary/40 text-center py-8">
              Таблица не используется ни в одном приложении
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="px-8 py-4 border-t border-cardbg shrink-0 flex justify-end">
          <button
            onClick={onClose}
            className="px-5 h-[34px] bg-cta border-2 border-cta rounded-btn text-white text-[13px] hover:bg-active transition-colors"
          >
            Закрыть
          </button>
        </div>
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   RelationsModal — view & delete relations for an entity
───────────────────────────────────────────────── */

export interface RelationItem {
  id: string;
  fromEntityName: string;
  toEntityName: string;
  relationType: string;
  fromFieldName: string;
  displayName: string | null;
}

const RELATION_TYPE_LABELS: Record<string, string> = {
  one_to_one: "1 : 1",
  one_to_many: "1 : N",
  many_to_many: "N : N",
};

export function RelationsModal({
  entityName,
  relations,
  onClose,
  onDelete,
}: {
  entityName: string;
  relations: RelationItem[];
  onClose: () => void;
  onDelete: (id: string) => void;
}) {
  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 620 }} className="px-10 pb-8">
        <div className="flex items-start justify-between pt-[30px] mb-5">
          <div>
            <h2 className="text-[20px] font-bold text-primary">Связи таблицы: {entityName}</h2>
            <p className="text-[14px] text-primary/60 mt-1">{relations.length} связей</p>
          </div>
          <CloseBtn onClick={onClose} />
        </div>

        {relations.length === 0 ? (
          <div className="py-10 text-center text-[14px] text-primary/40">
            Связи не настроены. Добавьте поле типа «Связь» чтобы создать первую.
          </div>
        ) : (
          <div className="rounded-[10px] overflow-hidden border border-white/30 mb-6">
            <table className="w-full text-[13px]">
              <thead className="bg-cardbg">
                <tr>
                  <th className="text-left font-semibold text-primary px-4 py-3">Из таблицы</th>
                  <th className="text-left font-semibold text-primary px-4 py-3">Тип</th>
                  <th className="text-left font-semibold text-primary px-4 py-3">В таблицу</th>
                  <th className="text-left font-semibold text-primary px-4 py-3">Поле</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {relations.map((r, i) => (
                  <tr key={r.id} className={cn("border-t border-white/30", i % 2 === 0 ? "bg-mainbg" : "bg-mainbg/60")}>
                    <td className="px-4 py-2 font-medium text-primary">{r.fromEntityName}</td>
                    <td className="px-4 py-2">
                      <span className="px-2 py-0.5 rounded-full bg-cta/10 text-cta text-[12px] font-mono">
                        {RELATION_TYPE_LABELS[r.relationType] ?? r.relationType}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-primary">{r.toEntityName}</td>
                    <td className="px-4 py-2 text-primary/60 font-mono text-[12px]">{r.fromFieldName}</td>
                    <td className="px-2 py-2 text-center">
                      <button
                        onClick={() => onDelete(r.id)}
                        className="w-6 h-6 flex items-center justify-center text-primary/30 hover:text-red-400 transition-colors mx-auto"
                        title="Удалить связь"
                      >
                        <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5">
                          <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                        </svg>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex justify-end">
          <PrimaryBtn onClick={onClose}>Закрыть</PrimaryBtn>
        </div>
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   ICONS
───────────────────────────────────────────────── */

function KeyIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 inline">
      <circle cx="6" cy="8" r="3.5" stroke="#35A7FF" strokeWidth="1.5" />
      <path d="M9 8h5M12 6v4" stroke="#35A7FF" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function TagIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 inline">
      <path d="M2 2h6l6 6-6 6-6-6V2z" stroke="#35A7FF" strokeWidth="1.5" strokeLinejoin="round" />
      <circle cx="5.5" cy="5.5" r="1" fill="#35A7FF" />
    </svg>
  );
}

