import { useNavigate, useSearchParams } from "react-router-dom";
import { cn } from "@/lib/cn";

export type RailModule =
  | "home"
  | "analytics"
  | "constructor"
  | "data"
  | "automation"
  | "notifications"
  | "documents"
  | "security"
  | "docs";

interface IconRailProps {
  active: RailModule;
  onChange: (m: RailModule) => void;
  onCollapse?: () => void;
  onSettings?: () => void;
  collapsed?: boolean;
}

const items: { id: RailModule; label: string; icon: React.ReactNode }[] = [
  { id: "home",          label: "Главная",        icon: <HomeIcon /> },
  { id: "analytics",     label: "Аналитика",      icon: <AnalyticsIcon /> },
  { id: "data",          label: "Данные",         icon: <DataIcon /> },
  { id: "constructor",   label: "Конструктор",    icon: <ConstructorIcon /> },
  { id: "automation",    label: "Автоматизация",  icon: <RobotIcon /> },
  { id: "notifications", label: "Уведомления",    icon: <BellIcon /> },
  { id: "documents",     label: "Публикация",      icon: <DocumentIcon /> },
  { id: "security",      label: "Безопасность",   icon: <ShieldIcon /> },
  { id: "docs",          label: "Документация",   icon: <BookIcon /> },
];

/**
 * Узкая (85px) панель-рельс с иконками модулей редактора.
 * Слева на канвасе 1920×1080, начинается под навбаром (top 70px).
 */
const MODULE_ROUTES: Partial<Record<RailModule, string>> = {
  home: "/",
  constructor: "/views",
  data: "/schema",        // конструктор сущностей и схема данных
  automation: "/bot",
  analytics: "/intel",    // AI / Intelligence
  notifications: "/admin",
  documents: "/deploy",
  security: "/security",
  docs: "/learning",      // обучение / документация
};

export function IconRail({ active, onChange, onCollapse, onSettings, collapsed }: IconRailProps) {
  const navigate = useNavigate();
  const [params] = useSearchParams();

  // Preserve the active app across module switches so the editor, data and
  // automation screens stay on the same app the user opened.
  function withApp(route: string): string {
    const appId = params.get("app");
    return appId ? `${route}?app=${appId}` : route;
  }

  function handleModuleClick(id: RailModule) {
    onChange(id);
    const route = MODULE_ROUTES[id];
    if (route) navigate(withApp(route));
  }

  function handleSettings() {
    onSettings?.();
    navigate(withApp("/settings"));
  }

  return (
    <aside className="absolute left-0 top-[70px] w-[85px] h-[1010px] bg-white flex flex-col items-center px-[15px]">
      <nav className="flex flex-col gap-[15px] w-[55px] pt-0">
        {items.map((item) => (
          <button
            key={item.id}
            onClick={() => handleModuleClick(item.id)}
            aria-label={item.label}
            title={item.label}
            className={cn(
              "w-[55px] h-[55px] flex items-center justify-center rounded-nav transition-colors",
              active === item.id ? "bg-mainbg" : "hover:bg-mainbg/60"
            )}
          >
            <span className="w-[25px] h-[25px]">{item.icon}</span>
          </button>
        ))}
      </nav>

      {/* Bottom group: settings + collapse */}
      <div className="mt-auto flex flex-col items-center gap-[15px] pb-[25px]">
        <button
          onClick={handleSettings}
          aria-label="Настройки"
          title="Настройки"
          className="w-[55px] h-[55px] flex items-center justify-center rounded-nav hover:bg-mainbg/60 transition-colors"
        >
          <span className="w-[27px] h-[27px]"><SettingsIcon /></span>
        </button>
        <button
          onClick={onCollapse}
          aria-label={collapsed ? "Развернуть панель" : "Свернуть панель"}
          title={collapsed ? "Развернуть панель" : "Свернуть панель"}
          className="w-[25px] h-[28px] flex items-center justify-center hover:opacity-70 transition-opacity"
        >
          <CollapseIcon collapsed={collapsed} />
        </button>
      </div>
    </aside>
  );
}

/* ── Icons ── */
const stroke = "#00205F";

function HomeIcon() {
  return (
    <svg viewBox="0 0 25 25" fill="none" className="w-full h-full">
      <path d="M3 10 L12.5 3 L22 10 L22 22 L3 22 Z" stroke={stroke} strokeWidth="2" strokeLinejoin="round" />
      <rect x="9" y="15" width="7" height="7" fill={stroke} rx="1" />
    </svg>
  );
}

function AnalyticsIcon() {
  return (
    <svg viewBox="0 0 25 25" fill="none" className="w-full h-full">
      <rect x="2" y="13" width="5" height="9" rx="1" stroke={stroke} strokeWidth="2" />
      <rect x="10" y="8" width="5" height="14" rx="1" stroke={stroke} strokeWidth="2" />
      <rect x="18" y="3" width="5" height="19" rx="1" stroke={stroke} strokeWidth="2" />
    </svg>
  );
}

function ConstructorIcon() {
  return (
    <svg viewBox="0 0 25 25" fill="none" className="w-full h-full">
      <rect x="2" y="2" width="9" height="9" rx="1.5" stroke={stroke} strokeWidth="2" />
      <rect x="14" y="2" width="9" height="9" rx="1.5" stroke={stroke} strokeWidth="2" />
      <rect x="2" y="14" width="9" height="9" rx="1.5" stroke={stroke} strokeWidth="2" />
      <rect x="14" y="14" width="9" height="9" rx="1.5" stroke={stroke} strokeWidth="2" />
    </svg>
  );
}

function DataIcon() {
  return (
    <svg viewBox="0 0 25 24" fill="none" className="w-full h-full">
      <ellipse cx="12.5" cy="4" rx="9" ry="3" stroke={stroke} strokeWidth="2" />
      <path d="M3.5 4 L3.5 20 C3.5 21.66 7.5 23 12.5 23 C17.5 23 21.5 21.66 21.5 20 L21.5 4" stroke={stroke} strokeWidth="2" />
      <path d="M3.5 12 C3.5 13.66 7.5 15 12.5 15 C17.5 15 21.5 13.66 21.5 12" stroke={stroke} strokeWidth="2" />
    </svg>
  );
}

function RobotIcon() {
  return (
    <svg viewBox="0 0 25 25" fill="none" className="w-full h-full">
      <rect x="4" y="8" width="17" height="13" rx="2" stroke={stroke} strokeWidth="2" />
      <line x1="12.5" y1="3" x2="12.5" y2="8" stroke={stroke} strokeWidth="2" strokeLinecap="round" />
      <circle cx="12.5" cy="3" r="1.5" fill={stroke} />
      <circle cx="9.5" cy="14" r="1.5" fill={stroke} />
      <circle cx="15.5" cy="14" r="1.5" fill={stroke} />
    </svg>
  );
}

function BellIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
      <path d="M5 18 L19 18 L19 17 L17 14 L17 10 C17 6.5 14.5 4 12 4 C9.5 4 7 6.5 7 10 L7 14 L5 17 Z"
            stroke={stroke} strokeWidth="2" strokeLinejoin="round" />
      <path d="M10 21 C10.5 22 13.5 22 14 21" stroke={stroke} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function DocumentIcon() {
  return (
    <svg viewBox="0 0 25 25" fill="none" className="w-full h-full">
      <path d="M5 2 L15 2 L20 7 L20 23 L5 23 Z" stroke={stroke} strokeWidth="2" strokeLinejoin="round" />
      <path d="M15 2 L15 7 L20 7" stroke={stroke} strokeWidth="2" strokeLinejoin="round" />
      <line x1="9" y1="13" x2="16" y2="13" stroke={stroke} strokeWidth="1.6" strokeLinecap="round" />
      <line x1="9" y1="17" x2="16" y2="17" stroke={stroke} strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg viewBox="0 0 25 25" fill="none" className="w-full h-full">
      <path d="M12.5 2 L21 5 L21 12 C21 17.5 17 21.5 12.5 23 C8 21.5 4 17.5 4 12 L4 5 Z"
            stroke={stroke} strokeWidth="2" strokeLinejoin="round" />
      <path d="M9 12 L11.5 14.5 L16 9.5" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function BookIcon() {
  return (
    <svg viewBox="0 0 25 25" fill="none" className="w-full h-full">
      <path d="M12.5 5 C10 3 6 3 3 4 L3 20 C6 19 10 19 12.5 21 C15 19 19 19 22 20 L22 4 C19 3 15 3 12.5 5 Z"
            stroke={stroke} strokeWidth="2" strokeLinejoin="round" />
      <line x1="12.5" y1="5" x2="12.5" y2="21" stroke={stroke} strokeWidth="2" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg viewBox="0 0 27 27" fill="none" className="w-full h-full">
      <circle cx="13.5" cy="13.5" r="3.5" stroke={stroke} strokeWidth="2" />
      <path d="M13.5 2 L13.5 5 M13.5 22 L13.5 25 M2 13.5 L5 13.5 M22 13.5 L25 13.5 M5.5 5.5 L7.6 7.6 M19.4 19.4 L21.5 21.5 M5.5 21.5 L7.6 19.4 M19.4 7.6 L21.5 5.5"
            stroke={stroke} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function CollapseIcon({ collapsed }: { collapsed?: boolean }) {
  return collapsed ? (
    <svg viewBox="0 0 25 25" fill="none" className="w-[25px] h-[25px]">
      <path d="M11 7 L16 12.5 L11 18" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6 7 L11 12.5 L6 18" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ) : (
    <svg viewBox="0 0 25 25" fill="none" className="w-[25px] h-[25px]">
      <path d="M14 7 L9 12.5 L14 18" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M19 7 L14 12.5 L19 18" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
