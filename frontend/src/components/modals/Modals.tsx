import { useState, useRef, useEffect, type ReactNode } from "react";
import { formatDistanceToNow } from "date-fns";
import { ru } from "date-fns/locale";
import { cn } from "@/lib/cn";
import { isAxiosError } from "axios";
import { buildRuntimeUrl, buildEditorUrl, buildInviteUrl } from "@/shared/lib/appLinks";
import {
  useAppMembers,
  useAddAppMember,
  useRemoveAppMember,
  useAppSnapshots,
  useCreateSnapshot,
  useRollbackSnapshot,
  useInviteLinks,
  useCreateInviteLink,
  useRevokeInviteLink,
} from "@/shared/hooks/useApps";
import { useUsers, useInviteUser } from "@/shared/hooks/useUsers";
import type { AppSnapshot, InviteRole } from "@/shared/api/apps";

/* ─────────────────────────────────────────────────
   PRIMITIVES
───────────────────────────────────────────────── */

/** Dark overlay backdrop */
function Overlay({
  onClose,
  children,
  alignTop = false,
  topOffset = 85,
}: {
  onClose: () => void;
  children: ReactNode;
  alignTop?: boolean;
  topOffset?: number;
}) {
  return (
    <div
      className="absolute inset-0 z-50 flex justify-center"
      style={{ background: "rgba(0, 32, 95, 0.5)", alignItems: alignTop ? "flex-start" : "center" }}
      onClick={onClose}
    >
      <div
        className="bg-mainbg rounded-[10px] shadow-[0_4px_4px_rgba(0,0,0,0.25)] overflow-visible"
        style={alignTop ? { marginTop: topOffset } : {}}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

function CloseBtn({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick} className="w-7 h-7 shrink-0 hover:opacity-70 transition-opacity">
      <svg viewBox="0 0 28 28" fill="none" className="w-full h-full">
        <line x1="7" y1="7" x2="21" y2="21" stroke="#00205F" strokeWidth="2" strokeLinecap="round" />
        <line x1="21" y1="7" x2="7" y2="21" stroke="#00205F" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </button>
  );
}

/** Blue pill input/field container */
function BlueField({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("w-full h-[41px] bg-cardbg rounded-btn flex items-center px-5 relative", className)}>
      {children}
    </div>
  );
}

/** Bottom action buttons */
function ModalButtons({
  onCancel,
  onConfirm,
  confirmLabel,
  disabled,
}: {
  onCancel: () => void;
  onConfirm: () => void;
  confirmLabel: string;
  disabled?: boolean;
}) {
  return (
    <div className="flex justify-end gap-[10px]">
      <button
        onClick={onCancel}
        className="px-5 py-[3px] h-[34px] border-2 border-cta rounded-btn text-cta text-meta
                   hover:bg-cta/10 transition-colors"
      >
        Отмена
      </button>
      <button
        onClick={onConfirm}
        disabled={disabled}
        className="px-5 py-[3px] h-[34px] bg-cta border-2 border-cta rounded-btn text-white text-meta
                   hover:bg-active transition-colors disabled:opacity-60 disabled:cursor-default"
      >
        {confirmLabel}
      </button>
    </div>
  );
}

/* ─────────────────────────────────────────────────
   MODAL 1 — Create project (type selection)
───────────────────────────────────────────────── */

export function CreateProjectModal({
  onClose,
  onBlank,
  onTemplate,
  onModules,
}: {
  onClose: () => void;
  onBlank: () => void;
  onTemplate: () => void;
  onModules: () => void;
}) {
  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 505 }} className="px-10 pb-8">
        {/* Header */}
        <div className="flex justify-end items-center pt-[30px] mb-5">
          <CloseBtn onClick={onClose} />
        </div>

        {/* Приложение */}
        <div className="flex flex-col gap-5 mb-[30px]">
          <span className="text-[18px] font-bold text-primary">Приложение</span>

          <button onClick={onBlank} className="flex items-center gap-[19px] text-meta text-primary hover:text-cta transition-colors text-left">
            <span className="w-[28px] h-[28px] shrink-0"><FileIcon /></span>
            <span>Пустое приложение</span>
          </button>
          <button onClick={onTemplate} className="flex items-center gap-[32px] text-meta text-primary hover:text-cta transition-colors text-left">
            <span className="w-[32px] h-[32px] shrink-0"><FolderDupIcon /></span>
            <span>Из шаблона</span>
          </button>
          <button onClick={onModules} className="flex items-center gap-[17px] text-meta text-primary hover:text-cta transition-colors text-left">
            <span className="w-[26px] h-[26px] shrink-0"><ArchiveIcon /></span>
            <span>Из набора модулей</span>
          </button>
        </div>

        {/* База данных */}
        <div className="flex flex-col gap-5">
          <span className="text-[18px] font-bold text-primary">База данных</span>

          <button onClick={onBlank} className="flex items-center gap-[18px] text-meta text-primary hover:text-cta transition-colors text-left">
            <span className="w-[24px] h-[24px] shrink-0"><DbOutlineIcon /></span>
            <span>Новая база данных</span>
          </button>
          <button disabled title="В разработке" className="flex items-center gap-[18px] text-meta text-primary/40 cursor-not-allowed text-left">
            <span className="w-[18px] h-[23px] shrink-0 flex items-center justify-center">
              <SheetsIcon />
            </span>
            <span>Импортировать из Sheets</span>
          </button>
          <button disabled title="В разработке" className="flex items-center gap-[18px] text-meta text-primary/40 cursor-not-allowed text-left">
            <span className="w-[23px] h-[25px] shrink-0 flex items-center justify-center">
              <ExcelIcon />
            </span>
            <span>Импортировать из Excel</span>
          </button>
        </div>
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   MODAL 2 — New App form
───────────────────────────────────────────────── */

const CATEGORY_PLACEHOLDER = "Выберете категорию...";

const CATEGORIES = [
  "Проверки и обследования",
  "Выездное обслуживание",
  "Управление недвижимостью",
  "Продажи и CRM",
  "Управление запасами",
  "Взаимодействие с клиентами",
  "Управление персоналом",
  "Планирование и управление проектами",
  "Обучение и тренинги",
  "Другое",
];

/** Custom category dropdown — Figma "категории приложений" */
function CategorySelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
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

  const options = [CATEGORY_PLACEHOLDER, ...CATEGORIES];

  return (
    <div ref={ref} className="relative">
      {/* Trigger */}
      <BlueField>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="w-full flex items-center justify-between text-[18px] text-primary cursor-pointer pr-1"
        >
          <span className={cn(!value && "opacity-70")}>{value || CATEGORY_PLACEHOLDER}</span>
          <span className={cn("text-xs transition-transform", open && "rotate-180")}>▾</span>
        </button>
      </BlueField>

      {/* Open panel — overflow-visible on Overlay allows this to escape */}
      {open && (
        <div
          className="absolute left-0 top-full mt-2 z-20 w-full bg-white rounded-[25px] p-[5px] flex flex-col"
          style={{ boxShadow: "10px 10px 20px rgba(0,0,0,0.25), -10px -10px 20px rgba(0,0,0,0.25)" }}
        >
          {options.map((label, i) => {
            const isPlaceholder = i === 0;
            const isSelected = isPlaceholder ? !value : label === value;
            return (
              <button
                key={label}
                type="button"
                onClick={() => {
                  onChange(isPlaceholder ? "" : label);
                  setOpen(false);
                }}
                className={cn(
                  "w-full h-12 shrink-0 flex items-center px-[30px] border-2 border-white rounded-btn",
                  "text-meta font-medium text-primary text-left transition-colors",
                  isSelected ? "bg-selected" : "bg-mainbg hover:bg-cardbg",
                )}
                style={{ marginTop: i === 0 ? 0 : -2 }}
              >
                {label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

const VIEW_TEMPLATES = [
  { label: "Календарь", icon: <CalendarIcon /> },
  { label: "Колода",    icon: <DeckIcon /> },
  { label: "Таблица",   icon: <TableTplIcon /> },
  { label: "Галерея",   icon: <GalleryIcon /> },
  { label: "Детали",    icon: <DetailsIcon /> },
];

const TABLE_TEMPLATES = [
  { label: "Бракераж" },
  { label: "Отчет" },
  { label: "Детали" },
  { label: "Аудит" },
];

function TemplateItem({
  label,
  icon,
  selected,
  onSelect,
}: {
  label: string;
  icon?: ReactNode;
  selected?: boolean;
  onSelect?: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={cn(
        "flex flex-col items-center justify-center gap-[5px] rounded-[5px] transition-all cursor-pointer",
        selected
          ? "bg-cta/20 ring-2 ring-cta opacity-100"
          : "bg-cardbg hover:opacity-100 opacity-85",
      )}
      style={{ width: 81, height: 75 }}
    >
      {icon ? (
        <span className={cn("w-[35px] h-[35px] flex items-center justify-center", selected && "[&_path]:stroke-cta [&_rect]:stroke-cta [&_line]:stroke-cta [&_circle]:stroke-cta")}>
          {icon}
        </span>
      ) : (
        <span className="w-[24px] h-[24px] flex items-center justify-center"><DbOutlineIcon /></span>
      )}
      <span className={cn("text-[12px] font-medium leading-tight", selected ? "text-cta" : "text-primary")}>
        {label}
      </span>
    </button>
  );
}

export function NewAppModal({
  onClose,
  onConfirm,
  isSubmitting = false,
}: {
  onClose: () => void;
  onConfirm: (name: string, category: string) => void;
  isSubmitting?: boolean;
}) {
  const [appName, setAppName] = useState("New App");
  const [category, setCategory] = useState("");
  const [selectedView, setSelectedView]   = useState<string | null>(null);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const hasCategory = category !== "";

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 505 }} className="px-10 py-[30px] flex flex-col gap-5">
        {/* Title */}
        <h2 className="text-[18px] font-bold text-primary">Создайте новое приложение</h2>

        {/* App name */}
        <div className="flex flex-col gap-[10px]">
          <label className="text-meta text-primary font-medium">Название приложения</label>
          <BlueField>
            <input
              value={appName}
              onChange={(e) => setAppName(e.target.value)}
              className="w-full bg-transparent outline-none text-[18px] text-primary"
            />
          </BlueField>
        </div>

        {/* Category */}
        <div className="flex flex-col gap-[10px]">
          <label className="text-meta text-primary font-medium">Категория</label>
          <CategorySelect value={category} onChange={setCategory} />
        </div>

        {/* View templates */}
        {hasCategory && (
          <div className="flex flex-col gap-[10px]">
            <label className="text-meta text-primary font-medium">
              Шаблоны представлений для данной категории
            </label>
            <div className="flex gap-[13px] flex-wrap">
              {VIEW_TEMPLATES.map((t) => (
                <TemplateItem
                  key={t.label}
                  label={t.label}
                  icon={t.icon}
                  selected={selectedView === t.label}
                  onSelect={() => setSelectedView(selectedView === t.label ? null : t.label)}
                />
              ))}
            </div>
          </div>
        )}

        {/* Table templates */}
        {hasCategory && (
          <div className="flex flex-col gap-[10px]">
            <label className="text-meta text-primary font-medium">
              Шаблоны таблиц для данной категории
            </label>
            <div className="flex gap-[13px] flex-wrap">
              {TABLE_TEMPLATES.map((t) => (
                <TemplateItem
                  key={t.label}
                  label={t.label}
                  selected={selectedTable === t.label}
                  onSelect={() => setSelectedTable(selectedTable === t.label ? null : t.label)}
                />
              ))}
              {/* + button */}
              <button
                className="flex items-center justify-center rounded-[5px] bg-cardbg hover:opacity-100 transition-opacity"
                style={{ width: 81, height: 75, opacity: 0.85 }}
              >
                <div className="w-[38px] h-[38px] bg-white rounded-full flex items-center justify-center">
                  <svg viewBox="0 0 20 20" fill="none" className="w-5 h-5">
                    <line x1="10" y1="3" x2="10" y2="17" stroke="#00205F" strokeWidth="2" strokeLinecap="round" />
                    <line x1="3" y1="10" x2="17" y2="10" stroke="#00205F" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                </div>
              </button>
            </div>
          </div>
        )}

        {/* Buttons */}
        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm(appName.trim(), category)}
          confirmLabel={isSubmitting ? "Создание…" : "Создать приложение"}
          disabled={isSubmitting || appName.trim().length < 2}
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   MODAL 3 — Share / Use app (URLs)
───────────────────────────────────────────────── */

function UrlRow({ label, url }: { label: string; url: string }) {
  const [copied, setCopied] = useState(false);
  function copy() {
    void navigator.clipboard?.writeText(url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }
  return (
    <div className="flex flex-col gap-[5px]">
      <span className="text-meta text-primary font-medium">{label}</span>
      <div className="flex items-center gap-[10px]">
        <BlueField className="flex-1">
          <a href={url} target="_blank" rel="noopener noreferrer" className="text-[18px] text-primary truncate hover:underline">{url}</a>
        </BlueField>
        <button onClick={copy} title={copied ? "Скопировано" : "Копировать"} className="shrink-0 w-[34px] h-[40px] flex items-center justify-center hover:opacity-70">
          <CopyIcon />
        </button>
      </div>
      {copied && <span className="text-[12px] text-[#20BE4F]">Скопировано</span>}
    </div>
  );
}

export function ShareModal({ onClose, appId }: { onClose: () => void; appId?: string | null }) {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const runtimeUrl = buildRuntimeUrl(appId, origin);
  const editorUrl = buildEditorUrl(appId, origin);
  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 505 }} className="px-10 pb-8">
        {/* Header — close only */}
        <div className="flex justify-end pt-[30px] mb-5">
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-5">
          {/* Использовать приложение */}
          <span className="text-[18px] font-bold text-primary">Использовать приложение</span>
          <UrlRow label="Установить на мобильное устройство" url={runtimeUrl} />
          <UrlRow label="Открыть в браузере" url={runtimeUrl} />

          {/* Редактировать */}
          <div className="pt-[10px] flex flex-col gap-5">
            <span className="text-[18px] font-medium text-primary">Редактировать приложение</span>
            <UrlRow label="Просмотр / копирование или редактирование" url={editorUrl} />
          </div>
        </div>
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   MODAL 4 — Roles / Share project
───────────────────────────────────────────────── */

const ROLE_LABELS: Record<string, string> = {
  owner: "Владелец",
  admin: "Администратор",
  editor: "Редактор",
  viewer: "Просмотр",
};

/** Copy to clipboard with a textarea fallback (Clipboard API requires HTTPS). */
function copyText(text: string) {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).catch(() => copyTextFallback(text));
    return;
  }
  copyTextFallback(text);
}

function copyTextFallback(text: string) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  document.execCommand("copy");
  document.body.removeChild(ta);
}

const LINK_ROLE_OPTIONS: { value: InviteRole; label: string }[] = [
  { value: "viewer", label: "Просмотр" },
  { value: "editor", label: "Редактор" },
  { value: "admin", label: "Администратор" },
];

const LINK_DAYS_OPTIONS: { value: number | null; label: string }[] = [
  { value: 1, label: "1 день" },
  { value: 7, label: "7 дней" },
  { value: 30, label: "30 дней" },
  { value: null, label: "Бессрочно" },
];

function initials(email: string, displayName?: string | null): string {
  if (displayName) {
    const parts = displayName.trim().split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return parts[0].slice(0, 2).toUpperCase();
  }
  return email.slice(0, 1).toUpperCase();
}

export function RolesModal({
  onClose,
  projectName = "Дикая Сибирь",
  appId,
}: {
  onClose: () => void;
  projectName?: string;
  appId?: string | null;
}) {
  const [linkCopied, setLinkCopied] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteError, setInviteError] = useState("");
  const [extraOpen, setExtraOpen] = useState(false);
  const { data: members, isLoading } = useAppMembers(appId);
  const { data: allUsers } = useUsers();
  const removeMember = useRemoveAppMember(appId ?? "");
  const addMember = useAddAppMember(appId ?? "");
  const inviteUser = useInviteUser();

  const [linkRole, setLinkRole] = useState<InviteRole>("viewer");
  const [linkDays, setLinkDays] = useState<number | null>(7);
  const [linkUrl, setLinkUrl] = useState<string | null>(null);
  const [linkError, setLinkError] = useState("");
  const { data: inviteLinks } = useInviteLinks(appId);
  const createLink = useCreateInviteLink(appId ?? "");
  const revokeLink = useRevokeInviteLink(appId ?? "");

  /** Create a real invite link (token grants membership) and copy it. */
  function copyLink() {
    if (!appId || createLink.isPending) return;
    setLinkError("");
    createLink.mutate(
      { role: linkRole, expires_in_days: linkDays },
      {
        onSuccess: (created) => {
          const url = buildInviteUrl(created.token, window.location.origin);
          setLinkUrl(url);
          copyText(url);
          setLinkCopied(true);
          setTimeout(() => setLinkCopied(false), 1500);
        },
        onError: (err) => {
          setLinkError(
            isAxiosError(err) && err.response?.status === 403
              ? "Создавать ссылки могут только владелец и администраторы приложения"
              : "Не удалось создать ссылку",
          );
        },
      },
    );
  }

  function handleInviteKey(e: React.KeyboardEvent) {
    if (e.key !== "Enter") return;
    const email = inviteEmail.trim();
    if (!email) return;
    const user = allUsers?.items.find((u) => u.email === email);
    if (!user) {
      inviteUser.mutate(
        { email, display_name: email, roles: [] },
        {
          onSuccess: (newUser) => {
            addMember.mutate(
              { userId: newUser.id, role: "editor" },
              {
                onSuccess: () => {
                  setInviteEmail("");
                  setInviteError(
                    newUser.email_sent || !newUser.temp_password
                      ? ""
                      : `Письмо не отправлено. Передайте вручную: ${newUser.email} / ${newUser.temp_password}`,
                  );
                },
              },
            );
          },
          onError: () => { setInviteError("Не удалось отправить приглашение"); },
        },
      );
      return;
    }
    const already = (members ?? []).some((m) => m.user_id === user.id);
    if (already) {
      setInviteError("Пользователь уже добавлен");
      return;
    }
    addMember.mutate(
      { userId: user.id, role: "editor" },
      { onSuccess: () => { setInviteEmail(""); setInviteError(""); } },
    );
  }

  return (
    <Overlay onClose={onClose} alignTop topOffset={85}>
      <div style={{ width: 703 }} className="px-10 flex flex-col gap-5">
        {/* Header */}
        <div className="flex flex-col gap-[10px] border-b-2 border-white pb-[5px]">
          <div className="flex justify-between items-start pt-[30px]">
            <div>
              <p className="text-[20px] font-bold text-primary leading-[150%]">
                Поделиться «{projectName}»
              </p>
              <p className="text-meta text-primary/70">
                {isLoading ? "Загрузка…" : `${members?.length ?? 0} пользователей`}
              </p>
            </div>
            <button className="mt-1 hover:opacity-70">
              <GearIcon />
            </button>
          </div>

          {/* Email input */}
          <BlueField>
            <input
              value={inviteEmail}
              onChange={(e) => { setInviteEmail(e.target.value); setInviteError(""); }}
              onKeyDown={handleInviteKey}
              placeholder="Добавить email или домен (Enter для добавления)"
              className="w-full bg-transparent outline-none text-[18px] text-primary placeholder-primary/50"
            />
          </BlueField>
          {inviteError && (
            <p className="text-[13px] text-red-400 -mt-2 pl-1">{inviteError}</p>
          )}
        </div>

        {/* Auth toggle */}
        <div className="flex flex-col gap-[10px]">
          <p className="text-meta text-primary">
            Поставщик услуг аутентификации для доступа к приложению:{" "}
            <button className="underline text-cta hover:opacity-80">Нет</button>
          </p>
          <button
            onClick={() => setExtraOpen((v) => !v)}
            className="flex items-center gap-[15px] w-fit"
          >
            <div className={cn(
              "relative w-[38px] h-[21px] rounded-full transition-colors duration-200",
              extraOpen ? "bg-cta" : "bg-cardbg",
            )}>
              <div className={cn(
                "absolute top-0 w-[21px] h-[21px] rounded-full bg-white border border-white/60 shadow transition-all duration-200",
                extraOpen ? "left-[17px]" : "left-0",
              )} />
            </div>
            <span className="text-meta text-primary">Дополнительно</span>
          </button>
          {extraOpen && (
            <div className="rounded-lg bg-cardbg/60 px-4 py-3 text-[14px] text-primary/70">
              Расширенные настройки доступа в разработке
            </div>
          )}
        </div>

        {/* Invite link settings + active links */}
        {appId && (
          <div className="flex flex-col gap-[10px]">
            <div className="flex items-center gap-[10px] flex-wrap text-meta text-primary">
              <span>Ссылка-приглашение: роль</span>
              <select
                value={linkRole}
                onChange={(e) => setLinkRole(e.target.value as InviteRole)}
                className="bg-cardbg rounded-[8px] px-2 h-[30px] outline-none text-[15px]"
              >
                {LINK_ROLE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <span>срок</span>
              <select
                value={linkDays ?? ""}
                onChange={(e) => setLinkDays(e.target.value ? Number(e.target.value) : null)}
                className="bg-cardbg rounded-[8px] px-2 h-[30px] outline-none text-[15px]"
              >
                {LINK_DAYS_OPTIONS.map((o) => <option key={o.label} value={o.value ?? ""}>{o.label}</option>)}
              </select>
            </div>
            {linkUrl && (
              <input
                readOnly
                value={linkUrl}
                onFocus={(e) => e.currentTarget.select()}
                className="w-full h-[34px] px-3 bg-cardbg rounded-[8px] text-[13px] text-primary outline-none"
              />
            )}
            {linkError && <p className="text-[13px] text-red-400 pl-1">{linkError}</p>}
            {(inviteLinks ?? []).length > 0 && (
              <div className="flex flex-col gap-[6px]">
                <span className="text-[13px] text-primary/60">Активные ссылки</span>
                {(inviteLinks ?? []).map((l) => (
                  <div key={l.id} className="flex justify-between items-center text-[13px] text-primary">
                    <span>
                      {ROLE_LABELS[l.role] ?? l.role}
                      {" · "}
                      {l.expires_at ? `до ${new Date(l.expires_at).toLocaleDateString("ru-RU")}` : "бессрочно"}
                      {" · "}
                      использована {l.use_count}{l.max_uses ? ` из ${l.max_uses}` : ""}
                    </span>
                    <button
                      onClick={() => revokeLink.mutate(l.id)}
                      className="text-primary/50 hover:text-red-400 transition-colors underline"
                    >
                      Отозвать
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Users list */}
        <div className="flex flex-col gap-[10px] max-h-[260px] overflow-y-auto">
          {isLoading && (
            <p className="text-meta text-primary/50 text-center py-4">Загрузка…</p>
          )}
          {!isLoading && (members ?? []).length === 0 && (
            <p className="text-meta text-primary/50 text-center py-4">Нет участников</p>
          )}
          {(members ?? []).map((m) => {
            const label = ROLE_LABELS[m.role] ?? m.role;
            const isOwner = m.role === "owner";
            return (
              <div key={m.user_id} className="flex justify-between items-center h-[34px]">
                <div className="flex items-center gap-[15px]">
                  <div className="w-[34px] h-[34px] bg-cardbg rounded-full flex items-center justify-center
                                  text-[15px] font-medium text-cta shrink-0">
                    {initials(m.email ?? "?", m.display_name)}
                  </div>
                  <div className="flex flex-col">
                    <span className="text-meta text-primary leading-tight">
                      {m.display_name || m.email}
                    </span>
                    {m.display_name && (
                      <span className="text-[12px] text-primary/50 leading-tight">{m.email}</span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-[10px]">
                  {isOwner ? (
                    <span className="text-[14px] italic text-primary">{label}</span>
                  ) : (
                    <>
                      <span className="text-[14px] text-primary">{label}</span>
                      <span className="text-primary text-[10px]">▾</span>
                      <button
                        onClick={() => removeMember.mutate(m.user_id)}
                        title="Удалить"
                        className="text-primary/30 hover:text-red-400 transition-colors ml-1"
                      >
                        <svg viewBox="0 0 14 14" fill="none" className="w-3.5 h-3.5">
                          <path d="M2 2l10 10M12 2L2 12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                        </svg>
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Bottom buttons */}
        <div className="flex justify-between items-center py-[30px]">
          <div className="flex gap-5">
            <button onClick={copyLink} disabled={!appId || createLink.isPending}
              title="Создать ссылку-приглашение и скопировать её"
              className="flex items-center gap-[10px] px-5 py-[3px] h-[34px]
                         border-2 border-cta rounded-btn text-cta text-meta hover:bg-cta/10 transition-colors">
              <span className="w-[25px] h-[25px]"><LinkIcon /></span>
              <span>{linkCopied ? "Скопировано" : createLink.isPending ? "Создаём…" : "Ссылка-приглашение"}</span>
            </button>
            <button disabled title="В разработке"
              className="flex items-center gap-[10px] px-5 py-[3px] h-[34px]
                         border-2 border-cta/40 rounded-btn text-cta/40 text-meta cursor-not-allowed">
              <span className="w-[21px] h-[25px]"><CopyIcon /></span>
              <span>Копировать пользователя</span>
            </button>
          </div>
          <button
            onClick={onClose}
            className="px-5 py-[3px] h-[34px] bg-cta border-2 border-cta rounded-btn
                       text-white text-meta hover:bg-active transition-colors"
          >
            Готово
          </button>
        </div>
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   MODAL 5 — Delete confirmation
───────────────────────────────────────────────── */

export function DeleteDbModal({
  onClose,
  onConfirm,
  name = "Дикая Сибирь",
}: {
  onClose: () => void;
  onConfirm: () => void;
  name?: string;
}) {
  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 505 }} className="px-10 pb-8">
        <div className="pt-[30px] mb-4">
          <h2 className="text-[22px] font-bold text-primary">Удалить «{name}»?</h2>
        </div>
        <p className="text-meta text-primary mb-4 leading-[1.6]">
          Вы уверены, что хотите удалить приложение «{name}»? Это действие нельзя отменить.
        </p>
        <div
          className="flex items-start gap-3 rounded-[10px] px-4 py-3 mb-6"
          style={{ background: "#EBF4FF" }}
        >
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 shrink-0 mt-0.5 text-cta">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
          </svg>
          <p className="text-[14px] text-cta leading-[1.5]">
            При удалении базы данных будут удалены и ее таблицы
          </p>
        </div>
        <ModalButtons onCancel={onClose} onConfirm={onConfirm} confirmLabel="Удалить" />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   MODAL 6 — Select database
───────────────────────────────────────────────── */

export function SelectDbModal({
  onClose,
  onNew,
}: {
  onClose: () => void;
  onNew: () => void;
}) {
  const [search, setSearch] = useState("");

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 505 }} className="px-10 pb-8">
        {/* Header with back + close */}
        <div className="flex items-center gap-3 pt-[30px] mb-5">
          <button
            onClick={onClose}
            className="w-6 h-6 shrink-0 text-primary hover:opacity-70 flex items-center justify-center"
          >
            <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
              <path d="M19 12H5M12 5l-7 7 7 7" stroke="#00205F" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <span className="flex-1 text-[18px] font-bold text-primary">Выберете базу данных</span>
          <CloseBtn onClick={onClose} />
        </div>

        {/* Search */}
        <BlueField className="mb-4">
          <svg viewBox="0 0 20 20" fill="none" className="w-4 h-4 shrink-0 mr-3 text-primary/50">
            <circle cx="9" cy="9" r="6" stroke="currentColor" strokeWidth="2" />
            <line x1="13.5" y1="13.5" x2="18" y2="18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск"
            className="w-full bg-transparent outline-none text-[18px] text-primary placeholder-primary/40"
          />
        </BlueField>

        {/* DB item */}
        <div className="flex items-center justify-between px-4 py-3 rounded-[10px] hover:bg-mainbg cursor-pointer mb-3 group transition-colors">
          <div className="flex items-center gap-3">
            <span className="w-8 h-8 shrink-0">
              <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
                <ellipse cx="12" cy="6" rx="8" ry="3" stroke="#35A7FF" strokeWidth="2" />
                <path d="M4 6v12c0 1.66 3.58 3 8 3s8-1.34 8-3V6" stroke="#35A7FF" strokeWidth="2" />
                <path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3" stroke="#35A7FF" strokeWidth="2" />
              </svg>
            </span>
            <div>
              <p className="text-[16px] font-semibold text-primary">AppSheet Database</p>
              <p className="text-[13px] text-primary/50">5 таблиц · you@example.com</p>
            </div>
          </div>
          <svg viewBox="0 0 20 20" fill="none" className="w-4 h-4 text-primary/40 group-hover:text-cta transition-colors">
            <path d="M10 4h6v6M16 4L4 16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>

        {/* New DB button */}
        <button
          onClick={onNew}
          className="w-full flex items-center justify-center gap-2 h-[41px] border-2 border-cta rounded-btn text-cta text-meta hover:bg-cta/10 transition-colors"
        >
          <svg viewBox="0 0 20 20" fill="none" className="w-4 h-4">
            <path d="M10 3v14M3 10h14" stroke="#35A7FF" strokeWidth="2" strokeLinecap="round" />
          </svg>
          Создайте новую базу данных
        </button>
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   MODAL 7 — Action order (drag-reorder)
───────────────────────────────────────────────── */

export interface OrderableAction {
  id: string;
  name: string;
  fromState: string;
  toState: string;
}

export function ActionOrderModal({
  onClose,
  viewName = "Аналитики",
  actions,
  onSave,
  isSaving = false,
}: {
  onClose: () => void;
  viewName?: string;
  actions: OrderableAction[];
  onSave: (orderedIds: string[]) => void;
  isSaving?: boolean;
}) {
  const [items, setItems] = useState(actions);
  const dragIndex = useRef<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);

  function handleDrop(targetIndex: number) {
    const from = dragIndex.current;
    dragIndex.current = null;
    setOverIndex(null);
    if (from === null || from === targetIndex) return;
    setItems((prev) => {
      const next = [...prev];
      const [moved] = next.splice(from, 1);
      next.splice(targetIndex, 0, moved);
      return next;
    });
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 580 }} className="px-10 pb-8">
        <div className="flex items-center justify-between pt-[30px] mb-5">
          <h2 className="text-[18px] font-bold text-primary">
            Порядок действий для «{viewName}»
          </h2>
          <CloseBtn onClick={onClose} />
        </div>

        {items.length === 0 ? (
          <p className="text-[13px] text-primary/50 bg-mainbg rounded-[8px] px-3 py-3 mb-6">
            У этого процесса пока нет действий (переходов) — добавьте их на вкладке процесса.
          </p>
        ) : (
          <div className="flex flex-col gap-[5px] mb-6">
            {items.map((action, i) => (
              <div
                key={action.id}
                draggable
                onDragStart={() => { dragIndex.current = i; }}
                onDragOver={(e) => { e.preventDefault(); setOverIndex(i); }}
                onDragLeave={() => setOverIndex((v) => (v === i ? null : v))}
                onDrop={() => handleDrop(i)}
                className={cn(
                  "flex items-center gap-3 h-[46px] px-3 rounded-[5px] bg-mainbg hover:bg-cardbg/60 transition-colors cursor-grab",
                  overIndex === i && "ring-2 ring-cta/50"
                )}
              >
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
                <span className="w-5 text-[14px] font-medium text-primary/50 shrink-0">{i + 1}</span>
                <span className="w-5 h-5 shrink-0">
                  <svg viewBox="0 0 20 20" fill="none" className="w-full h-full">
                    <ellipse cx="10" cy="5" rx="6" ry="2" stroke="#00205F" strokeWidth="1.6" />
                    <path d="M4 5v10c0 1.1 2.69 2 6 2s6-.9 6-2V5" stroke="#00205F" strokeWidth="1.6" />
                    <path d="M4 10c0 1.1 2.69 2 6 2s6-.9 6-2" stroke="#00205F" strokeWidth="1.6" />
                  </svg>
                </span>
                <span className="flex-1 text-[15px] font-medium text-primary">{action.name}</span>
                <span className="px-3 py-0.5 rounded-[20px] text-[12px] font-semibold shrink-0 bg-white border border-primary/20 text-primary/60">
                  {action.fromState} → {action.toState}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="flex justify-end">
          <button
            onClick={() => onSave(items.map((a) => a.id))}
            disabled={isSaving || items.length === 0}
            className="px-5 py-[3px] h-[34px] bg-cta border-2 border-cta rounded-btn text-white text-meta hover:bg-active transition-colors disabled:opacity-50"
          >
            {isSaving ? "Сохранение…" : "Готово"}
          </button>
        </div>
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   MODAL 8 — Formula assistant
───────────────────────────────────────────────── */

const FORMULA_FUNC_TABS = [
  "Да/нет", "Математика", "Текст", "Время",
  "Столбцы", "Списки", "Глубокие ссылки", "Другие",
];

const FORMULA_ROWS: Record<string, { name: string; type: string; value: string }[]> = {
  "Да/нет": [
    { name: "{constant}", type: "boolean", value: "TRUE" },
    { name: "AND()",      type: "boolean", value: "TRUE/FALSE" },
    { name: "OR()",       type: "boolean", value: "TRUE/FALSE" },
    { name: "NOT()",      type: "boolean", value: "TRUE/FALSE" },
    { name: "IF()",       type: "any",     value: "any" },
  ],
  "Математика": [
    { name: "{constant}", type: "number", value: "1" },
    { name: "ABS()",      type: "number", value: "number" },
    { name: "CEILING()",  type: "number", value: "number" },
    { name: "FLOOR()",    type: "number", value: "number" },
    { name: "MAX()",      type: "number", value: "number" },
  ],
  "Текст": [
    { name: "{constant}",    type: "text",   value: "\"...\"" },
    { name: "CONCATENATE()", type: "text",   value: "text" },
    { name: "LEFT()",        type: "text",   value: "text" },
    { name: "LEN()",         type: "number", value: "number" },
    { name: "LOWER()",       type: "text",   value: "text" },
  ],
  "Время": [
    { name: "NOW()",   type: "datetime", value: "datetime" },
    { name: "TODAY()", type: "date",     value: "date" },
    { name: "DAY()",   type: "number",   value: "number" },
    { name: "MONTH()", type: "number",   value: "number" },
    { name: "YEAR()",  type: "number",   value: "number" },
  ],
  "Столбцы": [
    { name: "[_RowNumber]", type: "number", value: "row#" },
    { name: "[Row ID]",     type: "text",   value: "id" },
    { name: "[Модуль]",     type: "text",   value: "text" },
    { name: "[view]",       type: "app",    value: "view" },
  ],
  "Списки": [
    { name: "LIST()",   type: "list",    value: "list" },
    { name: "COUNT()",  type: "number",  value: "number" },
    { name: "IN()",     type: "boolean", value: "TRUE/FALSE" },
    { name: "SELECT()", type: "list",    value: "list" },
    { name: "FILTER()", type: "list",    value: "list" },
  ],
  "Глубокие ссылки": [
    { name: "LINKTOROW()",  type: "url", value: "url" },
    { name: "LINKTOVIEW()", type: "url", value: "url" },
    { name: "LINKTOFORM()", type: "url", value: "url" },
  ],
  "Другие": [
    { name: "USEREMAIL()", type: "email", value: "email" },
    { name: "USERNAME()",  type: "name",  value: "name" },
    { name: "USERROLE()",  type: "text",  value: "role" },
    { name: "APP()",       type: "app",   value: "app" },
  ],
};

export function FormulaAssistantModal({
  onClose,
  onSave,
  columnName = "Название",
}: {
  onClose: () => void;
  onSave: (expr: string) => void;
  columnName?: string;
}) {
  const [expr, setExpr] = useState("=");
  const [primaryTab, setPrimaryTab] = useState("Пример");
  const [funcTab, setFuncTab] = useState("Да/нет");

  const rows = FORMULA_ROWS[funcTab] ?? [];

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 680 }} className="px-10 pb-8">
        <div className="flex items-center justify-between pt-[30px] mb-4">
          <div>
            <h2 className="text-[20px] font-bold text-primary">Помощник по формуле</h2>
            <p className="text-[14px] text-primary/50">= [{columnName}]</p>
          </div>
          <CloseBtn onClick={onClose} />
        </div>

        {/* Expression textarea */}
        <textarea
          value={expr}
          onChange={(e) => setExpr(e.target.value)}
          placeholder="Начните с = для ввода формулы…"
          rows={3}
          className="w-full bg-cardbg rounded-[10px] px-5 py-3 text-[18px] text-primary outline-none resize-none placeholder-primary/40 mb-3"
        />

        {/* Validate row */}
        <div className="flex items-center gap-4 mb-5">
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 shrink-0 text-green-500">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
          <button className="text-cta text-meta hover:underline flex items-center gap-1">
            Тест
            <svg viewBox="0 0 16 16" fill="none" className="w-3 h-3">
              <path d="M10 3h3v3M13 3L4 12" stroke="#35A7FF" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>

        {/* Primary tabs: Пример / Проводник */}
        <div className="flex items-center gap-[10px] mb-3">
          {["Пример", "Проводник"].map((t) => (
            <button
              key={t}
              onClick={() => setPrimaryTab(t)}
              className={cn(
                "h-[28px] px-5 rounded-[20px] text-[14px] font-medium transition-colors",
                primaryTab === t ? "bg-cta text-white" : "bg-mainbg text-primary hover:bg-cardbg"
              )}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Function category tabs */}
        <div className="flex flex-wrap gap-[6px] mb-3">
          {FORMULA_FUNC_TABS.map((t) => (
            <button
              key={t}
              onClick={() => setFuncTab(t)}
              className={cn(
                "h-[25px] px-3 rounded-[20px] text-[12px] border transition-colors",
                funcTab === t
                  ? "border-cta text-cta bg-cta/10"
                  : "border-cardbg text-primary/60 hover:border-cta/40"
              )}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Formula table */}
        <div className="bg-mainbg rounded-[10px] overflow-hidden mb-5" style={{ maxHeight: 200, overflowY: "auto" }}>
          <table className="w-full text-[13px]">
            <thead className="sticky top-0 bg-mainbg">
              <tr className="border-b border-white">
                <th className="text-left font-semibold text-primary px-4 py-2 w-[200px]">Функция</th>
                <th className="text-left font-semibold text-primary px-4 py-2 w-[100px]">Тип</th>
                <th className="text-left font-semibold text-primary px-4 py-2">Результат</th>
                <th className="text-center font-semibold text-primary px-4 py-2 w-[90px]">Вставить</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-b border-white/60 hover:bg-white/70 transition-colors">
                  <td className="px-4 py-2 text-cta font-medium">{row.name}</td>
                  <td className="px-4 py-2 text-primary/60">{row.type}</td>
                  <td className="px-4 py-2 text-primary">{row.value}</td>
                  <td className="px-4 py-2 text-center">
                    <button
                      onClick={() => setExpr((e) => e + row.name)}
                      className="px-3 py-0.5 border border-cta rounded-[20px] text-cta text-[12px] hover:bg-cta/10 transition-colors"
                    >
                      Вставить
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onSave(expr)}
          confirmLabel="Сохранить"
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   MODAL — Clone App
───────────────────────────────────────────────── */

export function CloneAppModal({
  onClose,
  onConfirm,
  sourceName,
  isSubmitting = false,
}: {
  onClose: () => void;
  onConfirm: (name: string) => void;
  sourceName: string;
  isSubmitting?: boolean;
}) {
  const [name, setName] = useState(`${sourceName} (копия)`);

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 505 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Клонировать приложение</h2>
          <CloseBtn onClick={onClose} />
        </div>
        <p className="text-meta text-primary/70">
          Будет создана полная копия «{sourceName}» — все таблицы, поля и правила.
        </p>
        <div className="flex flex-col gap-[10px]">
          <label className="text-meta text-primary font-medium">Название клона</label>
          <BlueField>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-transparent outline-none text-[18px] text-primary"
              autoFocus
            />
          </BlueField>
        </div>
        <ModalButtons
          onCancel={onClose}
          onConfirm={() => onConfirm(name.trim())}
          confirmLabel={isSubmitting ? "Клонирование…" : "Клонировать"}
          disabled={isSubmitting || name.trim().length < 2}
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   MODAL — App Version History
───────────────────────────────────────────────── */

export function AppVersionsModal({
  onClose,
  appId,
  appName,
}: {
  onClose: () => void;
  appId: string;
  appName: string;
}) {
  const [comment, setComment] = useState("");
  const { data: snapshots, isLoading } = useAppSnapshots(appId);
  const createSnap = useCreateSnapshot();
  const rollback = useRollbackSnapshot();

  function handleCreate() {
    createSnap.mutate(
      { appId, comment: comment.trim() || null },
      { onSuccess: () => setComment("") },
    );
  }

  function handleRollback(snapshotNum: number) {
    if (!window.confirm(`Откатить приложение к снимку #${snapshotNum}? Текущие данные будут заменены.`)) return;
    rollback.mutate({ appId, snapshotNum }, { onSuccess: () => onClose() });
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 560 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">История версий — «{appName}»</h2>
          <CloseBtn onClick={onClose} />
        </div>

        {/* Create snapshot */}
        <div className="flex gap-3 items-center">
          <BlueField className="flex-1">
            <input
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Комментарий (необязательно)"
              className="w-full bg-transparent outline-none text-[16px] text-primary placeholder-primary/40"
            />
          </BlueField>
          <button
            onClick={handleCreate}
            disabled={createSnap.isPending}
            className="shrink-0 h-[41px] px-4 bg-cta rounded-btn text-white text-meta
                       hover:bg-active transition-colors disabled:opacity-60"
          >
            {createSnap.isPending ? "Сохранение…" : "Создать снимок"}
          </button>
        </div>

        {/* Snapshot list */}
        <div className="flex flex-col gap-2 max-h-[320px] overflow-y-auto">
          {isLoading && (
            <p className="text-meta text-primary/50 text-center py-4">Загрузка…</p>
          )}
          {!isLoading && (!snapshots || snapshots.length === 0) && (
            <p className="text-meta text-primary/50 text-center py-4">
              Снимков пока нет. Создайте первый.
            </p>
          )}
          {(snapshots ?? []).map((s: AppSnapshot) => (
            <div
              key={s.id}
              className="flex items-center justify-between px-4 py-3 rounded-[10px] bg-cardbg"
            >
              <div className="flex flex-col">
                <span className="text-[15px] font-semibold text-primary">
                  Снимок #{s.snapshot_num}
                </span>
                {s.comment && (
                  <span className="text-[13px] text-primary/60">{s.comment}</span>
                )}
                <span className="text-[12px] text-primary/40">
                  {formatDistanceToNow(new Date(s.created_at), { addSuffix: true, locale: ru })}
                </span>
              </div>
              <button
                onClick={() => handleRollback(s.snapshot_num)}
                disabled={rollback.isPending}
                className="px-3 py-1 border-2 border-cta rounded-btn text-cta text-[13px]
                           hover:bg-cta/10 transition-colors disabled:opacity-60"
              >
                Откатить
              </button>
            </div>
          ))}
        </div>

        <div className="flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-[3px] h-[34px] bg-cta border-2 border-cta rounded-btn
                       text-white text-meta hover:bg-active transition-colors"
          >
            Закрыть
          </button>
        </div>
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   MODAL — Create App From Template
───────────────────────────────────────────────── */

const TEMPLATE_LIST = [
  { id: "empty",                name: "Пустое приложение",         desc: "Без модулей. Настройте всё вручную." },
  { id: "trading_company",      name: "Торговая компания",          desc: "Предприятие, склад, заказы, финансы и аналитика." },
  { id: "manufacturing_company",name: "Производственное предприятие",desc: "Предприятие, склад, производство, финансы." },
  { id: "service_company",      name: "Сервисная компания",         desc: "Задачи, договоры, финансы, IT-поддержка." },
  { id: "hr_department",        name: "HR-подразделение",           desc: "Предприятие, HR и задачи." },
  { id: "document_flow",        name: "Документооборот",            desc: "Документы, договоры и справочники." },
  { id: "financial_accounting", name: "Финансовый учёт",            desc: "Предприятие, финансы и аналитика." },
];

export function CreateFromTemplateModal({
  onClose,
  onConfirm,
  isSubmitting = false,
}: {
  onClose: () => void;
  onConfirm: (name: string, templateId: string, category: string) => void;
  isSubmitting?: boolean;
}) {
  const [appName, setAppName] = useState("Новое приложение");
  const [category, setCategory] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 560 }} className="px-10 py-[30px] flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] font-bold text-primary">Создать из шаблона</h2>
          <CloseBtn onClick={onClose} />
        </div>

        <div className="flex flex-col gap-[10px]">
          <label className="text-meta text-primary font-medium">Название приложения</label>
          <BlueField>
            <input
              value={appName}
              onChange={(e) => setAppName(e.target.value)}
              className="w-full bg-transparent outline-none text-[18px] text-primary"
            />
          </BlueField>
        </div>

        <div className="flex flex-col gap-[10px]">
          <label className="text-meta text-primary font-medium">Категория</label>
          <CategorySelect value={category} onChange={setCategory} />
        </div>

        <div className="flex flex-col gap-[10px]">
          <label className="text-meta text-primary font-medium">Выберите шаблон</label>
          <div className="flex flex-col gap-2 max-h-[260px] overflow-y-auto">
            {TEMPLATE_LIST.map((t) => (
              <button
                key={t.id}
                onClick={() => setSelectedTemplate(t.id)}
                className={cn(
                  "flex flex-col items-start px-4 py-3 rounded-[10px] text-left transition-colors border-2",
                  selectedTemplate === t.id
                    ? "border-cta bg-cta/10"
                    : "border-transparent bg-cardbg hover:bg-mainbg",
                )}
              >
                <span className={cn("text-[15px] font-semibold", selectedTemplate === t.id ? "text-cta" : "text-primary")}>
                  {t.name}
                </span>
                <span className="text-[13px] text-primary/60 leading-tight">{t.desc}</span>
              </button>
            ))}
          </div>
        </div>

        <ModalButtons
          onCancel={onClose}
          onConfirm={() => selectedTemplate && onConfirm(appName.trim(), selectedTemplate, category)}
          confirmLabel={isSubmitting ? "Создание…" : "Создать"}
          disabled={isSubmitting || appName.trim().length < 2 || !selectedTemplate}
        />
      </div>
    </Overlay>
  );
}

/* ─────────────────────────────────────────────────
   ICONS (inline SVG stubs)
───────────────────────────────────────────────── */

function ArchiveIcon() {
  return (
    <svg viewBox="0 0 26 26" fill="none" className="w-full h-full">
      <rect x="3" y="12" width="20" height="11" rx="1" stroke="#00205F" strokeWidth="2.17"/>
      <path d="M9 12 L9 7 L13 3 L13 12" stroke="#00205F" strokeWidth="2.17" strokeLinejoin="round"/>
      <rect x="3" y="3" width="20" height="20" rx="1" stroke="#00205F" strokeWidth="2.17"/>
    </svg>
  );
}

function FolderDupIcon() {
  return (
    <svg viewBox="0 0 32 32" fill="none" className="w-full h-full">
      <path d="M12 7 L20 7 L20 13 L12 13 Z" stroke="#00205F" strokeWidth="2" strokeLinejoin="round"/>
      <rect x="6" y="11" width="16" height="14" rx="1.33" stroke="#00205F" strokeWidth="2"/>
    </svg>
  );
}

function FileIcon() {
  return (
    <svg viewBox="0 0 28 28" fill="none" className="w-full h-full">
      <rect x="6" y="3.5" width="16" height="21" rx="1.5" stroke="#00205F" strokeWidth="2.33"/>
      <path d="M15 3.5 L15 9 L21 9" stroke="#00205F" strokeWidth="2.33"/>
    </svg>
  );
}

function DbOutlineIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
      <ellipse cx="12" cy="6" rx="8" ry="3" stroke="#00205F" strokeWidth="2"/>
      <path d="M4 6 L4 18 C4 19.66 7.58 21 12 21 C16.42 21 20 19.66 20 18 L20 6" stroke="#00205F" strokeWidth="2"/>
      <path d="M4 12 C4 13.66 7.58 15 12 15 C16.42 15 20 13.66 20 12" stroke="#00205F" strokeWidth="2"/>
    </svg>
  );
}

function SheetsIcon() {
  return (
    <svg viewBox="0 0 18 23" fill="none" className="w-full h-full">
      <rect x="1" y="1" width="16" height="21" rx="2" fill="#0F9D58"/>
      <rect x="4" y="7"  width="10" height="2" rx="0.5" fill="white"/>
      <rect x="4" y="11" width="10" height="2" rx="0.5" fill="white"/>
      <rect x="4" y="15" width="6"  height="2" rx="0.5" fill="white"/>
    </svg>
  );
}

function ExcelIcon() {
  return (
    <svg viewBox="0 0 23 25" fill="none" className="w-full h-full">
      <rect x="1" y="1" width="21" height="23" rx="2" fill="#1D6F42"/>
      <path d="M7 8 L11.5 12.5 M11.5 8 L7 12.5" stroke="white" strokeWidth="2" strokeLinecap="round"/>
      <rect x="13" y="8"  width="6" height="2" rx="0.5" fill="white"/>
      <rect x="13" y="12" width="6" height="2" rx="0.5" fill="white"/>
      <rect x="7"  y="16" width="12" height="2" rx="0.5" fill="white"/>
    </svg>
  );
}

function CopyIcon() {
  return (
    <svg viewBox="0 0 35 40" fill="none" className="w-full h-full">
      <rect x="6"  y="7"  width="15" height="15" rx="2" stroke="#35A7FF" strokeWidth="2.86"/>
      <rect x="14" y="18" width="15" height="15" rx="2" stroke="#35A7FF" strokeWidth="2.86"/>
    </svg>
  );
}

function GearIcon() {
  return (
    <svg viewBox="0 0 26 26" fill="none" className="w-[26px] h-[26px]">
      <circle cx="13" cy="13" r="4" stroke="#00205F" strokeWidth="2"/>
      <path d="M13 2 L14.5 6 L13 2 Z M13 24 L11.5 20 L13 24 Z" stroke="#00205F" strokeWidth="2" strokeLinecap="round"/>
      <circle cx="13" cy="13" r="9" stroke="#00205F" strokeWidth="2" strokeDasharray="3 3"/>
    </svg>
  );
}

function LinkIcon() {
  return (
    <svg viewBox="0 0 25 25" fill="none" className="w-full h-full">
      <path d="M10 8 C7 8 4 10 4 13 C4 16 7 18 10 18 L13 18" stroke="#35A7FF" strokeWidth="1.72" strokeLinecap="round"/>
      <path d="M15 18 C18 18 21 16 21 13 C21 10 18 8 15 8 L12 8" stroke="#35A7FF" strokeWidth="1.72" strokeLinecap="round"/>
      <line x1="9" y1="13" x2="16" y2="13" stroke="#35A7FF" strokeWidth="1.72" strokeLinecap="round"/>
    </svg>
  );
}

/* View template icons */
function CalendarIcon() {
  return (
    <svg viewBox="0 0 35 35" fill="none" className="w-full h-full">
      <rect x="4" y="9" width="27" height="22" rx="2" stroke="#00205F" strokeWidth="2.5"/>
      <rect x="4" y="9" width="27" height="8" rx="2" fill="#00205F"/>
      <line x1="10" y1="4" x2="10" y2="10" stroke="#00205F" strokeWidth="2.5" strokeLinecap="round"/>
      <line x1="25" y1="4" x2="25" y2="10" stroke="#00205F" strokeWidth="2.5" strokeLinecap="round"/>
      <rect x="10" y="20" width="4" height="4" rx="0.5" fill="#00205F"/>
      <rect x="19" y="20" width="4" height="4" rx="0.5" fill="#00205F"/>
      <rect x="10" y="26" width="4" height="4" rx="0.5" fill="#00205F"/>
      <rect x="19" y="26" width="4" height="4" rx="0.5" fill="#00205F"/>
    </svg>
  );
}

function DeckIcon() {
  return (
    <svg viewBox="0 0 35 35" fill="none" className="w-full h-full">
      <rect x="2" y="6" width="10" height="23" rx="2" stroke="#00205F" strokeWidth="2.5"/>
      <rect x="14" y="10" width="10" height="15" rx="2" stroke="#00205F" strokeWidth="2.5"/>
      <rect x="26" y="13" width="7" height="9" rx="2" stroke="#00205F" strokeWidth="2.5"/>
    </svg>
  );
}

function TableTplIcon() {
  return (
    <svg viewBox="0 0 35 35" fill="none" className="w-full h-full">
      <rect x="4" y="6" width="27" height="23" rx="2" stroke="#00205F" strokeWidth="2.5"/>
      <rect x="4" y="6" width="27" height="8" rx="2" fill="#00205F" fillOpacity="0.15" stroke="#00205F" strokeWidth="2.5"/>
      <line x1="4" y1="22" x2="31" y2="22" stroke="#00205F" strokeWidth="1.5"/>
      <line x1="17" y1="6" x2="17" y2="29" stroke="#00205F" strokeWidth="1.5"/>
    </svg>
  );
}

function GalleryIcon() {
  return (
    <svg viewBox="0 0 35 35" fill="none" className="w-full h-full">
      <rect x="3" y="3"   width="13" height="13" rx="2" stroke="#00205F" strokeWidth="2.5"/>
      <rect x="19" y="3"  width="13" height="13" rx="2" stroke="#00205F" strokeWidth="2.5"/>
      <rect x="3" y="19"  width="13" height="13" rx="2" stroke="#00205F" strokeWidth="2.5"/>
      <rect x="19" y="19" width="13" height="13" rx="2" stroke="#00205F" strokeWidth="2.5"/>
    </svg>
  );
}

function DetailsIcon() {
  return (
    <svg viewBox="0 0 37 37" fill="none" className="w-full h-full">
      <rect x="4" y="4" width="29" height="29" rx="3" stroke="#00205F" strokeWidth="2.5"/>
      <circle cx="14" cy="14" r="4" stroke="#00205F" strokeWidth="2.5"/>
      <line x1="22" y1="12" x2="30" y2="12" stroke="#00205F" strokeWidth="2.5" strokeLinecap="round"/>
      <line x1="22" y1="17" x2="30" y2="17" stroke="#00205F" strokeWidth="2.5" strokeLinecap="round"/>
      <line x1="8"  y1="25" x2="29" y2="25" stroke="#00205F" strokeWidth="2.5" strokeLinecap="round"/>
    </svg>
  );
}
