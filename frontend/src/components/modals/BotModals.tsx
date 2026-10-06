import { useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Overlay, CloseBtn, BlueField, ModalButtons, ModalError } from "./primitives";

export { Overlay, CloseBtn, BlueField, ModalButtons, ModalError };

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

/* ─────────────────────────────────────────────────
   1. NewStepModal
───────────────────────────────────────────────── */

const STEP_TYPES = [
  { key: "add_row",    icon: "➕", label: "Добавить строку" },
  { key: "delete_row", icon: "🗑️", label: "Удалить строку" },
  { key: "set_value",  icon: "📝", label: "Установить значение" },
  { key: "notify",     icon: "✉️", label: "Отправить уведомление" },
  { key: "branch",     icon: "🔀", label: "Разветвление с условием" },
  { key: "call",       icon: "🔄", label: "Вызвать другой процесс" },
];

export function NewStepModal({
  onClose,
  onAdd,
}: {
  onClose: () => void;
  onAdd: (type: string) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 480 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Добавить шаг процесса</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="grid grid-cols-2 gap-3">
          {STEP_TYPES.map((step) => (
            <button
              key={step.key}
              onClick={() => setSelected(step.key)}
              className={cn(
                "flex items-center gap-3 px-4 py-4 rounded-[10px] border-2 transition-colors text-left",
                selected === step.key
                  ? "border-cta bg-cta/10"
                  : "border-cardbg bg-mainbg hover:border-cta/40"
              )}
            >
              <span className="text-2xl shrink-0 leading-none">{step.icon}</span>
              <span
                className={cn(
                  "text-[14px] font-semibold",
                  selected === step.key ? "text-cta" : "text-primary"
                )}
              >
                {step.label}
              </span>
            </button>
          ))}
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => selected && onAdd(selected)}
          confirmLabel="Добавить"
          disabled={!selected}
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   2. CustomTaskModal
───────────────────────────────────────────────── */

const EXECUTOR_OPTIONS = ["Текущий пользователь", "Email", "Роль"];

export function CustomTaskModal({
  onClose,
  onConfirm,
}: {
  onClose: () => void;
  onConfirm: (data: {
    title: string;
    description: string;
    executor: string;
    deadline: string;
    message: string;
  }) => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [executor, setExecutor] = useState(EXECUTOR_OPTIONS[0]);
  const [deadline, setDeadline] = useState("");
  const [message, setMessage] = useState("");

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 500 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Пользовательская задача</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Название задачи</FieldLabel>
          <BlueField>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Введите название задачи..."
              className="w-full bg-transparent outline-none text-[16px] text-primary placeholder-primary/40"
            />
          </BlueField>
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Описание</FieldLabel>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Описание задачи..."
            rows={3}
            className="w-full bg-cardbg rounded-btn px-5 py-3 text-[16px] text-primary outline-none resize-none placeholder-primary/40"
          />
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Исполнитель</FieldLabel>
          <SimpleSelect value={executor} onChange={setExecutor} options={EXECUTOR_OPTIONS} />
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Срок выполнения</FieldLabel>
          <BlueField>
            <input
              type="date"
              value={deadline}
              onChange={(e) => setDeadline(e.target.value)}
              className="w-full bg-transparent outline-none text-[16px] text-primary"
            />
          </BlueField>
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Сообщение пользователю</FieldLabel>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Сообщение для исполнителя..."
            rows={3}
            className="w-full bg-cardbg rounded-btn px-5 py-3 text-[16px] text-primary outline-none resize-none placeholder-primary/40"
          />
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm({ title, description, executor, deadline, message })}
          confirmLabel="Сохранить"
          disabled={!title.trim()}
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   3. EventSourcesModal
───────────────────────────────────────────────── */

const SCHEDULE_PRESETS = ["Ежедневно", "Еженедельно", "Ежемесячно", "Своё расписание"];

export function EventSourcesModal({
  tables,
  onClose,
  onSave,
}: {
  tables: string[];
  onClose: () => void;
  onSave: (settings: {
    appEnabled: boolean;
    appTable: string;
    appTriggers: { add: boolean; delete: boolean; update: boolean };
    scheduleEnabled: boolean;
    schedulePreset: string;
    scheduleCron: string;
    webhookEnabled: boolean;
    manualEnabled: boolean;
  }) => void;
}) {
  const [appEnabled, setAppEnabled] = useState(false);
  const [appTable, setAppTable] = useState(tables[0] ?? "");
  const [appTriggers, setAppTriggers] = useState({ add: true, delete: false, update: false });

  const [scheduleEnabled, setScheduleEnabled] = useState(false);
  const [schedulePreset, setSchedulePreset] = useState(SCHEDULE_PRESETS[0]);
  const [scheduleCron, setScheduleCron] = useState("");

  const [webhookEnabled, setWebhookEnabled] = useState(false);
  const [manualEnabled, setManualEnabled] = useState(false);

  const webhookUrl = typeof window !== "undefined"
    ? `${window.location.origin}/api/webhooks/trigger`
    : "https://example.com/api/webhooks/trigger";

  const [webhookCopied, setWebhookCopied] = useState(false);
  function copyWebhook() {
    void navigator.clipboard?.writeText(webhookUrl).then(() => {
      setWebhookCopied(true);
      setTimeout(() => setWebhookCopied(false), 1500);
    });
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 540 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Источники событий</h2>
          <CloseBtn onClick={onClose} />
        </div>

        {/* App source */}
        <div className="flex flex-col gap-3 p-4 rounded-[10px] bg-mainbg">
          <div className="flex items-center justify-between">
            <span className="text-[15px] font-semibold text-primary">Приложение</span>
            <Toggle checked={appEnabled} onChange={setAppEnabled} />
          </div>
          {appEnabled && (
            <div className="flex flex-col gap-3">
              <SimpleSelect value={appTable} onChange={setAppTable} options={tables.length ? tables : ["(нет таблиц)"]} />
              <div className="flex gap-5">
                {(["add", "delete", "update"] as const).map((t) => {
                  const labels = { add: "Добавление", delete: "Удаление", update: "Обновление" };
                  return (
                    <label key={t} className="flex items-center gap-2 cursor-pointer text-[14px] text-primary">
                      <input
                        type="checkbox"
                        checked={appTriggers[t]}
                        onChange={(e) => setAppTriggers((prev) => ({ ...prev, [t]: e.target.checked }))}
                        className="accent-cta"
                      />
                      {labels[t]}
                    </label>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Schedule source */}
        <div className="flex flex-col gap-3 p-4 rounded-[10px] bg-mainbg">
          <div className="flex items-center justify-between">
            <span className="text-[15px] font-semibold text-primary">Расписание</span>
            <Toggle checked={scheduleEnabled} onChange={setScheduleEnabled} />
          </div>
          {scheduleEnabled && (
            <div className="flex flex-col gap-3">
              <SimpleSelect value={schedulePreset} onChange={setSchedulePreset} options={SCHEDULE_PRESETS} />
              {schedulePreset === "Своё расписание" && (
                <BlueField>
                  <input
                    value={scheduleCron}
                    onChange={(e) => setScheduleCron(e.target.value)}
                    placeholder="0 9 * * 1-5"
                    className="w-full bg-transparent outline-none text-[15px] text-primary placeholder-primary/40 font-mono"
                  />
                </BlueField>
              )}
            </div>
          )}
        </div>

        {/* Webhook source */}
        <div className="flex flex-col gap-3 p-4 rounded-[10px] bg-mainbg">
          <div className="flex items-center justify-between">
            <span className="text-[15px] font-semibold text-primary">Webhook</span>
            <Toggle checked={webhookEnabled} onChange={setWebhookEnabled} />
          </div>
          {webhookEnabled && (
            <div className="flex items-center gap-2">
              <BlueField className="flex-1">
                <span className="text-[13px] text-primary/70 truncate font-mono">{webhookUrl}</span>
              </BlueField>
              <button
                onClick={copyWebhook}
                title={webhookCopied ? "Скопировано" : "Копировать URL"}
                className="shrink-0 h-[41px] px-4 border-2 border-cta rounded-btn text-cta text-[13px] hover:bg-cta/10 transition-colors"
              >
                {webhookCopied ? "✓" : "Копировать"}
              </button>
            </div>
          )}
        </div>

        {/* Manual source */}
        <div className="flex items-center justify-between p-4 rounded-[10px] bg-mainbg">
          <span className="text-[15px] font-semibold text-primary">Вручную</span>
          <Toggle checked={manualEnabled} onChange={setManualEnabled} />
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() =>
            onSave({
              appEnabled,
              appTable,
              appTriggers,
              scheduleEnabled,
              schedulePreset,
              scheduleCron,
              webhookEnabled,
              manualEnabled,
            })
          }
          confirmLabel="Сохранить"
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   4. TableExtensionModal
───────────────────────────────────────────────── */

const TABLE_EXTENSIONS = [
  { key: "triggers",   icon: "⚡", label: "Триггеры",               desc: "Автоматические действия" },
  { key: "aggcols",    icon: "📊", label: "Агрегированные столбцы",  desc: "Вычисляемые агрегаты" },
  { key: "related",    icon: "🔗", label: "Связанные данные",        desc: "Отношения между таблицами" },
  { key: "rls",        icon: "🔒", label: "Строчная безопасность",   desc: "Ограничение доступа к строкам" },
  { key: "audit",      icon: "📝", label: "Аудит изменений",         desc: "Журнал всех изменений" },
  { key: "versions",   icon: "🔄", label: "История версий",          desc: "Откат к предыдущим версиям" },
];

export function TableExtensionModal({ onClose }: { onClose: () => void }) {
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});

  function toggle(key: string) {
    setEnabled((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 480 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Расширение таблицы</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-3">
          {TABLE_EXTENSIONS.map((ext) => (
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
   5. RunTaskModal — запустить задачу
───────────────────────────────────────────────── */

const PROCESS_OPTIONS = ["Обработка заявки", "Уведомление клиента", "Синхронизация данных", "Генерация отчёта"];

export function RunTaskModal({
  processes = PROCESS_OPTIONS,
  initialData,
  onClose,
  onConfirm,
}: {
  processes?: string[];
  initialData?: { process?: string; inputData?: string; sync?: boolean };
  onClose: () => void;
  onConfirm: (process: string, inputData: string, sync: boolean) => void;
}) {
  const [process, setProcess] = useState(initialData?.process ?? (processes[0] ?? ""));
  const [inputData, setInputData] = useState(initialData?.inputData ?? "");
  const [sync, setSync] = useState(initialData?.sync ?? true);

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 480 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Запустить задачу</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Процесс</FieldLabel>
          <SimpleSelect value={process} onChange={setProcess} options={processes.length ? processes : PROCESS_OPTIONS} />
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Входящие данные</FieldLabel>
          <textarea
            value={inputData}
            onChange={(e) => setInputData(e.target.value)}
            placeholder="Данные для передачи в процесс..."
            rows={3}
            className="w-full bg-cardbg rounded-btn px-5 py-3 text-[16px] text-primary outline-none resize-none placeholder-primary/40"
          />
        </div>

        <div className="flex items-center justify-between px-0 py-1">
          <FieldLabel>Синхронный запуск</FieldLabel>
          <Toggle checked={sync} onChange={setSync} />
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm(process, inputData, sync)}
          confirmLabel="Сохранить"
          disabled={!process}
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   6. WaitModal — подождать
───────────────────────────────────────────────── */

const TIME_UNITS = ["Секунды", "Минуты", "Часы", "Дни"];

export function WaitModal({
  initialData,
  onClose,
  onConfirm,
}: {
  initialData?: { amount?: number; unit?: string };
  onClose: () => void;
  onConfirm: (amount: number, unit: string) => void;
}) {
  const [amount, setAmount] = useState(String(initialData?.amount ?? 1));
  const [unit, setUnit] = useState(initialData?.unit ?? TIME_UNITS[1]);

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 400 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Подождать</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex gap-3">
          <div className="flex flex-col gap-[8px] w-[120px]">
            <FieldLabel>Количество</FieldLabel>
            <BlueField>
              <input
                type="number"
                min={1}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="w-full bg-transparent outline-none text-[16px] text-primary"
              />
            </BlueField>
          </div>
          <div className="flex flex-col gap-[8px] flex-1">
            <FieldLabel>Единица</FieldLabel>
            <SimpleSelect value={unit} onChange={setUnit} options={TIME_UNITS} />
          </div>
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm(Number(amount) || 1, unit)}
          confirmLabel="Сохранить"
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   7. DataActionModal — действие с данными
───────────────────────────────────────────────── */

const DATA_OPERATIONS = ["Добавить строку", "Удалить строку", "Обновить строку", "Найти строку"];

export function DataActionModal({
  tables = [],
  initialData,
  onClose,
  onConfirm,
}: {
  tables?: string[];
  initialData?: { table?: string; operation?: string; condition?: string; values?: string };
  onClose: () => void;
  onConfirm: (table: string, operation: string, condition: string, values: string) => void;
}) {
  const tableList = tables.length ? tables : ["Таблица 1", "Таблица 2"];
  const [table, setTable] = useState(initialData?.table ?? tableList[0]);
  const [operation, setOperation] = useState(initialData?.operation ?? DATA_OPERATIONS[0]);
  const [condition, setCondition] = useState(initialData?.condition ?? "");
  const [values, setValues] = useState(initialData?.values ?? "");

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 500 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Действие с данными</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Таблица</FieldLabel>
          <SimpleSelect value={table} onChange={setTable} options={tableList} />
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Операция</FieldLabel>
          <SimpleSelect value={operation} onChange={setOperation} options={DATA_OPERATIONS} />
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Условие</FieldLabel>
          <BlueField>
            <input
              value={condition}
              onChange={(e) => setCondition(e.target.value)}
              placeholder="например: ID = {ID}"
              className="w-full bg-transparent outline-none text-[16px] text-primary placeholder-primary/40"
            />
          </BlueField>
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Значения</FieldLabel>
          <textarea
            value={values}
            onChange={(e) => setValues(e.target.value)}
            placeholder="Поле: значение"
            rows={3}
            className="w-full bg-cardbg rounded-btn px-5 py-3 text-[16px] text-primary outline-none resize-none placeholder-primary/40"
          />
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm(table, operation, condition, values)}
          confirmLabel="Сохранить"
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   8. BranchModal — разветвление с условием
───────────────────────────────────────────────── */

const OPERATORS = ["равно", "не равно", "больше", "меньше", "содержит", "пусто"];

interface BranchCondition { field: string; operator: string; value: string }

export function BranchModal({
  initialData,
  onClose,
  onConfirm,
}: {
  initialData?: { conditions?: BranchCondition[] };
  onClose: () => void;
  onConfirm: (conditions: BranchCondition[]) => void;
}) {
  const [conditions, setConditions] = useState<BranchCondition[]>(
    initialData?.conditions ?? [{ field: "", operator: OPERATORS[0], value: "" }]
  );

  function update(i: number, key: keyof BranchCondition, val: string) {
    setConditions((prev) => prev.map((c, idx) => (idx === i ? { ...c, [key]: val } : c)));
  }

  function addCondition() {
    if (conditions.length < 5) {
      setConditions((prev) => [...prev, { field: "", operator: OPERATORS[0], value: "" }]);
    }
  }

  function removeCondition(i: number) {
    setConditions((prev) => prev.filter((_, idx) => idx !== i));
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 520 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Разветвление с условием</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-3">
          {conditions.map((cond, i) => (
            <div key={i} className="flex items-end gap-2">
              <div className="flex-1 flex flex-col gap-[6px]">
                {i === 0 && <FieldLabel>Поле</FieldLabel>}
                <BlueField>
                  <input
                    value={cond.field}
                    onChange={(e) => update(i, "field", e.target.value)}
                    placeholder="Название поля"
                    className="w-full bg-transparent outline-none text-[15px] text-primary placeholder-primary/40"
                  />
                </BlueField>
              </div>
              <div className="w-[140px] flex flex-col gap-[6px]">
                {i === 0 && <FieldLabel>Оператор</FieldLabel>}
                <SimpleSelect value={cond.operator} onChange={(v) => update(i, "operator", v)} options={OPERATORS} />
              </div>
              <div className="flex-1 flex flex-col gap-[6px]">
                {i === 0 && <FieldLabel>Значение</FieldLabel>}
                <BlueField>
                  <input
                    value={cond.value}
                    onChange={(e) => update(i, "value", e.target.value)}
                    placeholder="Значение"
                    className="w-full bg-transparent outline-none text-[15px] text-primary placeholder-primary/40"
                  />
                </BlueField>
              </div>
              {conditions.length > 1 && (
                <button onClick={() => removeCondition(i)} className="mb-[1px] text-mistake hover:opacity-70 shrink-0">✕</button>
              )}
            </div>
          ))}
        </div>

        {conditions.length < 5 && (
          <button
            onClick={addCondition}
            className="self-start text-[14px] text-cta hover:underline"
          >
            + Добавить условие
          </button>
        )}

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm(conditions)}
          confirmLabel="Сохранить"
          disabled={conditions.some((c) => !c.field.trim())}
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   9. CallProcessModal — вызвать процесс
───────────────────────────────────────────────── */

const CALL_PROCESS_OPTIONS = ["Обработка заявки", "Уведомление клиента", "Синхронизация данных", "Генерация отчёта"];

export function CallProcessModal({
  processes = CALL_PROCESS_OPTIONS,
  initialData,
  onClose,
  onConfirm,
}: {
  processes?: string[];
  initialData?: { process?: string; wait?: boolean; passData?: boolean };
  onClose: () => void;
  onConfirm: (process: string, wait: boolean, passData: boolean) => void;
}) {
  const opts = processes.length ? processes : CALL_PROCESS_OPTIONS;
  const [process, setProcess] = useState(initialData?.process ?? opts[0]);
  const [wait, setWait] = useState(initialData?.wait ?? true);
  const [passData, setPassData] = useState(initialData?.passData ?? false);

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 460 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Вызвать процесс</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Процесс</FieldLabel>
          <SimpleSelect value={process} onChange={setProcess} options={opts} />
        </div>

        <div className="flex items-center justify-between py-1">
          <FieldLabel>Ждать завершения</FieldLabel>
          <Toggle checked={wait} onChange={setWait} />
        </div>

        <div className="flex items-center justify-between py-1">
          <FieldLabel>Передать данные</FieldLabel>
          <Toggle checked={passData} onChange={setPassData} />
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm(process, wait, passData)}
          confirmLabel="Сохранить"
          disabled={!process}
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   10. ReturnValueModal — вернуть значение
───────────────────────────────────────────────── */

const VALUE_TYPES = ["Текст", "Число", "Дата", "Список", "Запись"];

export function ReturnValueModal({
  initialData,
  onClose,
  onConfirm,
}: {
  initialData?: { value?: string; type?: string };
  onClose: () => void;
  onConfirm: (value: string, type: string) => void;
}) {
  const [value, setValue] = useState(initialData?.value ?? "");
  const [type, setType] = useState(initialData?.type ?? VALUE_TYPES[0]);

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 440 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Вернуть значение</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Значение</FieldLabel>
          <BlueField>
            <input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="формула или значение"
              className="w-full bg-transparent outline-none text-[16px] text-primary placeholder-primary/40"
            />
          </BlueField>
        </div>

        <div className="flex flex-col gap-[8px]">
          <FieldLabel>Тип</FieldLabel>
          <SimpleSelect value={type} onChange={setType} options={VALUE_TYPES} />
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm(value, type)}
          confirmLabel="Сохранить"
          disabled={!value.trim()}
        />
      </div>
    </Overlay>
  );
}
