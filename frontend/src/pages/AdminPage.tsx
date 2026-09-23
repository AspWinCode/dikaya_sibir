import { useEffect, useRef, useState } from "react";
import { Navbar } from "@/components/layout/Navbar";
import { cn } from "@/lib/cn";
import { PasswordInput } from "@/shared/components/PasswordInput";
import { useUsers, useDeactivateUser, useUpdateUser, useHardDeleteUser, useInviteUser, useSetUserPassword, useRoles } from "@/shared/hooks/useUsers";
import { useGroups, useCreateGroup, useUpdateGroup, useDeleteGroup, useGroup, useAddGroupMember, useRemoveGroupMember, useApplyGroupRoles } from "@/shared/hooks/useGroups";
import { useAuditLogs } from "@/shared/hooks/useAuditLogs";
import { useApps } from "@/shared/hooks/useApps";
import { useOrgs, useCreateOrg, useUpdateOrg } from "@/shared/hooks/useOrgs";
import { useHealth } from "@/shared/hooks/useHealth";
import { useAuthStore } from "@/shared/auth/store";
import { useAllSessions, useTerminateSession, useTerminateUserSessions } from "@/shared/hooks/useSessions";
import { useAllRoles, useCreateRole, useDeleteRole } from "@/shared/hooks/useRbac";
import { EmailTemplatesContent } from "@/pages/EmailTemplatesPage";

/* ── Types ── */
type AdminSection = "home" | "orgs" | "logs" | "users" | "groups" | "roles" | "apps" | "databases" | "sessions" | "notifications";

const ALL_ADMIN_ITEMS: { id: AdminSection; label: string; icon: React.ReactNode; platformOnly?: boolean }[] = [
  { id: "home",      label: "Главная",        icon: <HomeIcon /> },
  { id: "orgs",      label: "Организации",    icon: <OrgsIcon />, platformOnly: true },
  { id: "users",     label: "Пользователи",   icon: <UsersIcon /> },
  { id: "groups",    label: "Группы",         icon: <GroupsIcon /> },
  { id: "roles",     label: "Роли",           icon: <RolesNavIcon /> },
  { id: "apps",      label: "Приложения",     icon: <AppsIcon />, platformOnly: true },
  { id: "databases", label: "Базы данных",    icon: <DbIcon />, platformOnly: true },
  { id: "sessions",       label: "Сессии",          icon: <SessionsNavIcon /> },
  { id: "notifications",  label: "Email-шаблоны",   icon: <NotifNavIcon /> },
  { id: "logs",           label: "Журнал аудита",   icon: <LogsIcon /> },
];

function AdminSidebar({
  active,
  onChange,
  items,
}: {
  active: AdminSection;
  onChange: (s: AdminSection) => void;
  items: typeof ALL_ADMIN_ITEMS;
}) {
  return (
    <aside
      className="absolute left-0 top-[70px] w-[280px] h-[1010px] flex"
      style={{ padding: "0 15px 12px" }}
    >
      <nav className="flex flex-col w-[250px] gap-[15px]">
        {items.map((item) => (
          <button
            key={item.id}
            onClick={() => onChange(item.id)}
            className={cn(
              "nav-item",
              active === item.id && "active"
            )}
          >
            <span className="w-[25px] h-[25px] shrink-0">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
    </aside>
  );
}

/* ── Dashboard (Главная) ── */
function StatRow({
  active,
  inDev,
  total,
}: {
  active: number;
  inDev: number;
  total: number;
}) {
  return (
    <div className="flex justify-between items-center w-full">
      <span className="text-info text-primary text-center w-[75px]">{active}</span>
      <span className="text-info text-primary text-center w-[120px]">{inDev}</span>
      <span className="text-info text-[#35A7FF] text-center w-[52px]">{total}</span>
    </div>
  );
}

function ServiceStatusRow({
  label,
  status,
  latencyMs,
}: {
  label: string;
  status?: string;
  latencyMs?: number;
}) {
  const ok = status === "ok";
  return (
    <div className="flex items-center gap-4">
      <div className={cn("w-3 h-3 rounded-full shrink-0", ok ? "bg-[#20BE4F]" : status == null ? "bg-cardbg" : "bg-[#C22A2A]")} />
      <span className="text-info text-primary w-[120px]">{label}</span>
      <span className={cn("text-info font-semibold", ok ? "text-[#20BE4F]" : status == null ? "text-primary/30" : "text-[#C22A2A]")}>
        {status == null ? "—" : ok ? "Активен" : "Недоступен"}
      </span>
      {latencyMs != null && (
        <span className="text-info text-primary/40 ml-auto">{latencyMs} мс</span>
      )}
    </div>
  );
}

function computePieSlices(data: { value: number; color: string }[]) {
  const total = data.reduce((s, d) => s + d.value, 0);
  if (total === 0) return [{ path: `M 100 100 m -80 0 a 80 80 0 1 0 160 0 a 80 80 0 1 0 -160 0`, color: "#E5E7EB" }];
  const slices: { path: string; color: string }[] = [];
  let current = 0;
  const cx = 100, cy = 100, r = 80;
  function toXY(angle: number) {
    const rad = (angle - 90) * (Math.PI / 180);
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
  }
  for (const d of data) {
    if (d.value === 0) continue;
    const sweep = (d.value / total) * 360;
    const start = toXY(current);
    const end = toXY(current + sweep - 0.01);
    const large = sweep > 180 ? 1 : 0;
    slices.push({
      path: `M ${cx} ${cy} L ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)} Z`,
      color: d.color,
    });
    current += sweep;
  }
  return slices;
}

function AdminDashboard() {
  const { data: appsData } = useApps();
  const { data: usersData } = useUsers();
  const { data: orgsData } = useOrgs();
  const { data: healthData } = useHealth();
  const { data: allLogs } = useAuditLogs({ limit: 500 });

  const totalApps = appsData?.total ?? 0;
  const activeApps = appsData?.items.filter((a) => a.is_published).length ?? 0;
  const devApps = totalApps - activeApps;

  const totalUsers = usersData?.total ?? 0;
  const activeUsers = usersData?.items.filter((u) => u.is_active).length ?? 0;

  // Tariff distribution
  const orgs = orgsData ?? [];
  const planData = [
    { value: orgs.filter((o) => o.plan === "trial").length,    color: "#35A7FF", label: "Бесплатный" },
    { value: orgs.filter((o) => o.plan === "pro").length,      color: "#20BE4F", label: "Про план" },
    { value: orgs.filter((o) => o.plan === "business").length, color: "#FFA600", label: "Бизнес план" },
  ];
  const pieSlices = computePieSlices(planData);

  // New users per day (last 7 days)
  const today = new Date();
  const last7Days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(today);
    d.setDate(d.getDate() - (6 - i));
    return d.toISOString().slice(0, 10);
  });
  const newUserLogs = (allLogs ?? []).filter((l) => l.action === "user_created");
  const newUsersByDay = last7Days.map((day) =>
    newUserLogs.filter((l) => l.created_at.slice(0, 10) === day).length
  );
  const maxNewUsers = Math.max(...newUsersByDay, 1);

  // Warnings from real data
  const dbOk = healthData?.database.status === "ok";
  const redisOk = healthData?.redis.status === "ok";
  const securityErrors = (allLogs ?? []).filter((l) => l.level === "error").length;
  const warnings = [
    { label: "ошибки БД",              count: healthData == null ? "—" : dbOk ? 0 : 1 },
    { label: "ошибки Redis",           count: healthData == null ? "—" : redisOk ? 0 : 1 },
    { label: "инциденты безопасности", count: securityErrors },
    { label: "интеграции недоступны",  count: healthData == null ? "—" : (!dbOk || !redisOk) ? 1 : 0 },
  ];

  return (
    <div className="flex flex-col gap-[70px] h-full">
      {/* Header */}
      <div className="flex flex-col gap-[10px]">
        <h1 className="text-[40px] font-bold text-primary leading-[150%]">
          Панель администратора
        </h1>
        <p className="text-[24px] font-medium text-primary leading-[150%]">
          Обзор состояния платформы и ключевых метрик в реальном времени
        </p>
      </div>

      {/* Cards grid */}
      <div className="flex flex-wrap gap-x-5 gap-y-[50px]">
        {/* Card 1: Apps & Users */}
        <div className="bg-white rounded-[5px] shadow-[0_4px_4px_rgba(0,0,0,0.25)] p-[30px_20px] flex flex-col gap-[30px] w-[544px]">
          <h2 className="text-card-h font-semibold text-primary">Приложения и пользователи</h2>
          <div className="flex gap-[50px] items-end">
            <div className="flex flex-col gap-[25px]">
              <span className="text-info text-primary">Пользователи</span>
              <span className="text-info text-primary">Приложения</span>
            </div>
            <div className="flex-1 flex flex-col gap-[25px]">
              <div className="flex justify-between text-info">
                <span className="text-[#20BE4F] w-[75px]">Активно</span>
                <span className="text-[#FFA600] w-[120px]">В разработке</span>
                <span className="text-cta w-[52px]">Всего</span>
              </div>
              <StatRow active={activeUsers} inDev={totalUsers - activeUsers} total={totalUsers} />
              <StatRow active={activeApps} inDev={devApps} total={totalApps} />
            </div>
          </div>
        </div>

        {/* Card 2: System Health */}
        <div className="bg-white rounded-[5px] shadow-[0_4px_4px_rgba(0,0,0,0.25)] p-[30px_20px] flex flex-col gap-[30px] w-[611px]">
          <h2 className="text-card-h font-semibold text-primary">Статус сервисов</h2>
          <div className="flex flex-col gap-5">
            <ServiceStatusRow
              label="База данных"
              status={healthData?.database.status}
              latencyMs={healthData?.database.latency_ms}
            />
            <ServiceStatusRow
              label="Redis"
              status={healthData?.redis.status}
              latencyMs={healthData?.redis.latency_ms}
            />
            <ServiceStatusRow
              label="API"
              status={healthData != null ? "ok" : undefined}
            />
          </div>
        </div>

        {/* Card 3: Warnings */}
        <div className="bg-white rounded-[5px] shadow-[0_4px_4px_rgba(0,0,0,0.25)] p-[30px_20px] flex flex-col gap-[30px] w-[315px]">
          <h2 className="text-card-h font-semibold text-[#FFA600]">Предупреждения</h2>
          <div className="flex gap-[30px]">
            <div className="flex flex-col gap-[10px] flex-1">
              {warnings.map((w) => (
                <span key={w.label} className="text-info text-primary">{w.label}</span>
              ))}
            </div>
            <div className="flex flex-col gap-[10px]">
              {warnings.map((w, i) => (
                <span
                  key={i}
                  className={cn(
                    "text-info w-[20px] text-center",
                    typeof w.count === "number" && w.count > 0 ? "text-[#FFA600] font-semibold" : "text-primary"
                  )}
                >
                  {w.count}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Card 4: Tariff distribution */}
        <div className="bg-white rounded-[5px] shadow-[0_4px_4px_rgba(0,0,0,0.25)] p-[30px_0_30px_0] flex flex-col gap-0 w-[544px]">
          <h2 className="text-card-h font-semibold text-primary px-5 mb-5">Распределение по тарифам</h2>
          <div className="flex items-center justify-between px-5">
            <div className="relative w-[200px] h-[200px] shrink-0">
              <svg viewBox="0 0 200 200" className="w-full h-full">
                {pieSlices.map((s, i) => (
                  <path key={i} d={s.path} fill={s.color} />
                ))}
                <circle cx="100" cy="100" r="40" fill="white" />
                <text x="100" y="104" textAnchor="middle" fontSize="13" fill="#00205F" fontWeight="600">
                  {orgs.length}
                </text>
              </svg>
            </div>
            <div className="flex flex-col gap-[20px]">
              {planData.map((t) => (
                <div key={t.label} className="flex items-center gap-3">
                  <div className="w-[30px] h-[18px] rounded-sm shrink-0" style={{ background: t.color }} />
                  <span className="text-info text-primary">{t.label}</span>
                  <span className="text-info text-primary/50 ml-auto">{t.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Card 5: New users chart */}
        <div className="bg-white rounded-[5px] shadow-[0_4px_4px_rgba(0,0,0,0.25)] p-[30px_0_30px_0] flex flex-col gap-5 w-[625px]">
          <h2 className="text-card-h font-semibold text-primary px-5">Новые пользователи (чел./день)</h2>
          <div className="flex items-start px-5">
            <div className="flex flex-col justify-between h-[193px] w-[30px] shrink-0 pb-1">
              {[maxNewUsers, Math.round(maxNewUsers * 0.5), 0].map((v) => (
                <span key={v} className="text-info text-primary text-right text-[12px]">{v}</span>
              ))}
            </div>
            <div className="flex-1 flex items-end justify-around h-[193px] border-b-2 border-l-2 border-cta px-2 ml-2">
              {newUsersByDay.map((h, i) => (
                <div key={i} className="flex flex-col items-center gap-1">
                  <div
                    className="w-[40px] bg-cta rounded-t-sm transition-all"
                    style={{ height: `${(h / maxNewUsers) * 170}px` }}
                  />
                  <span className="text-[10px] text-primary/40">{last7Days[i].slice(5)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Logs ── */

// Actions that belong to each tab
const USER_ACTIONS = new Set([
  "login", "login_ldap", "login_yandex",
  "record_created", "record_updated", "record_deleted",
]);
const ADMIN_ACTIONS = new Set([
  "user_created", "user_invited", "user_updated", "user_deactivated", "user_hard_deleted",
  "org_created", "org_updated",
  "group_created", "group_updated", "group_deleted",
  "group_member_added", "group_member_removed", "group_roles_applied",
]);

const LOG_TABS = [
  { id: "all",   label: "Все события" },
  { id: "user",  label: "Действия пользователей" },
  { id: "admin", label: "Администрирование" },
  { id: "warn",  label: "Важные события" },
];

interface LogEntry {
  id: string;
  rawAction: string;
  time: string;
  user: string;
  action: string;
  resource: string;
  level: "info" | "warn" | "error";
  ip: string;
  device: string;
  json: string;
}

const levelColors: Record<string, string> = {
  info:  "text-primary",
  warn:  "text-[#FFA600]",
  error: "text-[#C22A2A]",
};

const levelBg: Record<string, string> = {
  info:  "bg-primary/10 text-primary",
  warn:  "bg-[#FFA600]/15 text-[#FFA600]",
  error: "bg-[#C22A2A]/15 text-[#C22A2A]",
};

const LEVEL_LABELS: Record<string, string> = {
  info: "INFO",
  warn: "WARN",
  error: "ERROR",
};

const ACTION_LABELS: Record<string, string> = {
  // Auth
  login:                 "Вход в систему",
  login_ldap:            "Вход через LDAP",
  login_yandex:          "Вход через Яндекс ID",
  // Users
  user_created:          "Создание пользователя",
  user_invited:          "Приглашение пользователя",
  user_updated:          "Изменение пользователя",
  user_deactivated:      "Деактивация пользователя",
  user_hard_deleted:     "Удаление пользователя",
  // Orgs
  org_created:           "Создание организации",
  org_updated:           "Изменение организации",
  // Groups
  group_created:         "Создание группы",
  group_updated:         "Изменение группы",
  group_deleted:         "Удаление группы",
  group_member_added:    "Добавление в группу",
  group_member_removed:  "Исключение из группы",
  group_roles_applied:   "Применение ролей группы",
  // Records
  record_created:        "Создание записи",
  record_updated:        "Изменение записи",
  record_deleted:        "Удаление записи",
};

const RESOURCE_LABELS: Record<string, string> = {
  user:         "Пользователь",
  group:        "Группа",
  organisation: "Организация",
  record:       "Запись данных",
};

function AdminLogs() {
  const [activeTab, setActiveTab] = useState("all");
  const [search, setSearch] = useState("");
  const [selectedLog, setSelectedLog] = useState<LogEntry | null>(null);
  const { data: rawLogs, isLoading } = useAuditLogs({ limit: 500 });
  const currentUser = useAuthStore((s) => s.user);
  const isOrgAdmin = currentUser?.roles.some((r) => r.id === "org_admin") &&
    !currentUser?.roles.some((r) => r.id === "platform_admin");

  const allLogs: LogEntry[] = (rawLogs ?? []).map((e) => ({
    id:        e.id,
    rawAction: e.action,
    time:      new Date(e.created_at).toLocaleString("ru", { dateStyle: "short", timeStyle: "short" }),
    user:      e.actor_email ?? e.user_id ?? "—",
    action:    ACTION_LABELS[e.action] ?? e.action,
    resource:  (e.resource_type ? RESOURCE_LABELS[e.resource_type] ?? e.resource_type : "") +
               (e.resource_id ? ` #${e.resource_id.slice(0, 8)}` : ""),
    level:     e.level as "info" | "warn" | "error",
    ip:        e.ip_address ?? "—",
    device:    e.user_agent ?? "—",
    json:      JSON.stringify({ action: e.action, resource: e.resource_type, id: e.resource_id, ...e.details }, null, 2),
  }));

  const filteredByTab = allLogs.filter((log) => {
    if (activeTab === "all")   return true;
    if (activeTab === "user")  return USER_ACTIONS.has(log.rawAction);
    if (activeTab === "admin") return ADMIN_ACTIONS.has(log.rawAction);
    if (activeTab === "warn")  return log.level === "warn" || log.level === "error";
    return true;
  });

  const logs = search.trim()
    ? filteredByTab.filter((l) =>
        l.user.toLowerCase().includes(search.toLowerCase()) ||
        l.action.toLowerCase().includes(search.toLowerCase()) ||
        l.resource.toLowerCase().includes(search.toLowerCase())
      )
    : filteredByTab;

  const warnCount = allLogs.filter((l) => l.level === "warn" || l.level === "error").length;

  return (
    <div className="flex gap-[30px] items-start">
      {/* Left: list */}
      <div className="flex flex-col gap-[30px] flex-1 min-w-0">
        <div className="flex flex-col gap-[8px]">
          <h1 className="text-[40px] font-bold text-primary leading-[150%]">Журнал аудита</h1>
          <p className="text-[18px] text-primary/60">Неизменяемая история всех действий в системе</p>
          {isOrgAdmin && (
            <div className="flex items-center gap-2 bg-cta/5 border border-cta/20 rounded-[10px] px-4 py-2 self-start mt-1">
              <span className="text-[14px] text-cta">
                Отображаются только действия пользователей вашей организации
              </span>
            </div>
          )}
        </div>

        {/* Tabs + search */}
        <div className="flex items-center gap-[16px]">
          <div className="flex items-center bg-white rounded-tab p-[3.6px] gap-1 shrink-0">
            {LOG_TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => { setActiveTab(t.id); setSelectedLog(null); }}
                className={cn(
                  "relative px-4 py-[3.6px] rounded-tab text-[14px] text-primary transition-colors",
                  activeTab === t.id ? "bg-cardbg font-semibold" : "hover:bg-mainbg"
                )}
              >
                {t.label}
                {t.id === "warn" && warnCount > 0 && (
                  <span className="ml-1.5 inline-flex items-center justify-center w-[18px] h-[18px] rounded-full bg-[#FFA600] text-white text-[10px] font-bold">
                    {warnCount > 99 ? "99+" : warnCount}
                  </span>
                )}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-[10px] flex-1 h-[38px] px-4 bg-white rounded-[20px] shadow-sm">
            <svg viewBox="0 0 20 20" fill="none" className="w-4 h-4 shrink-0 text-primary/40">
              <circle cx="9" cy="9" r="6" stroke="currentColor" strokeWidth="1.8" />
              <line x1="13.5" y1="13.5" x2="18" y2="18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск по пользователю, действию…"
              className="flex-1 bg-transparent text-[14px] text-primary outline-none placeholder:text-primary/30"
            />
            {search && (
              <button onClick={() => setSearch("")} className="text-primary/30 hover:text-primary text-[18px] leading-none">×</button>
            )}
          </div>

          <span className="text-[13px] text-primary/40 shrink-0">{logs.length} записей</span>
        </div>

        <div className="bg-white rounded-[5px] shadow-[0_4px_4px_rgba(0,0,0,0.25)] overflow-hidden">
          <table className="w-full">
            <thead className="bg-mainbg">
              <tr>
                <th className="text-left px-6 py-3 text-[13px] font-semibold text-primary w-[130px]">Время</th>
                <th className="text-left px-6 py-3 text-[13px] font-semibold text-primary">Пользователь</th>
                <th className="text-left px-6 py-3 text-[13px] font-semibold text-primary">Действие</th>
                <th className="text-left px-6 py-3 text-[13px] font-semibold text-primary">Объект</th>
                <th className="text-left px-6 py-3 text-[13px] font-semibold text-primary w-[80px]">Уровень</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr><td colSpan={5} className="px-6 py-4 text-center text-primary/50 text-[15px]">Загрузка…</td></tr>
              )}
              {!isLoading && logs.length === 0 && (
                <tr><td colSpan={5} className="px-6 py-4 text-center text-primary/50 text-[15px]">Записей не найдено</td></tr>
              )}
              {logs.map((log) => (
                <tr
                  key={log.id}
                  onClick={() => setSelectedLog(log === selectedLog ? null : log)}
                  className={cn(
                    "border-t border-mainbg cursor-pointer transition-colors",
                    log === selectedLog ? "bg-selected" : "hover:bg-mainbg/40"
                  )}
                >
                  <td className="px-6 py-3 text-[13px] text-primary/60 font-mono whitespace-nowrap">{log.time}</td>
                  <td className="px-6 py-3 text-[14px] text-primary">{log.user}</td>
                  <td className={cn("px-6 py-3 text-[14px] font-medium", levelColors[log.level])}>{log.action}</td>
                  <td className="px-6 py-3 text-[13px] text-primary/50">{log.resource || "—"}</td>
                  <td className="px-6 py-3">
                    <span className={cn("text-[11px] font-bold px-2 py-0.5 rounded-full", levelBg[log.level])}>
                      {LEVEL_LABELS[log.level]}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Right: detail panel */}
      {selectedLog && <LogDetailPanel log={selectedLog} onClose={() => setSelectedLog(null)} />}
    </div>
  );
}

/** Download a single audit log entry as a JSON file. */
function exportLog(log: LogEntry): void {
  const payload = {
    time: log.time, user: log.user, action: log.action,
    level: log.level, ip: log.ip, device: log.device,
    details: safeParse(log.json),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `audit-log-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function safeParse(s: string): unknown {
  try { return JSON.parse(s); } catch { return s; }
}

function LogDetailPanel({ log, onClose }: { log: LogEntry; onClose: () => void }) {
  const criticalityLabel: Record<string, { label: string; color: string }> = {
    info:  { label: "Низкий",   color: "#20BE4F" },
    warn:  { label: "Средний",  color: "#FFA600" },
    error: { label: "Высокий",  color: "#C22A2A" },
  };
  const crit = criticalityLabel[log.level];

  return (
    <div className="w-[420px] shrink-0 bg-white rounded-[5px] shadow-[0_4px_4px_rgba(0,0,0,0.25)] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-mainbg">
        <span className="text-[22px] font-bold text-primary">Детали действия</span>
        <button
          onClick={onClose}
          className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-mainbg transition-colors"
          aria-label="Закрыть"
        >
          <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4">
            <path d="M3 3 L13 13 M13 3 L3 13" stroke="#00205F" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      {/* Fields */}
      <div className="flex flex-col gap-[12px] px-6 py-5">
        {[
          { label: "Пользователь", value: log.user },
          { label: "Действие",     value: log.action },
          { label: "Время",        value: log.time },
          { label: "IP",           value: log.ip },
          { label: "Устройство",   value: log.device },
        ].map(({ label, value }) => (
          <div key={label} className="flex flex-col gap-[2px]">
            <span className="text-[13px] text-primary/60">{label}</span>
            <span className="text-[16px] text-primary">{value}</span>
          </div>
        ))}
        <div className="flex flex-col gap-[2px]">
          <span className="text-[13px] text-primary/60">Уровень критичности</span>
          <span className="text-[16px] font-semibold" style={{ color: crit.color }}>{crit.label}</span>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex gap-[15px] px-6 pb-5">
        <button
          disabled
          title="В разработке"
          className="flex-1 h-[38px] border-2 border-cta/40 rounded-[20px] text-[14px] font-semibold text-cta/40 cursor-not-allowed"
        >
          Пометить как решённое
        </button>
        <button
          onClick={() => exportLog(log)}
          className="flex-1 h-[38px] border-2 border-cta rounded-[20px] text-[14px] font-semibold text-cta hover:bg-selected transition-colors"
        >
          Экспорт данных
        </button>
      </div>

      {/* JSON log */}
      <div className="flex flex-col gap-[10px] px-6 pb-6">
        <span className="text-[18px] font-bold text-primary">Подробное сообщение лога</span>
        <div className="bg-selected rounded-[5px] p-4">
          <div className="text-[12px] font-semibold text-primary/60 mb-2">JSON / TEXT</div>
          <pre className="text-[13px] text-primary font-mono whitespace-pre-wrap break-all">{log.json}</pre>
        </div>
      </div>
    </div>
  );
}

/* ── Invite dialog ── */
export function InviteUserDialog({ onClose }: { onClose: () => void }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [roleOpen, setRoleOpen] = useState(false);
  const { data: rolesData } = useRoles();
  const invite = useInviteUser();
  // Set when the invitation email could not be delivered
  const [fallback, setFallback] = useState<{ email: string; password: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const roles = rolesData ?? [];
  const selectedRole = roles.find((r) => r.id === role);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email || !name) return;
    invite.mutate(
      { email, display_name: name, roles: role ? [role] : [] },
      {
        onSuccess: (res) => {
          if (res.email_sent || !res.temp_password) onClose();
          else setFallback({ email: res.email, password: res.temp_password });
        },
      },
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,32,95,0.35)" }}
      onClick={onClose}
    >
      <div
        className="bg-white rounded-[20px] w-[480px] flex flex-col"
        style={{ boxShadow: "0 8px 40px rgba(0,32,95,0.18)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-[30px] pt-[28px] pb-[20px]">
          <span className="text-[22px] font-bold text-primary">Пригласить пользователя</span>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-mainbg transition-colors text-primary/40 hover:text-primary text-[22px] leading-none"
          >
            ×
          </button>
        </div>

        {fallback ? (
          <div className="flex flex-col gap-[16px] px-[30px] pb-[28px]">
            <p className="text-[14px] text-[#8A5A00] bg-[#FFF6E0] rounded-[8px] px-3 py-2 leading-snug">
              Пользователь создан, но письмо с приглашением отправить не удалось.
              Передайте данные для входа самостоятельно — при первом входе система попросит сменить пароль.
            </p>
            <div className="flex flex-col gap-[6px] text-[15px] text-primary">
              <span><span className="text-primary/60">Email:</span> {fallback.email}</span>
              <span className="flex items-center gap-[10px]">
                <span className="text-primary/60">Временный пароль:</span>
                <code className="bg-mainbg rounded-[6px] px-2 py-[2px] select-all">{fallback.password}</code>
                <button
                  type="button"
                  onClick={() => {
                    void navigator.clipboard?.writeText(fallback.password).then(() => setCopied(true)).catch(() => {});
                  }}
                  className="text-[13px] text-cta underline"
                >
                  {copied ? "Скопировано" : "Копировать"}
                </button>
              </span>
            </div>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={onClose}
                className="h-[42px] px-[22px] bg-cta rounded-[20px] text-[15px] font-semibold text-white hover:bg-active transition-colors"
              >
                Готово
              </button>
            </div>
          </div>
        ) : (
        <form onSubmit={handleSubmit} className="flex flex-col gap-[18px] px-[30px] pb-[28px]">
          {/* Email */}
          <div className="flex flex-col gap-[6px]">
            <label className="text-[13px] font-medium text-primary/60">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="user@company.ru"
              className="h-[42px] px-[14px] bg-mainbg rounded-[10px] text-[15px] text-primary outline-none border border-transparent focus:border-cta transition-colors placeholder:text-primary/30"
            />
          </div>

          {/* Name */}
          <div className="flex flex-col gap-[6px]">
            <label className="text-[13px] font-medium text-primary/60">Имя и фамилия</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="Иванов Иван"
              className="h-[42px] px-[14px] bg-mainbg rounded-[10px] text-[15px] text-primary outline-none border border-transparent focus:border-cta transition-colors placeholder:text-primary/30"
            />
          </div>

          {/* Role — custom dropdown */}
          <div className="flex flex-col gap-[6px]">
            <label className="text-[13px] font-medium text-primary/60">Роль</label>
            <div className="relative" onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setRoleOpen(false); }}>
              <button
                type="button"
                onClick={() => setRoleOpen((v) => !v)}
                className="w-full h-[42px] px-[14px] bg-mainbg rounded-[10px] text-[15px] text-left flex items-center justify-between border border-transparent focus:border-cta transition-colors outline-none"
              >
                <span className={selectedRole ? "text-primary" : "text-primary/30"}>
                  {selectedRole ? selectedRole.display_name : "— без роли —"}
                </span>
                <svg
                  viewBox="0 0 16 16"
                  className={cn("w-4 h-4 text-primary/40 transition-transform shrink-0", roleOpen && "rotate-180")}
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                >
                  <path d="M3 6l5 5 5-5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>

              {roleOpen && (
                <div
                  className="absolute left-0 right-0 top-[46px] z-50 bg-white rounded-[12px] py-[6px] flex flex-col overflow-y-auto"
                  style={{ boxShadow: "0 4px 24px rgba(0,32,95,0.14)", maxHeight: 280 }}
                >
                  <button
                    type="button"
                    onClick={() => { setRole(""); setRoleOpen(false); }}
                    className={cn(
                      "flex items-center h-[38px] px-[14px] text-[15px] text-left transition-colors",
                      !role ? "bg-selected text-cta font-medium" : "text-primary/40 hover:bg-mainbg"
                    )}
                  >
                    — без роли —
                  </button>
                  {roles.map((r) => (
                    <button
                      key={r.id}
                      type="button"
                      onClick={() => { setRole(r.id); setRoleOpen(false); }}
                      className={cn(
                        "flex items-center h-[38px] px-[14px] text-[15px] text-left transition-colors",
                        role === r.id ? "bg-selected text-cta font-medium" : "text-primary hover:bg-mainbg"
                      )}
                    >
                      {r.display_name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {invite.isError && (
            <p className="text-[13px] text-[#C22A2A] bg-[#FFF0F0] rounded-[8px] px-3 py-2">
              Ошибка приглашения. Попробуйте снова.
            </p>
          )}

          {/* Actions */}
          <div className="flex gap-[10px] justify-end pt-[4px]">
            <button
              type="button"
              onClick={onClose}
              className="h-[42px] px-[22px] border-2 border-primary/20 rounded-[20px] text-[15px] text-primary hover:bg-mainbg transition-colors"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={invite.isPending}
              className="h-[42px] px-[22px] bg-cta rounded-[20px] text-[15px] font-semibold text-white hover:bg-active transition-colors disabled:opacity-50"
            >
              {invite.isPending ? "Отправка…" : "Пригласить"}
            </button>
          </div>
        </form>
        )}
      </div>
    </div>
  );
}

/* ── Users ── */
function AdminUsers() {
  const [search, setSearch] = useState("");
  const [inviteOpen, setInviteOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: string; name: string } | null>(null);
  const [passwordUser, setPasswordUser] = useState<{ id: string; name: string } | null>(null);
  const { data, isLoading } = useUsers(search ? { search } : undefined);
  const deactivate = useDeactivateUser();
  const update = useUpdateUser();
  const hardDelete = useHardDeleteUser();

  const users = data?.items ?? [];

  function fmtDate(iso: string) {
    return new Date(iso).toLocaleDateString("ru", { day: "2-digit", month: "2-digit", year: "numeric" });
  }

  function userStatus(u: typeof users[0]) {
    if (u.is_blocked) return { label: "Заблокирован", color: "text-[#C22A2A]" };
    if (!u.is_active) return { label: "Неактивен", color: "text-[#FFA600]" };
    return { label: "Активен", color: "text-[#20BE4F]" };
  }

  return (
    <div className="flex flex-col gap-[40px]">
      {inviteOpen && <InviteUserDialog onClose={() => setInviteOpen(false)} />}
      {passwordUser && <SetPasswordDialog userId={passwordUser.id} userName={passwordUser.name} onClose={() => setPasswordUser(null)} />}

      {deleteConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: "rgba(0,32,95,0.35)" }}
          onClick={() => setDeleteConfirm(null)}
        >
          <div
            className="bg-white rounded-[20px] w-[420px] p-[30px] flex flex-col gap-[20px]"
            style={{ boxShadow: "0 8px 40px rgba(0,32,95,0.18)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex flex-col gap-[8px]">
              <span className="text-[20px] font-bold text-primary">Удалить пользователя?</span>
              <span className="text-[15px] text-primary/60">
                Это действие необратимо. Учётная запись <strong className="text-primary">{deleteConfirm.name}</strong> и все связанные данные будут удалены навсегда.
              </span>
            </div>
            <div className="flex gap-[10px] justify-end">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="h-[42px] px-[22px] border-2 border-primary/20 rounded-[20px] text-[15px] text-primary hover:bg-mainbg transition-colors"
              >
                Отмена
              </button>
              <button
                onClick={() => hardDelete.mutate(deleteConfirm.id, { onSuccess: () => setDeleteConfirm(null) })}
                disabled={hardDelete.isPending}
                className="h-[42px] px-[22px] bg-[#C22A2A] rounded-[20px] text-[15px] font-semibold text-white hover:bg-[#A01E1E] transition-colors disabled:opacity-50"
              >
                {hardDelete.isPending ? "Удаление…" : "Удалить навсегда"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <h1 className="text-[40px] font-bold text-primary leading-[150%]">Пользователи</h1>
        <button
          onClick={() => setInviteOpen(true)}
          className="flex items-center gap-2 h-[42px] px-6 bg-cta rounded-[20px] text-[16px] font-semibold text-white hover:bg-cta/90 transition-colors"
        >
          <svg viewBox="0 0 20 20" fill="none" className="w-5 h-5">
            <line x1="10" y1="3" x2="10" y2="17" stroke="white" strokeWidth="2" strokeLinecap="round" />
            <line x1="3" y1="10" x2="17" y2="10" stroke="white" strokeWidth="2" strokeLinecap="round" />
          </svg>
          Пригласить
        </button>
      </div>

      {/* Search */}
      <div className="flex items-center gap-[15px]">
        <div className="flex items-center gap-[10px] w-[400px] h-[42px] px-5 bg-white rounded-[30px] shadow-sm">
          <svg viewBox="0 0 20 20" fill="none" className="w-5 h-5 shrink-0">
            <circle cx="9" cy="9" r="6" stroke="#00205F" strokeWidth="1.8" />
            <line x1="13.5" y1="13.5" x2="18" y2="18" stroke="#00205F" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по имени или email…"
            className="flex-1 bg-transparent text-[16px] text-primary outline-none"
          />
        </div>
      </div>

      <div className="bg-white rounded-[5px] shadow-[0_4px_4px_rgba(0,0,0,0.25)] overflow-hidden">
        <table className="w-full">
          <thead className="bg-mainbg">
            <tr>
              {["Имя", "Email", "Роли", "Статус", "Последний вход", "Создан", ""].map((h, i) => (
                <th key={i} className="text-left px-6 py-3 text-info font-semibold text-primary">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={7} className="px-6 py-4 text-center text-primary/50 text-[16px]">Загрузка…</td></tr>
            )}
            {!isLoading && users.length === 0 && (
              <tr><td colSpan={7} className="px-6 py-4 text-center text-primary/50 text-[16px]">Пользователи не найдены</td></tr>
            )}
            {users.map((u) => {
              const st = userStatus(u);
              return (
                <tr key={u.id} className="border-t border-mainbg hover:bg-mainbg/40">
                  <td className="px-6 py-3 text-meta font-semibold text-primary">{u.display_name}</td>
                  <td className="px-6 py-3 text-meta text-primary">{u.email}</td>
                  <td className="px-6 py-3 text-meta text-primary">
                    {u.roles.length > 0 ? u.roles.map((r) => r.display_name).join(", ") : "—"}
                  </td>
                  <td className={cn("px-6 py-3 text-meta font-semibold", st.color)}>{st.label}</td>
                  <td className="px-6 py-3 text-meta text-primary">
                    {u.last_login_at ? fmtDate(u.last_login_at) : "—"}
                  </td>
                  <td className="px-6 py-3 text-meta text-primary">{fmtDate(u.created_at)}</td>
                  <td className="px-6 py-3">
                    <UserActionsMenu
                      user={u}
                      onDeactivate={() => deactivate.mutate(u.id)}
                      onActivate={() => update.mutate({ userId: u.id, body: { is_active: true } })}
                      onBlock={() => update.mutate({ userId: u.id, body: { is_blocked: true } })}
                      onUnblock={() => update.mutate({ userId: u.id, body: { is_blocked: false } })}
                      onDelete={() => setDeleteConfirm({ id: u.id, name: u.display_name })}
                      onSetPassword={() => setPasswordUser({ id: u.id, name: u.display_name })}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── User actions dropdown ── */
function UserActionsMenu({
  user,
  onDeactivate,
  onActivate,
  onBlock,
  onUnblock,
  onDelete,
  onSetPassword,
}: {
  user: { is_active: boolean; is_blocked: boolean; is_superuser: boolean };
  onDeactivate: () => void;
  onActivate: () => void;
  onBlock: () => void;
  onUnblock: () => void;
  onDelete: () => void;
  onSetPassword: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  function act(fn: () => void) {
    fn();
    setOpen(false);
  }

  return (
    <div ref={ref} className="relative flex justify-end">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-7 h-7 flex items-center justify-center rounded hover:bg-mainbg transition-colors text-primary/40 hover:text-primary"
        title="Действия"
      >
        <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4">
          <circle cx="8" cy="3" r="1.3" />
          <circle cx="8" cy="8" r="1.3" />
          <circle cx="8" cy="13" r="1.3" />
        </svg>
      </button>
      {open && (
        <div
          className="absolute right-0 top-8 z-50 bg-white rounded-[12px] py-[6px] min-w-[190px]"
          style={{ boxShadow: "0 4px 24px rgba(0,32,95,0.14)" }}
        >
          {user.is_active ? (
            <button
              onClick={() => act(onDeactivate)}
              className="w-full text-left flex items-center gap-[10px] px-[14px] h-[36px] text-[14px] text-primary hover:bg-mainbg transition-colors"
            >
              <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-[#FFA600]" stroke="currentColor" strokeWidth="1.5">
                <circle cx="8" cy="8" r="6.5" />
                <line x1="5" y1="8" x2="11" y2="8" strokeLinecap="round" />
              </svg>
              Деактивировать
            </button>
          ) : (
            <button
              onClick={() => act(onActivate)}
              className="w-full text-left flex items-center gap-[10px] px-[14px] h-[36px] text-[14px] text-primary hover:bg-mainbg transition-colors"
            >
              <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-[#20BE4F]" stroke="currentColor" strokeWidth="1.5">
                <circle cx="8" cy="8" r="6.5" />
                <path d="M5.5 8l2 2 3-3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Активировать
            </button>
          )}

          {user.is_blocked ? (
            <button
              onClick={() => act(onUnblock)}
              className="w-full text-left flex items-center gap-[10px] px-[14px] h-[36px] text-[14px] text-primary hover:bg-mainbg transition-colors"
            >
              <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-[#20BE4F]" stroke="currentColor" strokeWidth="1.5">
                <rect x="3" y="7" width="10" height="7" rx="1.5" />
                <path d="M5.5 7V5a2.5 2.5 0 015 0v2" strokeLinecap="round" />
              </svg>
              Разблокировать
            </button>
          ) : (
            <button
              onClick={() => act(onBlock)}
              className="w-full text-left flex items-center gap-[10px] px-[14px] h-[36px] text-[14px] text-primary hover:bg-mainbg transition-colors"
            >
              <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-[#C22A2A]" stroke="currentColor" strokeWidth="1.5">
                <rect x="3" y="7" width="10" height="7" rx="1.5" />
                <path d="M5.5 7V5a2.5 2.5 0 015 0v2" strokeLinecap="round" />
                <line x1="5" y1="10.5" x2="11" y2="10.5" strokeLinecap="round" />
              </svg>
              Заблокировать
            </button>
          )}

          <div className="border-t border-mainbg my-[4px]" />
          <button
            onClick={() => act(onSetPassword)}
            className="w-full text-left flex items-center gap-[10px] px-[14px] h-[36px] text-[14px] text-primary hover:bg-mainbg transition-colors"
          >
            <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-primary/60" stroke="currentColor" strokeWidth="1.5">
              <rect x="3" y="7" width="10" height="7" rx="1.5" />
              <path d="M5.5 7V5a2.5 2.5 0 015 0v2" strokeLinecap="round" />
              <line x1="8" y1="10" x2="8" y2="11.5" strokeLinecap="round" strokeWidth="2" />
            </svg>
            Установить пароль
          </button>

          {!user.is_superuser && (
            <>
              <div className="border-t border-mainbg my-[4px]" />
              <button
                onClick={() => act(onDelete)}
                className="w-full text-left flex items-center gap-[10px] px-[14px] h-[36px] text-[14px] text-[#C22A2A] hover:bg-[#FFF0F0] transition-colors"
              >
                <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0" stroke="currentColor" strokeWidth="1.5">
                  <path d="M3 4h10M6 4V2.5h4V4M5 4v8.5a.5.5 0 00.5.5h5a.5.5 0 00.5-.5V4" strokeLinecap="round" />
                  <line x1="6.5" y1="7" x2="6.5" y2="10.5" strokeLinecap="round" />
                  <line x1="9.5" y1="7" x2="9.5" y2="10.5" strokeLinecap="round" />
                </svg>
                Удалить навсегда
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Set password dialog ── */
function SetPasswordDialog({ userId, userName, onClose }: { userId: string; userName: string; onClose: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const setPass = useSetUserPassword();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < 8) { setError("Минимум 8 символов"); return; }
    setPass.mutate(
      { userId, newPassword: password },
      {
        onSuccess: onClose,
        onError: (err: unknown) => {
          const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
          setError(detail ?? "Не удалось установить пароль");
        },
      },
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,32,95,0.35)" }}
      onClick={onClose}
    >
      <div
        className="bg-white rounded-[20px] w-[420px] flex flex-col"
        style={{ boxShadow: "0 8px 40px rgba(0,32,95,0.18)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-[30px] pt-[28px] pb-[20px]">
          <span className="text-[20px] font-bold text-primary">Установить пароль</span>
          <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-mainbg transition-colors text-primary/40 hover:text-primary text-[22px] leading-none">×</button>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col gap-[16px] px-[30px] pb-[28px]">
          <p className="text-[14px] text-primary/60">Новый пароль для <strong className="text-primary">{userName}</strong></p>
          <PasswordInput
            value={password}
            onChange={(e) => { setPassword(e.target.value); setError(""); }}
            placeholder="Введите новый пароль"
            autoFocus
            className="h-[42px] px-[14px] bg-mainbg rounded-[10px] text-[15px] text-primary outline-none border border-transparent focus:border-cta transition-colors placeholder:text-primary/30"
          />
          {error && <p className="text-[13px] text-red-400 -mt-2">{error}</p>}
          <div className="flex gap-[10px] justify-end pt-[4px]">
            <button type="button" onClick={onClose} className="h-[42px] px-[22px] border-2 border-primary/20 rounded-[20px] text-[15px] text-primary hover:bg-mainbg transition-colors">
              Отмена
            </button>
            <button type="submit" disabled={setPass.isPending} className="h-[42px] px-[22px] bg-cta rounded-[20px] text-[15px] font-semibold text-white hover:bg-active transition-colors disabled:opacity-50">
              {setPass.isPending ? "Сохранение…" : "Сохранить"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ── Groups ── */
function AdminGroups() {
  const { data: groups = [], isLoading } = useGroups();
  const { data: allUsers } = useUsers();
  const { data: allRoles } = useRoles();
  const createGroup = useCreateGroup();
  const updateGroup = useUpdateGroup();
  const deleteGroup = useDeleteGroup();
  const addMember = useAddGroupMember();
  const removeMember = useRemoveGroupMember();
  const applyRoles = useApplyGroupRoles();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: detail } = useGroup(selectedId);
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: string; name: string } | null>(null);
  const [applyResult, setApplyResult] = useState<number | null>(null);

  const users = allUsers?.items ?? [];
  const roles = allRoles ?? [];

  const memberIds = new Set((detail?.members ?? []).map((m) => m.id));
  const nonMembers = users.filter((u) => !memberIds.has(u.id));

  return (
    <div className="flex flex-col gap-[40px]">
      {/* Create modal */}
      {createOpen && (
        <GroupFormModal
          title="Создать группу"
          roles={roles}
          onClose={() => setCreateOpen(false)}
          onSubmit={(data) =>
            createGroup.mutate(data, {
              onSuccess: (g) => { setCreateOpen(false); setSelectedId(g.id); },
            })
          }
          pending={createGroup.isPending}
        />
      )}

      {/* Edit modal */}
      {editOpen && detail && (
        <GroupFormModal
          title="Редактировать группу"
          roles={roles}
          initial={{ name: detail.name, description: detail.description ?? "", role_ids: detail.roles.map((r) => r.id) }}
          onClose={() => setEditOpen(false)}
          onSubmit={(data) =>
            updateGroup.mutate({ groupId: detail.id, body: data }, { onSuccess: () => setEditOpen(false) })
          }
          pending={updateGroup.isPending}
        />
      )}

      {/* Delete confirm */}
      {deleteConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: "rgba(0,32,95,0.35)" }}
          onClick={() => setDeleteConfirm(null)}
        >
          <div
            className="bg-white rounded-[20px] w-[400px] p-[30px] flex flex-col gap-[20px]"
            style={{ boxShadow: "0 8px 40px rgba(0,32,95,0.18)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <span className="text-[20px] font-bold text-primary">Удалить группу?</span>
            <span className="text-[15px] text-primary/60">
              Группа <strong className="text-primary">{deleteConfirm.name}</strong> будет удалена. Участники и их роли не изменятся.
            </span>
            <div className="flex gap-[10px] justify-end">
              <button onClick={() => setDeleteConfirm(null)}
                className="h-[42px] px-[22px] border-2 border-primary/20 rounded-[20px] text-[15px] text-primary hover:bg-mainbg transition-colors">
                Отмена
              </button>
              <button
                onClick={() => deleteGroup.mutate(deleteConfirm.id, {
                  onSuccess: () => { setDeleteConfirm(null); if (selectedId === deleteConfirm.id) setSelectedId(null); }
                })}
                disabled={deleteGroup.isPending}
                className="h-[42px] px-[22px] bg-[#C22A2A] rounded-[20px] text-[15px] font-semibold text-white hover:bg-[#A01E1E] transition-colors disabled:opacity-50"
              >
                {deleteGroup.isPending ? "Удаление…" : "Удалить"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Apply roles result toast */}
      {applyResult !== null && (
        <div className="fixed bottom-6 right-6 z-50 bg-white rounded-[12px] px-5 py-3 flex items-center gap-3"
          style={{ boxShadow: "0 4px 24px rgba(0,32,95,0.18)" }}>
          <span className="text-[#20BE4F] text-[20px]">✓</span>
          <span className="text-[15px] text-primary">
            {applyResult === 0 ? "Все роли уже назначены" : `Добавлено ${applyResult} назначений ролей`}
          </span>
          <button onClick={() => setApplyResult(null)} className="text-primary/40 hover:text-primary ml-2">×</button>
        </div>
      )}

      <div className="flex items-center justify-between">
        <h1 className="text-[40px] font-bold text-primary leading-[150%]">Группы</h1>
        <button
          onClick={() => setCreateOpen(true)}
          className="flex items-center gap-2 h-[42px] px-6 bg-cta rounded-[20px] text-[16px] font-semibold text-white hover:bg-cta/90 transition-colors"
        >
          <svg viewBox="0 0 20 20" fill="none" className="w-5 h-5">
            <line x1="10" y1="3" x2="10" y2="17" stroke="white" strokeWidth="2" strokeLinecap="round" />
            <line x1="3" y1="10" x2="17" y2="10" stroke="white" strokeWidth="2" strokeLinecap="round" />
          </svg>
          Создать группу
        </button>
      </div>

      <div className="flex gap-[24px]">
        {/* Group list */}
        <div className="flex flex-col gap-[8px] w-[320px] shrink-0">
          {isLoading && <span className="text-[15px] text-primary/50">Загрузка…</span>}
          {!isLoading && groups.length === 0 && (
            <div className="bg-white rounded-[12px] p-6 text-center text-[15px] text-primary/40"
              style={{ boxShadow: "0 2px 8px rgba(0,32,95,0.08)" }}>
              Групп пока нет
            </div>
          )}
          {groups.map((g) => (
            <button
              key={g.id}
              onClick={() => setSelectedId(g.id === selectedId ? null : g.id)}
              className={cn(
                "w-full text-left rounded-[12px] px-5 py-4 transition-colors",
                selectedId === g.id
                  ? "bg-selected border-2 border-cta"
                  : "bg-white hover:bg-mainbg border-2 border-transparent",
              )}
              style={{ boxShadow: "0 2px 8px rgba(0,32,95,0.06)" }}
            >
              <div className="flex items-center justify-between gap-2">
                <span className={cn("text-[16px] font-semibold", selectedId === g.id ? "text-cta" : "text-primary")}>
                  {g.name}
                </span>
                <span className="text-[13px] text-primary/40 shrink-0">{g.member_count} чел.</span>
              </div>
              {g.description && (
                <p className="text-[13px] text-primary/50 mt-1 truncate">{g.description}</p>
              )}
              {g.roles.length > 0 && (
                <div className="flex flex-wrap gap-[4px] mt-2">
                  {g.roles.map((r) => (
                    <span key={r.id} className="text-[11px] bg-cta/10 text-cta rounded-full px-2 py-0.5">{r.display_name}</span>
                  ))}
                </div>
              )}
            </button>
          ))}
        </div>

        {/* Group detail */}
        {selectedId && detail ? (
          <div className="flex-1 flex flex-col gap-[20px]">
            {/* Header */}
            <div className="bg-white rounded-[16px] p-6 flex items-start justify-between"
              style={{ boxShadow: "0 2px 12px rgba(0,32,95,0.08)" }}>
              <div className="flex flex-col gap-[4px]">
                <h2 className="text-[24px] font-bold text-primary">{detail.name}</h2>
                {detail.description && <p className="text-[15px] text-primary/60">{detail.description}</p>}
                <div className="flex gap-2 mt-2 flex-wrap">
                  {detail.roles.length === 0
                    ? <span className="text-[13px] text-primary/40">Без ролей</span>
                    : detail.roles.map((r) => (
                        <span key={r.id} className="text-[12px] bg-cta/10 text-cta rounded-full px-3 py-0.5">{r.display_name}</span>
                      ))
                  }
                </div>
              </div>
              <div className="flex gap-[8px]">
                {detail.roles.length > 0 && (
                  <button
                    onClick={() => applyRoles.mutate(detail.id, {
                      onSuccess: (r) => setApplyResult(r.grants_added),
                    })}
                    disabled={applyRoles.isPending}
                    title="Назначить роли группы всем участникам"
                    className="h-[36px] px-4 bg-cta/10 text-cta rounded-[20px] text-[13px] font-medium hover:bg-cta/20 transition-colors disabled:opacity-50"
                  >
                    {applyRoles.isPending ? "Применяю…" : "Применить роли"}
                  </button>
                )}
                <button onClick={() => setEditOpen(true)}
                  className="h-[36px] px-4 border border-primary/20 rounded-[20px] text-[13px] text-primary hover:bg-mainbg transition-colors">
                  Редактировать
                </button>
                <button onClick={() => setDeleteConfirm({ id: detail.id, name: detail.name })}
                  className="h-[36px] px-4 border border-[#C22A2A]/30 rounded-[20px] text-[13px] text-[#C22A2A] hover:bg-[#FFF0F0] transition-colors">
                  Удалить
                </button>
              </div>
            </div>

            {/* Members */}
            <div className="bg-white rounded-[16px] overflow-hidden"
              style={{ boxShadow: "0 2px 12px rgba(0,32,95,0.08)" }}>
              <div className="flex items-center justify-between px-6 py-4 border-b border-mainbg">
                <span className="text-[18px] font-bold text-primary">Участники ({detail.member_count})</span>
                {/* Add member dropdown */}
                {nonMembers.length > 0 && (
                  <AddMemberDropdown
                    users={nonMembers}
                    onAdd={(userId) => addMember.mutate({ groupId: detail.id, userId })}
                  />
                )}
              </div>
              {detail.members.length === 0 ? (
                <div className="px-6 py-8 text-center text-[15px] text-primary/40">Нет участников</div>
              ) : (
                <table className="w-full">
                  <thead className="bg-mainbg">
                    <tr>
                      {["Имя", "Email", "Статус", ""].map((h, i) => (
                        <th key={i} className="text-left px-6 py-3 text-[13px] font-semibold text-primary">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {detail.members.map((m) => (
                      <tr key={m.id} className="border-t border-mainbg hover:bg-mainbg/40">
                        <td className="px-6 py-3 text-[14px] font-semibold text-primary">{m.display_name}</td>
                        <td className="px-6 py-3 text-[14px] text-primary">{m.email}</td>
                        <td className={cn("px-6 py-3 text-[14px] font-semibold",
                          m.is_active ? "text-[#20BE4F]" : "text-[#FFA600]"
                        )}>
                          {m.is_active ? "Активен" : "Неактивен"}
                        </td>
                        <td className="px-6 py-3 text-right">
                          <button
                            onClick={() => removeMember.mutate({ groupId: detail.id, userId: m.id })}
                            className="text-[13px] text-primary/40 hover:text-[#C22A2A] transition-colors"
                          >
                            Исключить
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        ) : selectedId ? (
          <div className="flex-1 flex items-center justify-center text-primary/40 text-[15px]">Загрузка…</div>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center flex flex-col items-center gap-3">
              <svg viewBox="0 0 48 48" fill="none" className="w-12 h-12 text-primary/20">
                <circle cx="16" cy="16" r="7" stroke="currentColor" strokeWidth="2.5" />
                <circle cx="32" cy="16" r="7" stroke="currentColor" strokeWidth="2.5" />
                <path d="M4 40c0-7 5-12 12-12h4" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                <path d="M24 40c0-7 5-12 12-12" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
              </svg>
              <span className="text-[15px] text-primary/40">Выберите группу для просмотра</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Add member dropdown ── */
function AddMemberDropdown({
  users,
  onAdd,
}: {
  users: { id: string; display_name: string; email: string }[];
  onAdd: (userId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const filtered = users.filter(
    (u) =>
      u.display_name.toLowerCase().includes(search.toLowerCase()) ||
      u.email.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 h-[34px] px-4 bg-cta rounded-[20px] text-[13px] font-semibold text-white hover:bg-cta/90 transition-colors"
      >
        <svg viewBox="0 0 14 14" fill="none" className="w-3.5 h-3.5">
          <line x1="7" y1="1" x2="7" y2="13" stroke="white" strokeWidth="1.8" strokeLinecap="round" />
          <line x1="1" y1="7" x2="13" y2="7" stroke="white" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
        Добавить участника
      </button>
      {open && (
        <div
          className="absolute right-0 top-10 z-50 bg-white rounded-[12px] w-[280px]"
          style={{ boxShadow: "0 4px 24px rgba(0,32,95,0.14)" }}
        >
          <div className="p-2 border-b border-mainbg">
            <input
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск…"
              className="w-full h-[32px] px-3 bg-mainbg rounded-[8px] text-[13px] text-primary outline-none"
            />
          </div>
          <div className="max-h-[220px] overflow-y-auto py-1">
            {filtered.length === 0 && (
              <div className="px-4 py-3 text-[13px] text-primary/40">Не найдено</div>
            )}
            {filtered.map((u) => (
              <button
                key={u.id}
                onClick={() => { onAdd(u.id); setOpen(false); setSearch(""); }}
                className="w-full text-left flex flex-col px-4 py-2 hover:bg-mainbg transition-colors"
              >
                <span className="text-[14px] text-primary font-medium">{u.display_name}</span>
                <span className="text-[12px] text-primary/50">{u.email}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Group form modal ── */
function GroupFormModal({
  title,
  roles,
  initial,
  onClose,
  onSubmit,
  pending,
}: {
  title: string;
  roles: { id: string; display_name: string }[];
  initial?: { name: string; description: string; role_ids: string[] };
  onClose: () => void;
  onSubmit: (data: { name: string; description?: string; role_ids: string[] }) => void;
  pending: boolean;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [selectedRoles, setSelectedRoles] = useState<Set<string>>(new Set(initial?.role_ids ?? []));

  function toggleRole(id: string) {
    setSelectedRoles((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    onSubmit({ name: name.trim(), description: description.trim() || undefined, role_ids: [...selectedRoles] });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,32,95,0.35)" }}
      onClick={onClose}
    >
      <div
        className="bg-white rounded-[20px] w-[520px] flex flex-col"
        style={{ boxShadow: "0 8px 40px rgba(0,32,95,0.18)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-[30px] pt-[28px] pb-[20px]">
          <span className="text-[22px] font-bold text-primary">{title}</span>
          <button onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-mainbg transition-colors text-primary/40 hover:text-primary text-[22px] leading-none">
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-[18px] px-[30px] pb-[28px]">
          <div className="flex flex-col gap-[6px]">
            <label className="text-[13px] font-medium text-primary/60">Название группы</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="Финансовый отдел"
              className="h-[42px] px-[14px] bg-mainbg rounded-[10px] text-[15px] text-primary outline-none border border-transparent focus:border-cta transition-colors placeholder:text-primary/30"
            />
          </div>

          <div className="flex flex-col gap-[6px]">
            <label className="text-[13px] font-medium text-primary/60">Описание <span className="text-primary/30">(необязательно)</span></label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="Краткое описание группы"
              className="px-[14px] py-[10px] bg-mainbg rounded-[10px] text-[15px] text-primary outline-none border border-transparent focus:border-cta transition-colors placeholder:text-primary/30 resize-none"
            />
          </div>

          <div className="flex flex-col gap-[8px]">
            <label className="text-[13px] font-medium text-primary/60">Роли группы <span className="text-primary/30">(назначаются участникам)</span></label>
            <div className="flex flex-col gap-[4px] max-h-[200px] overflow-y-auto bg-mainbg rounded-[10px] p-2">
              {roles.map((r) => (
                <label key={r.id} className="flex items-center gap-[10px] px-3 py-2 rounded-[8px] hover:bg-white cursor-pointer transition-colors">
                  <input
                    type="checkbox"
                    checked={selectedRoles.has(r.id)}
                    onChange={() => toggleRole(r.id)}
                    className="w-4 h-4 accent-[#00205F] cursor-pointer"
                  />
                  <span className="text-[14px] text-primary">{r.display_name}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="flex gap-[10px] justify-end pt-[4px]">
            <button type="button" onClick={onClose}
              className="h-[42px] px-[22px] border-2 border-primary/20 rounded-[20px] text-[15px] text-primary hover:bg-mainbg transition-colors">
              Отмена
            </button>
            <button type="submit" disabled={pending}
              className="h-[42px] px-[22px] bg-cta rounded-[20px] text-[15px] font-semibold text-white hover:bg-active transition-colors disabled:opacity-50">
              {pending ? "Сохранение…" : (initial ? "Сохранить" : "Создать")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ── Apps ── */
function AdminApps() {
  const { data, isLoading } = useApps();
  const apps = data?.items ?? [];

  function fmtRelative(iso: string) {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60_000);
    if (mins < 60) return `${mins} мин. назад`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs} ч. назад`;
    const days = Math.floor(hrs / 24);
    return `${days} дн. назад`;
  }

  function appStatus(app: { is_published: boolean; is_archived: boolean }) {
    if (app.is_archived) return { label: "В архиве", cls: "text-[#8898AA]" };
    if (app.is_published) return { label: "Активен",      cls: "text-[#20BE4F]" };
    return { label: "В разработке", cls: "text-[#FFA600]" };
  }

  return (
    <div className="flex flex-col gap-[40px]">
      <div className="flex items-center justify-between">
        <h1 className="text-[40px] font-bold text-primary leading-[150%]">Приложения</h1>
        <span className="text-[18px] text-primary/60">{data?.total != null ? `Всего: ${data.total}` : ""}</span>
      </div>
      <div className="bg-white rounded-[5px] shadow-[0_4px_4px_rgba(0,0,0,0.25)] overflow-hidden">
        <table className="w-full">
          <thead className="bg-mainbg">
            <tr>
              {["Название", "Описание", "Статус", "Версия", "Изменён"].map((h) => (
                <th key={h} className="text-left px-6 py-3 text-info font-semibold text-primary">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={5} className="px-6 py-4 text-center text-primary/50 text-[16px]">Загрузка…</td></tr>
            )}
            {!isLoading && apps.length === 0 && (
              <tr><td colSpan={5} className="px-6 py-4 text-center text-primary/50 text-[16px]">Приложений нет</td></tr>
            )}
            {apps.map((a) => {
              const st = appStatus(a);
              return (
                <tr key={a.id} className="border-t border-mainbg hover:bg-mainbg/40">
                  <td className="px-6 py-3 text-meta font-semibold text-primary">{a.name}</td>
                  <td className="px-6 py-3 text-meta text-primary max-w-[260px] truncate">{a.description ?? "—"}</td>
                  <td className={cn("px-6 py-3 text-meta font-semibold", st.cls)}>{st.label}</td>
                  <td className="px-6 py-3 text-meta text-primary">v{a.version}</td>
                  <td className="px-6 py-3 text-meta text-primary">{fmtRelative(a.updated_at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Databases ── */
export interface DbRow {
  name: string;
  app: string;
  status: string;
  statusCls: string;
  version: string;
}

/** Map backend apps into the per-app database rows shown in the admin table. */
export function appsToDbRows(
  apps: { slug: string; name: string; is_published: boolean; is_archived: boolean; version: number }[],
): DbRow[] {
  return apps.map((a) => {
    const status = a.is_archived ? "В архиве" : a.is_published ? "Активна" : "В разработке";
    const statusCls = a.is_archived ? "text-[#8898AA]" : a.is_published ? "text-[#20BE4F]" : "text-[#FFA600]";
    return { name: `${a.slug}_db`, app: a.name, status, statusCls, version: `v${a.version}` };
  });
}

function AdminDatabases() {
  const { data, isLoading } = useApps();
  const rows = appsToDbRows(data?.items ?? []);

  return (
    <div className="flex flex-col gap-[70px]">
      <h1 className="text-[40px] font-bold text-primary leading-[150%]">Базы данных</h1>
      <div className="bg-white rounded-[5px] shadow-[0_4px_4px_rgba(0,0,0,0.25)] overflow-hidden">
        <table className="w-full">
          <thead className="bg-mainbg">
            <tr>
              {["Имя базы", "Приложение", "Версия", "Статус"].map((h) => (
                <th key={h} className="text-left px-6 py-3 text-info font-semibold text-primary">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={4} className="px-6 py-4 text-center text-primary/50 text-[16px]">Загрузка…</td></tr>
            )}
            {!isLoading && rows.length === 0 && (
              <tr><td colSpan={4} className="px-6 py-4 text-center text-primary/50 text-[16px]">Баз данных нет</td></tr>
            )}
            {rows.map((db, i) => (
              <tr key={i} className="border-t border-mainbg hover:bg-mainbg/40">
                <td className="px-6 py-3 text-meta font-semibold text-primary font-mono">{db.name}</td>
                <td className="px-6 py-3 text-meta text-primary">{db.app}</td>
                <td className="px-6 py-3 text-meta text-primary">{db.version}</td>
                <td className={cn("px-6 py-3 text-meta font-semibold", db.statusCls)}>{db.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Organisations ── */
const PLAN_LABELS: Record<string, string> = {
  trial:    "Trial",
  pro:      "Про",
  business: "Бизнес",
};

function CreateOrgDialog({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState({
    display_name: "",
    slug: "",
    plan: "trial",
    admin_email: "",
    admin_display_name: "",
    admin_password: "",
  });
  const create = useCreateOrg();

  function set(k: string, v: string) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    create.mutate(form, { onSuccess: onClose });
  }

  const fields: { key: keyof typeof form; label: string; type?: string; placeholder: string }[] = [
    { key: "display_name",      label: "Название организации",  placeholder: "ООО Ромашка" },
    { key: "slug",              label: "Slug (ID)",             placeholder: "romashka" },
    { key: "plan",              label: "Тариф",                 placeholder: "trial" },
    { key: "admin_email",       label: "Email администратора",  type: "email", placeholder: "admin@company.ru" },
    { key: "admin_display_name",label: "Имя администратора",    placeholder: "Иван Петров" },
    { key: "admin_password",    label: "Пароль администратора", type: "password", placeholder: "••••••••••" },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.45)" }}
      onClick={onClose}
    >
      <div
        className="bg-white rounded-[20px] shadow-[0_8px_32px_rgba(0,32,95,0.15)] w-[540px] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-8 py-6 border-b border-[#cbe3ff]">
          <span className="text-[24px] font-bold text-primary">Создать организацию</span>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-mainbg"
          >
            <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4">
              <path d="M3 3L13 13M13 3L3 13" stroke="#00205F" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </button>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5 px-8 py-6">
          {fields.map(({ key, label, type = "text", placeholder }) => (
            <div key={key} className="flex flex-col gap-1">
              <label className="text-[14px] font-semibold text-primary">{label}</label>
              <input
                type={type}
                value={form[key]}
                onChange={(e) => set(key, e.target.value)}
                required
                placeholder={placeholder}
                className="h-[44px] px-4 bg-mainbg rounded-[8px] text-[15px] text-primary outline-none border border-[#cbe3ff] focus:border-cta"
              />
            </div>
          ))}
          {create.isError && (
            <p className="text-[14px] text-[#C22A2A]">Ошибка создания. Проверьте данные.</p>
          )}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 h-[44px] border-2 border-[#cbe3ff] rounded-[22px] text-[16px] font-semibold text-primary hover:bg-mainbg transition-colors"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={create.isPending}
              className="flex-1 h-[44px] bg-cta rounded-[22px] text-[16px] font-semibold text-white hover:bg-cta/90 disabled:opacity-50 transition-colors"
            >
              {create.isPending ? "Создание…" : "Создать"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function AdminOrgs() {
  const [createOpen, setCreateOpen] = useState(false);
  const { data: orgs, isLoading } = useOrgs();
  const updateOrg = useUpdateOrg();

  function fmtDate(iso: string) {
    return new Date(iso).toLocaleDateString("ru", { day: "2-digit", month: "2-digit", year: "2-digit" });
  }

  return (
    <div className="flex flex-col gap-[40px]">
      {createOpen && <CreateOrgDialog onClose={() => setCreateOpen(false)} />}

      <div className="flex items-start justify-between">
        <div className="flex flex-col gap-[10px]">
          <h1 className="text-[40px] font-bold text-primary leading-[150%]">Организации</h1>
          <p className="text-[18px] font-medium text-primary/60 leading-[150%]">
            Управление компаниями на платформе
          </p>
        </div>
        <button
          onClick={() => setCreateOpen(true)}
          className="flex items-center gap-2 h-[44px] px-6 bg-cta rounded-[22px] text-[15px] font-semibold text-white hover:bg-cta/90 transition-colors shrink-0"
        >
          <svg viewBox="0 0 20 20" fill="none" className="w-4 h-4">
            <line x1="10" y1="3" x2="10" y2="17" stroke="white" strokeWidth="2" strokeLinecap="round" />
            <line x1="3" y1="10" x2="17" y2="10" stroke="white" strokeWidth="2" strokeLinecap="round" />
          </svg>
          Создать организацию
        </button>
      </div>

      <div className="bg-white rounded-[5px] shadow-[0_4px_4px_rgba(0,0,0,0.25)] overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-[#cbe3ff]">
              {["Название", "Slug", "Тариф", "Статус", "Дата создания", ""].map((h) => (
                <th key={h} className="text-left px-6 py-3 text-[16px] font-semibold text-primary">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-6 py-4 text-center text-primary/50 text-[16px]">Загрузка…</td>
              </tr>
            )}
            {!isLoading && (orgs ?? []).length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-4 text-center text-primary/50 text-[16px]">
                  Организаций пока нет
                </td>
              </tr>
            )}
            {(orgs ?? []).map((org) => (
              <tr
                key={org.id}
                className="border-t-2 border-[#cbe3ff] hover:bg-mainbg/40 transition-colors"
              >
                <td className="px-6 py-3 text-[15px] font-semibold text-primary">{org.display_name}</td>
                <td className="px-6 py-3 text-[14px] text-primary/70 font-mono">{org.slug}</td>
                <td className="px-6 py-3 text-[14px] font-medium text-primary">
                  {PLAN_LABELS[org.plan] ?? org.plan}
                </td>
                <td className={cn(
                  "px-6 py-3 text-[14px] font-medium",
                  org.is_active ? "text-[#20BE4F]" : "text-[#C22A2A]"
                )}>
                  {org.is_active ? "Активна" : "Отключена"}
                </td>
                <td className="px-6 py-3 text-[14px] text-primary">{fmtDate(org.created_at)}</td>
                <td className="px-6 py-3">
                  {org.is_active ? (
                    <button
                      onClick={() => updateOrg.mutate({ orgId: org.id, body: { is_active: false } })}
                      className="text-[13px] text-[#C22A2A] hover:underline"
                    >
                      Отключить
                    </button>
                  ) : (
                    <button
                      onClick={() => updateOrg.mutate({ orgId: org.id, body: { is_active: true } })}
                      className="text-[13px] text-[#20BE4F] hover:underline"
                    >
                      Включить
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Main export ── */
export function AdminPage() {
  const user = useAuthStore((s) => s.user);
  const isPlatformAdmin = user?.roles.some((r) => r.id === "platform_admin") ?? false;

  const sidebarItems = ALL_ADMIN_ITEMS.filter(
    (item) => !item.platformOnly || isPlatformAdmin
  );

  const defaultSection: AdminSection = isPlatformAdmin ? "home" : "logs";
  const [section, setSection] = useState<AdminSection>(defaultSection);

  const contentMap: Record<AdminSection, React.ReactNode> = {
    home:          <AdminDashboard />,
    orgs:          <AdminOrgs />,
    logs:          <AdminLogs />,
    users:         <AdminUsers />,
    groups:        <AdminGroups />,
    roles:         <AdminRoles />,
    apps:          <AdminApps />,
    databases:     <AdminDatabases />,
    sessions:      <AdminSessions />,
    notifications: <EmailTemplatesContent className="h-[920px]" />,
  };

  return (
    <div className="relative w-[1920px] h-[1080px] bg-white overflow-hidden">
      <Navbar />
      <AdminSidebar active={section} onChange={setSection} items={sidebarItems} />

      <main
        className="absolute bg-mainbg overflow-y-auto"
        style={{
          left: 280,
          top: 70,
          width: 1625,
          height: 1000,
          borderRadius: 20,
          padding: 40,
        }}
      >
        {contentMap[section]}
      </main>
    </div>
  );
}

/* ── Roles ── */
function AdminRoles() {
  const { data: roles = [], isLoading } = useAllRoles();
  const createRole = useCreateRole();
  const deleteRole = useDeleteRole();

  const [createOpen, setCreateOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: string; name: string } | null>(null);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");

  const systemRoles = roles.filter((r) => r.is_system);
  const customRoles = roles.filter((r) => !r.is_system);

  function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    createRole.mutate(
      { display_name: newName.trim(), description: newDesc.trim() || undefined },
      {
        onSuccess: () => {
          setCreateOpen(false);
          setNewName("");
          setNewDesc("");
        },
      }
    );
  }

  return (
    <div className="flex flex-col gap-[40px]">
      {/* Create modal */}
      {createOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: "rgba(0,32,95,0.35)" }}
          onClick={() => setCreateOpen(false)}
        >
          <div
            className="bg-white rounded-[20px] w-[460px] flex flex-col"
            style={{ boxShadow: "0 8px 40px rgba(0,32,95,0.18)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-[30px] pt-[28px] pb-[20px]">
              <span className="text-[22px] font-bold text-primary">Создать роль</span>
              <button
                onClick={() => setCreateOpen(false)}
                className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-mainbg transition-colors text-primary/40 text-[22px] leading-none"
              >×</button>
            </div>
            <form onSubmit={handleCreate} className="flex flex-col gap-[18px] px-[30px] pb-[28px]">
              <div className="flex flex-col gap-[6px]">
                <label className="text-[13px] font-medium text-primary/60">Название роли</label>
                <input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  required
                  placeholder="Менеджер склада"
                  className="h-[42px] px-[14px] bg-mainbg rounded-[10px] text-[15px] text-primary outline-none border border-transparent focus:border-cta transition-colors placeholder:text-primary/30"
                />
              </div>
              <div className="flex flex-col gap-[6px]">
                <label className="text-[13px] font-medium text-primary/60">Описание <span className="text-primary/30">(необязательно)</span></label>
                <textarea
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  rows={2}
                  placeholder="Краткое описание роли и её назначения"
                  className="px-[14px] py-[10px] bg-mainbg rounded-[10px] text-[15px] text-primary outline-none border border-transparent focus:border-cta transition-colors placeholder:text-primary/30 resize-none"
                />
              </div>
              {createRole.isError && (
                <p className="text-[13px] text-[#C22A2A] bg-[#FFF0F0] rounded-[8px] px-3 py-2">
                  Ошибка создания роли
                </p>
              )}
              <div className="flex gap-[10px] justify-end pt-[4px]">
                <button type="button" onClick={() => setCreateOpen(false)}
                  className="h-[42px] px-[22px] border-2 border-primary/20 rounded-[20px] text-[15px] text-primary hover:bg-mainbg transition-colors">
                  Отмена
                </button>
                <button type="submit" disabled={createRole.isPending}
                  className="h-[42px] px-[22px] bg-cta rounded-[20px] text-[15px] font-semibold text-white hover:bg-active transition-colors disabled:opacity-50">
                  {createRole.isPending ? "Создание…" : "Создать"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete confirm */}
      {deleteConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: "rgba(0,32,95,0.35)" }}
          onClick={() => setDeleteConfirm(null)}
        >
          <div
            className="bg-white rounded-[20px] w-[420px] p-[30px] flex flex-col gap-[20px]"
            style={{ boxShadow: "0 8px 40px rgba(0,32,95,0.18)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex flex-col gap-[8px]">
              <span className="text-[20px] font-bold text-primary">Удалить роль?</span>
              <span className="text-[15px] text-primary/60">
                Роль <strong className="text-primary">{deleteConfirm.name}</strong> будет удалена. Пользователи с этой ролью потеряют её.
              </span>
            </div>
            <div className="flex gap-[10px] justify-end">
              <button onClick={() => setDeleteConfirm(null)}
                className="h-[42px] px-[22px] border-2 border-primary/20 rounded-[20px] text-[15px] text-primary hover:bg-mainbg transition-colors">
                Отмена
              </button>
              <button
                onClick={() => deleteRole.mutate(deleteConfirm.id, { onSuccess: () => setDeleteConfirm(null) })}
                disabled={deleteRole.isPending}
                className="h-[42px] px-[22px] bg-[#C22A2A] rounded-[20px] text-[15px] font-semibold text-white hover:bg-[#A01E1E] transition-colors disabled:opacity-50"
              >
                {deleteRole.isPending ? "Удаление…" : "Удалить"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[40px] font-bold text-primary leading-[150%]">Роли</h1>
          <p className="text-[16px] text-primary/60 mt-1">
            Системные роли встроены в платформу. Пользовательские роли можно создавать и удалять.
          </p>
        </div>
        <button
          onClick={() => setCreateOpen(true)}
          className="flex items-center gap-2 h-[42px] px-6 bg-cta rounded-[20px] text-[16px] font-semibold text-white hover:bg-cta/90 transition-colors"
        >
          <svg viewBox="0 0 20 20" fill="none" className="w-5 h-5">
            <line x1="10" y1="3" x2="10" y2="17" stroke="white" strokeWidth="2" strokeLinecap="round" />
            <line x1="3" y1="10" x2="17" y2="10" stroke="white" strokeWidth="2" strokeLinecap="round" />
          </svg>
          Создать роль
        </button>
      </div>

      {isLoading && <div className="text-primary/40 text-[15px]">Загрузка…</div>}

      {/* System roles */}
      {systemRoles.length > 0 && (
        <div className="flex flex-col gap-[16px]">
          <h2 className="text-[18px] font-semibold text-primary">Системные роли</h2>
          <div className="bg-white rounded-[5px] shadow-[0_4px_4px_rgba(0,0,0,0.25)] overflow-hidden">
            <table className="w-full">
              <thead className="bg-mainbg">
                <tr>
                  {["Роль", "ID", "Описание", "Тип"].map((h) => (
                    <th key={h} className="text-left px-6 py-3 text-[13px] font-semibold text-primary">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {systemRoles.map((r) => (
                  <tr key={r.id} className="border-t border-mainbg">
                    <td className="px-6 py-3 text-[15px] font-semibold text-primary">{r.display_name}</td>
                    <td className="px-6 py-3 text-[13px] text-primary/60 font-mono">{r.id}</td>
                    <td className="px-6 py-3 text-[13px] text-primary/60">{r.description ?? "—"}</td>
                    <td className="px-6 py-3">
                      <span className="text-[11px] font-semibold bg-cta/10 text-cta px-2 py-0.5 rounded-full">
                        системная
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Custom roles */}
      <div className="flex flex-col gap-[16px]">
        <h2 className="text-[18px] font-semibold text-primary">
          Пользовательские роли
          {customRoles.length > 0 && (
            <span className="ml-2 text-[14px] font-normal text-primary/40">({customRoles.length})</span>
          )}
        </h2>
        {customRoles.length === 0 ? (
          <div className="bg-white rounded-[12px] border border-cardbg p-8 text-center text-[15px] text-primary/40">
            Пользовательских ролей пока нет. Создайте первую роль для вашей организации.
          </div>
        ) : (
          <div className="bg-white rounded-[5px] shadow-[0_4px_4px_rgba(0,0,0,0.25)] overflow-hidden">
            <table className="w-full">
              <thead className="bg-mainbg">
                <tr>
                  {["Название", "ID", "Описание", "Тип", ""].map((h) => (
                    <th key={h} className="text-left px-6 py-3 text-[13px] font-semibold text-primary">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {customRoles.map((r) => (
                  <tr key={r.id} className="border-t border-mainbg hover:bg-mainbg/40">
                    <td className="px-6 py-3 text-[15px] font-semibold text-primary">{r.display_name}</td>
                    <td className="px-6 py-3 text-[12px] text-primary/50 font-mono">{r.id}</td>
                    <td className="px-6 py-3 text-[13px] text-primary/60">{r.description ?? "—"}</td>
                    <td className="px-6 py-3">
                      <span className="text-[11px] font-semibold bg-[#20BE4F]/10 text-[#20BE4F] px-2 py-0.5 rounded-full">
                        пользовательская
                      </span>
                    </td>
                    <td className="px-6 py-3 text-right">
                      <button
                        onClick={() => setDeleteConfirm({ id: r.id, name: r.display_name })}
                        className="text-[13px] text-primary/40 hover:text-[#C22A2A] transition-colors"
                      >
                        Удалить
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Icons ── */
function OrgsIcon() {
  return (
    <svg viewBox="0 0 25 25" fill="none" className="w-full h-full">
      <rect x="2" y="7" width="10" height="14" rx="2" stroke="#00205F" strokeWidth="2"/>
      <rect x="13" y="3" width="10" height="18" rx="2" stroke="#00205F" strokeWidth="2"/>
      <line x1="5" y1="11" x2="9" y2="11" stroke="#00205F" strokeWidth="1.5" strokeLinecap="round"/>
      <line x1="5" y1="14" x2="9" y2="14" stroke="#00205F" strokeWidth="1.5" strokeLinecap="round"/>
      <line x1="16" y1="7" x2="20" y2="7" stroke="#00205F" strokeWidth="1.5" strokeLinecap="round"/>
      <line x1="16" y1="11" x2="20" y2="11" stroke="#00205F" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  );
}

function HomeIcon() {
  return (
    <svg viewBox="0 0 25 25" fill="none" className="w-full h-full">
      <path d="M3 10 L12.5 3 L22 10 L22 22 L3 22 Z" stroke="#00205F" strokeWidth="2" strokeLinejoin="round"/>
      <rect x="9" y="15" width="7" height="7" fill="#00205F" rx="1"/>
    </svg>
  );
}

function LogsIcon() {
  return (
    <svg viewBox="0 0 25 25" fill="none" className="w-full h-full">
      <rect x="4" y="2" width="17" height="21" rx="2" stroke="#00205F" strokeWidth="2"/>
      <line x1="8" y1="8"  x2="17" y2="8"  stroke="#00205F" strokeWidth="1.5" strokeLinecap="round"/>
      <line x1="8" y1="12" x2="17" y2="12" stroke="#00205F" strokeWidth="1.5" strokeLinecap="round"/>
      <line x1="8" y1="16" x2="13" y2="16" stroke="#00205F" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  );
}

function UsersIcon() {
  return (
    <svg viewBox="0 0 29 29" fill="none" className="w-full h-full">
      <circle cx="14.5" cy="10" r="5" stroke="#00205F" strokeWidth="2"/>
      <path d="M4 26 C4 20 8.5 17 14.5 17 C20.5 17 25 20 25 26" stroke="#00205F" strokeWidth="2" strokeLinecap="round"/>
    </svg>
  );
}

function GroupsIcon() {
  return (
    <svg viewBox="0 0 29 29" fill="none" className="w-full h-full">
      <circle cx="10" cy="11" r="4.5" stroke="#00205F" strokeWidth="2"/>
      <circle cx="21" cy="11" r="4.5" stroke="#00205F" strokeWidth="2"/>
      <path d="M2 26c0-5 3.5-8 8-8h4c4.5 0 8 3 8 8" stroke="#00205F" strokeWidth="2" strokeLinecap="round"/>
      <path d="M19 18c2.5 0 6 1.5 7 7" stroke="#00205F" strokeWidth="2" strokeLinecap="round"/>
    </svg>
  );
}

function AppsIcon() {
  return (
    <svg viewBox="0 0 23 23" fill="none" className="w-full h-full">
      <rect x="4" y="1" width="15" height="21" rx="3" stroke="#00205F" strokeWidth="2"/>
      <circle cx="11.5" cy="18.5" r="1" fill="#00205F"/>
    </svg>
  );
}

function DbIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
      <ellipse cx="12" cy="6" rx="8" ry="3" stroke="#00205F" strokeWidth="2"/>
      <path d="M4 6 L4 18 C4 19.66 7.58 21 12 21 C16.42 21 20 19.66 20 18 L20 6" stroke="#00205F" strokeWidth="2"/>
      <path d="M4 12 C4 13.66 7.58 15 12 15 C16.42 15 20 13.66 20 12" stroke="#00205F" strokeWidth="2"/>
    </svg>
  );
}

function RolesNavIcon() {
  return (
    <svg viewBox="0 0 25 25" fill="none" className="w-full h-full">
      <path d="M12.5 3L20 7v6c0 4.5-3.5 8-7.5 9C5 21 2 17.5 2 13V7z" stroke="#00205F" strokeWidth="2" strokeLinejoin="round"/>
      <path d="M9 12l2.5 2.5 4-4" stroke="#00205F" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function SessionsNavIcon() {
  return (
    <svg viewBox="0 0 25 25" fill="none" className="w-full h-full">
      <rect x="3" y="6" width="19" height="13" rx="2" stroke="#00205F" strokeWidth="2"/>
      <path d="M3 10h19" stroke="#00205F" strokeWidth="1.5"/>
      <circle cx="7" cy="15" r="1.5" fill="#00205F"/>
      <circle cx="12.5" cy="15" r="1.5" fill="#00205F"/>
    </svg>
  );
}

function NotifNavIcon() {
  return (
    <svg viewBox="0 0 25 25" fill="none" className="w-full h-full">
      <rect x="3" y="5" width="19" height="14" rx="2" stroke="#00205F" strokeWidth="2"/>
      <path d="M3 9l9.5 6 9.5-6" stroke="#00205F" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  );
}

/* ── Admin sessions ── */
function AdminSessions() {
  const { data: sessions = [], isLoading, refetch } = useAllSessions();
  const terminate = useTerminateSession();
  const terminateAll = useTerminateUserSessions();

  function fmtDate(iso: string | null): string {
    if (!iso) return "—";
    return new Date(iso).toLocaleString("ru-RU", {
      day: "2-digit", month: "2-digit", year: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  }

  function fmtAgent(ua: string | null): string {
    if (!ua) return "—";
    if (ua.includes("Chrome")) return "Chrome";
    if (ua.includes("Firefox")) return "Firefox";
    if (ua.includes("Safari")) return "Safari";
    if (ua.includes("Edge")) return "Edge";
    return ua.slice(0, 28);
  }

  // Group by user for "terminate all" action
  const byUser = sessions.reduce<Record<string, string>>((acc, s) => {
    if (!acc[s.user_id]) acc[s.user_id] = s.user_email ?? s.user_id;
    return acc;
  }, {});

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-[26px] font-semibold text-primary">Активные сессии</h2>
          <p className="text-[14px] text-primary/50 mt-1">
            {sessions.length} активных сессий · {Object.keys(byUser).length} пользователей
          </p>
        </div>
        <button
          onClick={() => void refetch()}
          className="flex items-center gap-2 px-4 h-[38px] border border-cardbg rounded-btn text-[14px] text-primary hover:bg-mainbg transition-colors"
        >
          <svg viewBox="0 0 20 20" className="w-4 h-4" fill="none">
            <path d="M4 10a6 6 0 016-6 6 6 0 014.5 2M16 10a6 6 0 01-6 6 6 6 0 01-4.5-2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            <path d="M14.5 6V2.5M14.5 2.5H11M14.5 2.5l-2 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Обновить
        </button>
      </div>

      {isLoading ? (
        <div className="text-primary/40 text-[15px]">Загрузка сессий…</div>
      ) : sessions.length === 0 ? (
        <div className="bg-white rounded-[12px] border border-cardbg px-8 py-12 text-center text-[15px] text-primary/40">
          Нет активных сессий
        </div>
      ) : (
        <div className="bg-white rounded-[12px] border border-cardbg overflow-hidden">
          <table className="w-full text-[14px]">
            <thead>
              <tr className="bg-mainbg border-b border-cardbg">
                <th className="text-left px-5 py-3 font-semibold text-primary/60">Пользователь</th>
                <th className="text-left px-5 py-3 font-semibold text-primary/60">IP-адрес</th>
                <th className="text-left px-5 py-3 font-semibold text-primary/60">Браузер</th>
                <th className="text-left px-5 py-3 font-semibold text-primary/60">Последняя активность</th>
                <th className="text-left px-5 py-3 font-semibold text-primary/60">Создана</th>
                <th className="px-5 py-3 text-right font-semibold text-primary/60">Действие</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s, i) => (
                <tr key={s.id} className={cn("border-b last:border-0 border-cardbg", i % 2 !== 0 && "bg-mainbg/20")}>
                  <td className="px-5 py-3">
                    <div className="font-medium text-primary">{s.user_name ?? "—"}</div>
                    <div className="text-[12px] text-primary/50">{s.user_email ?? ""}</div>
                  </td>
                  <td className="px-5 py-3 font-mono text-primary/70">{s.ip_address ?? "—"}</td>
                  <td className="px-5 py-3 text-primary/70">{fmtAgent(s.user_agent)}</td>
                  <td className="px-5 py-3 text-primary/70">{fmtDate(s.last_activity_at)}</td>
                  <td className="px-5 py-3 text-primary/70">{fmtDate(s.created_at)}</td>
                  <td className="px-5 py-3 text-right">
                    <div className="flex items-center justify-end gap-3">
                      <button
                        onClick={() => terminate.mutate(s.id)}
                        disabled={terminate.isPending}
                        className="text-[13px] text-mistake hover:underline disabled:opacity-40"
                      >
                        Завершить
                      </button>
                      <button
                        onClick={() => terminateAll.mutate(s.user_id)}
                        disabled={terminateAll.isPending}
                        className="text-[13px] text-primary/50 hover:text-mistake hover:underline disabled:opacity-40"
                        title="Завершить все сессии пользователя"
                      >
                        Все сессии
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
