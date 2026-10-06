import { useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Overlay, CloseBtn, BlueField, ModalButtons, ModalError } from "./primitives";

export { Overlay, CloseBtn, BlueField, ModalButtons, ModalError };

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={cn(
        "relative w-[38px] h-[21px] rounded-full transition-colors shrink-0",
        checked ? "bg-cta" : "bg-cardbg border border-primary/20",
      )}
    >
      <span
        className={cn(
          "absolute top-[2px] w-[17px] h-[17px] rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-[19px]" : "translate-x-[2px]",
        )}
      />
    </button>
  );
}

function SimpleSelect({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <BlueField>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-transparent outline-none text-[16px] text-primary cursor-pointer appearance-none"
      >
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

/* ── 1. CopyTableModal ── */

export function CopyTableModal({
  tableName,
  onClose,
  onConfirm,
}: {
  tableName: string;
  onClose: () => void;
  onConfirm: (newName: string) => void;
}) {
  const [name, setName] = useState(`${tableName} (копия)`);
  const [withData, setWithData] = useState(true);
  const [withSettings, setWithSettings] = useState(true);

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 460 }} className="px-8 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Копировать таблицу</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-[8px]">
          <label className="text-[14px] font-medium text-primary">Название</label>
          <BlueField>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-transparent outline-none text-[16px] text-primary"
            />
          </BlueField>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-[15px] text-primary">Включить данные</span>
          <Toggle checked={withData} onChange={setWithData} />
        </div>

        <div className="flex items-center justify-between">
          <span className="text-[15px] text-primary">Включить настройки</span>
          <Toggle checked={withSettings} onChange={setWithSettings} />
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm(name.trim() || tableName)}
          confirmLabel="Копировать"
          disabled={!name.trim()}
        />
      </div>
    </Overlay>
  );
}

/* ── 2. MoveModal ── */

export function MoveModal({
  itemName,
  targets,
  onClose,
  onConfirm,
}: {
  itemName: string;
  targets: string[];
  onClose: () => void;
  onConfirm: (target: string) => void;
}) {
  const [selected, setSelected] = useState(targets[0] ?? "");

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 460 }} className="px-8 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">
            Переместить «{itemName}»
          </h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-[8px]">
          <label className="text-[14px] font-medium text-primary">Куда переместить</label>
          {targets.length > 0 ? (
            <SimpleSelect value={selected} onChange={setSelected} options={targets} />
          ) : (
            <BlueField>
              <span className="text-[15px] text-primary/40">Нет доступных таблиц</span>
            </BlueField>
          )}
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm(selected)}
          confirmLabel="Переместить"
          disabled={targets.length === 0}
        />
      </div>
    </Overlay>
  );
}

/* ── 3. PresetModal ── */

const PRESETS: { id: string; label: string; desc: string; icon: ReactNode }[] = [
  {
    id: "default",
    label: "По умолчанию",
    desc: "Стандартный вид для большинства задач",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-6 h-6">
        <rect x="3" y="3" width="18" height="18" rx="3" stroke="#00205F" strokeWidth="2" />
        <line x1="3" y1="9" x2="21" y2="9" stroke="#00205F" strokeWidth="1.5" />
        <line x1="3" y1="15" x2="21" y2="15" stroke="#00205F" strokeWidth="1.5" />
      </svg>
    ),
  },
  {
    id: "compact",
    label: "Компактный",
    desc: "Минимальные отступы для плотных данных",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-6 h-6">
        <rect x="3" y="4" width="18" height="3" rx="1" fill="#00205F" />
        <rect x="3" y="10" width="18" height="3" rx="1" fill="#00205F" />
        <rect x="3" y="16" width="18" height="3" rx="1" fill="#00205F" />
      </svg>
    ),
  },
  {
    id: "wide",
    label: "Широкий",
    desc: "Увеличенные строки для удобного чтения",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-6 h-6">
        <rect x="2" y="5" width="20" height="5" rx="1.5" stroke="#00205F" strokeWidth="2" />
        <rect x="2" y="14" width="20" height="5" rx="1.5" stroke="#00205F" strokeWidth="2" />
      </svg>
    ),
  },
  {
    id: "summary",
    label: "Сводный",
    desc: "Только ключевые поля, без деталей",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-6 h-6">
        <path d="M4 6h16M4 12h10M4 18h7" stroke="#00205F" strokeWidth="2" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: "detailed",
    label: "Детализированный",
    desc: "Все поля и дополнительная информация",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-6 h-6">
        <rect x="3" y="3" width="7" height="7" rx="1" stroke="#00205F" strokeWidth="2" />
        <rect x="14" y="3" width="7" height="7" rx="1" stroke="#00205F" strokeWidth="2" />
        <rect x="3" y="14" width="7" height="7" rx="1" stroke="#00205F" strokeWidth="2" />
        <rect x="14" y="14" width="7" height="7" rx="1" stroke="#00205F" strokeWidth="2" />
      </svg>
    ),
  },
];

export function PresetModal({
  onClose,
  onApply,
}: {
  onClose: () => void;
  onApply: (preset: string) => void;
}) {
  const [selected, setSelected] = useState("default");

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 460 }} className="px-8 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Пресет</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-[8px]">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              onClick={() => setSelected(p.id)}
              className={cn(
                "flex items-center gap-4 px-4 py-3 rounded-[10px] border-2 transition-all text-left",
                selected === p.id
                  ? "border-cta bg-cta/5 ring-1 ring-cta"
                  : "border-cardbg bg-white hover:border-cta/40",
              )}
            >
              <span className={cn("shrink-0", selected === p.id ? "text-cta" : "text-primary")}>
                {p.icon}
              </span>
              <div className="flex flex-col">
                <span
                  className={cn(
                    "text-[15px] font-semibold",
                    selected === p.id ? "text-cta" : "text-primary",
                  )}
                >
                  {p.label}
                </span>
                <span className="text-[13px] text-primary/60">{p.desc}</span>
              </div>
            </button>
          ))}
        </div>

        <div className="flex justify-end gap-[10px]">
          <button
            onClick={onClose}
            className="px-5 py-[3px] h-[34px] border-2 border-cta rounded-btn text-cta text-meta hover:bg-cta/10 transition-colors"
          >
            Отмена
          </button>
          <button
            onClick={() => onApply(selected)}
            className="px-5 py-[3px] h-[34px] bg-cta border-2 border-cta rounded-btn text-white text-meta hover:bg-active transition-colors"
          >
            Применить
          </button>
        </div>
      </div>
    </Overlay>
  );
}

/* ── 4. ProjectExtensionModal ── */

const PROJECT_EXTENSIONS = [
  {
    id: "versioning",
    label: "Версионирование",
    desc: "История изменений проекта",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
        <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="2" />
        <path d="M12 7v5l3 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: "multilang",
    label: "Мультиязычность",
    desc: "Поддержка нескольких языков",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
        <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="2" />
        <path d="M12 4C9 7 9 17 12 20M12 4C15 7 15 17 12 20M4 12h16" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    ),
  },
  {
    id: "analytics",
    label: "Аналитика",
    desc: "Встроенная аналитика",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
        <path d="M4 18l4-5 4 3 4-7 4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: "api",
    label: "API интеграции",
    desc: "Подключение внешних API",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
        <rect x="3" y="9" width="7" height="6" rx="1" stroke="currentColor" strokeWidth="2" />
        <rect x="14" y="9" width="7" height="6" rx="1" stroke="currentColor" strokeWidth="2" />
        <line x1="10" y1="12" x2="14" y2="12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: "push",
    label: "Push уведомления",
    desc: "Уведомления пользователей",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
        <path d="M6 10a6 6 0 1112 0v4l2 2H4l2-2v-4z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
        <path d="M10 18a2 2 0 004 0" stroke="currentColor" strokeWidth="2" />
      </svg>
    ),
  },
];

export function ProjectExtensionModal({ onClose }: { onClose: () => void }) {
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 500 }} className="px-8 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Расширения проекта</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-[4px]">
          {PROJECT_EXTENSIONS.map((ext) => (
            <div
              key={ext.id}
              className="flex items-center justify-between px-4 py-3 rounded-[8px] hover:bg-white/60 transition-colors"
            >
              <div className="flex items-center gap-3">
                <span className="text-primary/60">{ext.icon}</span>
                <div className="flex flex-col">
                  <span className="text-[15px] font-medium text-primary">{ext.label}</span>
                  <span className="text-[12px] text-primary/50">{ext.desc}</span>
                </div>
              </div>
              <Toggle
                checked={!!enabled[ext.id]}
                onChange={(v) => setEnabled((prev) => ({ ...prev, [ext.id]: v }))}
              />
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

/* ── 5. DbExtensionModal ── */

const DB_EXTENSIONS = [
  {
    id: "fts",
    label: "Полнотекстовый поиск",
    desc: "Поиск по всем полям таблицы",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
        <circle cx="10" cy="10" r="6" stroke="currentColor" strokeWidth="2" />
        <line x1="14.5" y1="14.5" x2="19" y2="19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <line x1="7" y1="10" x2="13" y2="10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="10" y1="7" x2="10" y2="13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: "encryption",
    label: "Шифрование",
    desc: "Шифрование данных",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
        <rect x="5" y="11" width="14" height="10" rx="2" stroke="currentColor" strokeWidth="2" />
        <path d="M8 11V7a4 4 0 018 0v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <circle cx="12" cy="16" r="1.5" fill="currentColor" />
      </svg>
    ),
  },
  {
    id: "replication",
    label: "Репликация",
    desc: "Дублирование данных",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
        <ellipse cx="8" cy="7" rx="4" ry="2" stroke="currentColor" strokeWidth="1.8" />
        <path d="M4 7v6c0 1.1 1.79 2 4 2s4-.9 4-2V7" stroke="currentColor" strokeWidth="1.8" />
        <ellipse cx="16" cy="7" rx="4" ry="2" stroke="currentColor" strokeWidth="1.8" />
        <path d="M12 7v6c0 1.1 1.79 2 4 2s4-.9 4-2V7" stroke="currentColor" strokeWidth="1.8" />
      </svg>
    ),
  },
  {
    id: "partitioning",
    label: "Партиционирование",
    desc: "Разбиение больших таблиц",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
        <rect x="3" y="4" width="8" height="7" rx="1" stroke="currentColor" strokeWidth="1.8" />
        <rect x="13" y="4" width="8" height="7" rx="1" stroke="currentColor" strokeWidth="1.8" />
        <rect x="3" y="14" width="18" height="6" rx="1" stroke="currentColor" strokeWidth="1.8" />
      </svg>
    ),
  },
  {
    id: "cache",
    label: "Кэширование",
    desc: "Ускорение запросов",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      </svg>
    ),
  },
];

export function DbExtensionModal({ onClose }: { onClose: () => void }) {
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 500 }} className="px-8 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Расширения базы данных</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-[4px]">
          {DB_EXTENSIONS.map((ext) => (
            <div
              key={ext.id}
              className="flex items-center justify-between px-4 py-3 rounded-[8px] hover:bg-white/60 transition-colors"
            >
              <div className="flex items-center gap-3">
                <span className="text-primary/60">{ext.icon}</span>
                <div className="flex flex-col">
                  <span className="text-[15px] font-medium text-primary">{ext.label}</span>
                  <span className="text-[12px] text-primary/50">{ext.desc}</span>
                </div>
              </div>
              <Toggle
                checked={!!enabled[ext.id]}
                onChange={(v) => setEnabled((prev) => ({ ...prev, [ext.id]: v }))}
              />
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

/* ── 6. CategoryExtensionModal ── */

const CATEGORY_EXTENSIONS = [
  {
    id: "tags",
    label: "Теги",
    desc: "Метки для группировки",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
        <path d="M3 7a2 2 0 012-2h6l8 8-8 8-8-8V7z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
        <circle cx="8" cy="10" r="1.5" fill="currentColor" />
      </svg>
    ),
  },
  {
    id: "hierarchy",
    label: "Иерархия",
    desc: "Вложенные категории",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
        <rect x="9" y="2" width="6" height="4" rx="1" stroke="currentColor" strokeWidth="1.8" />
        <rect x="2" y="16" width="6" height="4" rx="1" stroke="currentColor" strokeWidth="1.8" />
        <rect x="9" y="16" width="6" height="4" rx="1" stroke="currentColor" strokeWidth="1.8" />
        <rect x="16" y="16" width="6" height="4" rx="1" stroke="currentColor" strokeWidth="1.8" />
        <path d="M12 6v5M5 11v5M12 11v5M19 11v5M5 11h14" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    ),
  },
  {
    id: "icons",
    label: "Иконки",
    desc: "Выбор иконок для категорий",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
        <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="2" />
        <path d="M12 2v2M12 20v2M2 12h2M20 12h2M5.6 5.6l1.4 1.4M16.9 16.9l1.4 1.4M5.6 18.4l1.4-1.4M16.9 7.1l1.4-1.4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: "colors",
    label: "Цветовая маркировка",
    desc: "Цвета категорий",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
        <circle cx="7" cy="7" r="3" fill="#35A7FF" />
        <circle cx="17" cy="7" r="3" fill="#22C55E" />
        <circle cx="7" cy="17" r="3" fill="#F59E0B" />
        <circle cx="17" cy="17" r="3" fill="#EF4444" />
      </svg>
    ),
  },
];

export function CategoryExtensionModal({ onClose }: { onClose: () => void }) {
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 460 }} className="px-8 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Расширения категории</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-[4px]">
          {CATEGORY_EXTENSIONS.map((ext) => (
            <div
              key={ext.id}
              className="flex items-center justify-between px-4 py-3 rounded-[8px] hover:bg-white/60 transition-colors"
            >
              <div className="flex items-center gap-3">
                <span className="text-primary/60">{ext.icon}</span>
                <div className="flex flex-col">
                  <span className="text-[15px] font-medium text-primary">{ext.label}</span>
                  <span className="text-[12px] text-primary/50">{ext.desc}</span>
                </div>
              </div>
              <Toggle
                checked={!!enabled[ext.id]}
                onChange={(v) => setEnabled((prev) => ({ ...prev, [ext.id]: v }))}
              />
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

/* ── 7. EditActionModal ── */

const ACTION_TYPES = ["Добавить", "Изменить", "Удалить", "Экспорт", "Отправить уведомление"];

export function EditActionModal({
  actionName,
  onClose,
  onSave,
}: {
  actionName: string;
  onClose: () => void;
  onSave: (name: string, description: string) => void;
}) {
  const [name, setName] = useState(actionName);
  const [description, setDescription] = useState("");
  const [actionType, setActionType] = useState(ACTION_TYPES[0]);
  const [requireConfirm, setRequireConfirm] = useState(false);

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 480 }} className="px-8 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Редактировать действие</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-[8px]">
          <label className="text-[14px] font-medium text-primary">Название</label>
          <BlueField>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-transparent outline-none text-[16px] text-primary"
            />
          </BlueField>
        </div>

        <div className="flex flex-col gap-[8px]">
          <label className="text-[14px] font-medium text-primary">Описание</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="Введите описание..."
            className="w-full bg-cardbg rounded-btn px-5 py-3 text-[15px] text-primary outline-none resize-none placeholder:text-primary/40"
          />
        </div>

        <div className="flex flex-col gap-[8px]">
          <label className="text-[14px] font-medium text-primary">Тип действия</label>
          <SimpleSelect value={actionType} onChange={setActionType} options={ACTION_TYPES} />
        </div>

        <div className="flex items-center justify-between">
          <span className="text-[15px] text-primary">Подтверждение требуется</span>
          <Toggle checked={requireConfirm} onChange={setRequireConfirm} />
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onSave(name.trim() || actionName, description)}
          confirmLabel="Сохранить"
          disabled={!name.trim()}
        />
      </div>
    </Overlay>
  );
}

/* ── 8. ErrorsModal ── */

export function ErrorsModal({
  onClose,
  errors,
}: {
  onClose: () => void;
  errors?: string[];
}) {
  const hasErrors = errors && errors.length > 0;

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 540 }} className="px-8 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Ошибки</h2>
          <CloseBtn onClick={onClose} />
        </div>

        {!hasErrors ? (
          <div className="flex items-center gap-3 px-4 py-3 bg-[#E8F5E9] rounded-[8px]">
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 shrink-0 text-[#2E7D32]">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
            <span className="text-[15px] text-[#2E7D32] font-medium">Ошибок не обнаружено</span>
          </div>
        ) : (
          <div className="flex flex-col gap-[6px] max-h-[300px] overflow-y-auto">
            {errors.map((err, i) => (
              <div
                key={i}
                className="flex items-start gap-3 px-4 py-3 bg-[#FFF8E1] border border-[#FFE082] rounded-[8px]"
              >
                <span className="text-[16px] shrink-0 mt-[1px]">⚠️</span>
                <span className="text-[14px] text-primary leading-[1.5]">{err}</span>
              </div>
            ))}
          </div>
        )}

        <div className="flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-[3px] h-[34px] bg-cta border-2 border-cta rounded-btn text-white text-meta hover:bg-active transition-colors"
          >
            Закрыть
          </button>
        </div>
      </div>
    </Overlay>
  );
}
