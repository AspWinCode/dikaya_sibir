import { http, HttpResponse } from "msw";
import type { App, CursorPage } from "@/shared/api/apps";
import type { CurrentUser, TokenPair } from "@/shared/api/auth";
import type { EntityRead, FieldRead } from "@/shared/api/entities";
import type { Rule } from "@/shared/api/rules";
import type { User, UserRole } from "@/shared/api/users";
import type { RecordRead, TrashedRecordRead } from "@/shared/api/records";
import type { ViewRead, PageRead } from "@/shared/api/views";
import type { WorkflowDefRead, StateDefRead, ApprovalChainDefRead, ApprovalChainInstanceRead } from "@/shared/api/workflows";
import type { WebhookRead } from "@/shared/api/webhooks";
import type { ModuleInstallResult, ModuleRead } from "@/shared/api/modules";
import type { EmailTemplateRead } from "@/shared/api/emailTemplates";

/**
 * In-memory mock backend for local frontend dev without Docker.
 * Enabled only when VITE_USE_MOCKS=true (see src/mocks/browser.ts).
 * Accepts any non-empty credentials; rejects password "wrong" to demo errors.
 */

const API = "/api/v1";

const MOCK_USER: CurrentUser = {
  id: "00000000-0000-0000-0000-000000000001",
  email: "admin@nocode.local",
  display_name: "Platform Admin",
  is_active: true,
  is_superuser: true,
  totp_enabled: false,
  last_login_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  roles: [
    { id: "platform_admin", display_name: "Platform Admin" },
    { id: "app_builder", display_name: "App Builder" },
  ],
};

function makeApp(partial: Partial<App> & Pick<App, "slug" | "name">): App {
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    description: null,
    icon: null,
    color: null,
    category: null,
    owner_id: MOCK_USER.id,
    is_published: false,
    is_archived: false,
    settings: {},
    version: 1,
    created_at: now,
    updated_at: now,
    ...partial,
  };
}

const apps: App[] = [
  makeApp({
    slug: "wild-siberia",
    name: "Дикая Сибирь",
    description: "Приложение для анализа и контроля физической нагрузки",
    is_published: false,
    updated_at: new Date(Date.now() - 6 * 86400_000).toISOString(),
  }),
  makeApp({
    slug: "delivery-app",
    name: "Delivery App",
    description: "Сбор корзины, оформление заказа и доставка",
    is_published: true,
    updated_at: new Date(Date.now() - 2 * 86400_000).toISOString(),
  }),
];

const moduleCatalog: ModuleRead[] = [
  { code: "enterprise", name: "Enterprise", category: "Base", description: "Base company directories", dependencies: [], color: "#4C6EF5", icon: "building" },
  { code: "warehouse", name: "Warehouse", category: "Operations", description: "Products, balances and stock operations", dependencies: ["enterprise"], color: "#8B5CF6", icon: "package" },
  { code: "production", name: "Production", category: "Operations", description: "Production orders, BOM and operations", dependencies: ["enterprise", "warehouse"], color: "#64748B", icon: "settings" },
  { code: "orders", name: "Orders and shipments", category: "Operations", description: "Customer orders and shipments", dependencies: ["enterprise", "warehouse"], color: "#06B6D4", icon: "truck" },
  { code: "finance", name: "Finance", category: "Finance", description: "Budgets, payments and transactions", dependencies: ["enterprise"], color: "#059669", icon: "coins" },
  { code: "contracts", name: "Contracts", category: "Finance", description: "Contracts and execution stages", dependencies: ["enterprise"], color: "#DC2626", icon: "file" },
  { code: "hr", name: "HR", category: "HR", description: "Candidates, hiring and reviews", dependencies: ["enterprise"], color: "#DB2777", icon: "users" },
  { code: "projects", name: "Tasks and projects", category: "Productivity", description: "Projects, tasks and milestones", dependencies: ["enterprise"], color: "#10B981", icon: "check" },
  { code: "analytics", name: "Analytics", category: "Analytics", description: "KPI, dashboards and reports", dependencies: [], color: "#0EA5E9", icon: "chart" },
  { code: "documents", name: "Document flow", category: "Documents", description: "Documents and filing cases", dependencies: ["enterprise"], color: "#7C3AED", icon: "file" },
  { code: "it_support", name: "IT support", category: "IT", description: "Tickets, equipment and SLA", dependencies: ["enterprise"], color: "#EA580C", icon: "tool" },
].map((m, index) => ({
  id: `module-${index + 1}`,
  is_base: m.code === "enterprise",
  is_active: true,
  current_version: "1.0.0",
  installed: false,
  installed_version: null,
  created_at: "2026-01-01T00:00:00Z",
  ...m,
}));

const installedModulesByApp: Record<string, Set<string>> = {};

function modulesForApp(appId: string | null): ModuleRead[] {
  const installed = appId ? installedModulesByApp[appId] ?? new Set<string>() : new Set<string>();
  return moduleCatalog.map((m) => ({
    ...m,
    installed: installed.has(m.code),
    installed_version: installed.has(m.code) ? m.current_version : null,
  }));
}

/* ── Mock Users ── */
const MOCK_ROLES: UserRole[] = [
  { id: "platform_admin", display_name: "Platform Admin" },
  { id: "app_builder",    display_name: "App Builder" },
  { id: "auditor",        display_name: "Auditor" },
  { id: "viewer",         display_name: "Viewer" },
];

const mockUsers: User[] = [
  {
    id: "00000000-0000-0000-0000-000000000001",
    email: "admin@nocode.local",
    display_name: "Platform Admin",
    is_active: true,
    is_blocked: false,
    is_superuser: true,
    totp_enabled: false,
    last_login_at: new Date().toISOString(),
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    roles: [{ id: "platform_admin", display_name: "Platform Admin" }],
  },
  {
    id: "00000000-0000-0000-0000-000000000002",
    email: "ivan@mail.ru",
    display_name: "Иван Петров",
    is_active: true,
    is_blocked: false,
    is_superuser: false,
    totp_enabled: false,
    last_login_at: new Date(Date.now() - 2 * 86400_000).toISOString(),
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    roles: [{ id: "app_builder", display_name: "App Builder" }],
  },
  {
    id: "00000000-0000-0000-0000-000000000003",
    email: "anna@corp.ru",
    display_name: "Анна Соколова",
    is_active: true,
    is_blocked: false,
    is_superuser: false,
    totp_enabled: true,
    last_login_at: new Date(Date.now() - 1 * 86400_000).toISOString(),
    created_at: "2026-02-15T00:00:00Z",
    updated_at: "2026-02-15T00:00:00Z",
    roles: [{ id: "app_builder", display_name: "App Builder" }, { id: "auditor", display_name: "Auditor" }],
  },
  {
    id: "00000000-0000-0000-0000-000000000004",
    email: "dev@example.com",
    display_name: "Dev User",
    is_active: false,
    is_blocked: false,
    is_superuser: false,
    totp_enabled: false,
    last_login_at: null,
    created_at: "2026-03-20T00:00:00Z",
    updated_at: "2026-03-20T00:00:00Z",
    roles: [{ id: "viewer", display_name: "Viewer" }],
  },
  {
    id: "00000000-0000-0000-0000-000000000005",
    email: "maria@mail.ru",
    display_name: "Мария Иванова",
    is_active: true,
    is_blocked: false,
    is_superuser: false,
    totp_enabled: false,
    last_login_at: new Date(Date.now() - 3 * 86400_000).toISOString(),
    created_at: "2026-04-05T00:00:00Z",
    updated_at: "2026-04-05T00:00:00Z",
    roles: [{ id: "app_builder", display_name: "App Builder" }],
  },
];

/* ── Mock Entities ── */
function makeField(
  partial: Partial<FieldRead> & Pick<FieldRead, "id" | "entity_id" | "app_id" | "name" | "display_name" | "field_type" | "display_order">
): FieldRead {
  const now = new Date().toISOString();
  return {
    is_required: false, is_unique: false, is_system: false, is_indexed: false, is_sensitive: false,
    default_value: null, validation_rules: {}, field_options: {},
    formula_definition: null,
    created_at: now, updated_at: now,
    ...partial,
  };
}

const ENTITY_ID = "00000000-0000-0000-0000-000000000010";

function buildEntities(appId: string): EntityRead[] {
  const now = new Date().toISOString();
  const e1Id = ENTITY_ID;
  const e2Id = "00000000-0000-0000-0000-000000000011";
  const e3Id = "00000000-0000-0000-0000-000000000012";

  return [
    {
      id: e1Id, app_id: appId, slug: "analytics", display_name: "Аналитика",
      name_plural: null, description: null, icon: null, color: null,
      settings: {}, is_system: false, field_order: [],
      created_at: now, updated_at: now,
      fields: [
        makeField({ id: "f1", entity_id: e1Id, app_id: appId, name: "_row_number", display_name: "_RowNumber", field_type: "number", display_order: 0, is_system: true, is_unique: true }),
        makeField({ id: "f2", entity_id: e1Id, app_id: appId, name: "row_id",      display_name: "Row ID",     field_type: "text",   display_order: 1, is_system: true, is_unique: true }),
        makeField({ id: "f3", entity_id: e1Id, app_id: appId, name: "module",      display_name: "Модуль",     field_type: "text",   display_order: 2, is_required: true }),
        makeField({ id: "f4", entity_id: e1Id, app_id: appId, name: "view",        display_name: "Вид",        field_type: "select", display_order: 3 }),
        makeField({ id: "f5", entity_id: e1Id, app_id: appId, name: "status",      display_name: "Статус",     field_type: "select", display_order: 4 }),
      ],
    },
    {
      id: e2Id, app_id: appId, slug: "audit", display_name: "Аудит",
      name_plural: null, description: null, icon: null, color: null,
      settings: {}, is_system: false, field_order: [],
      created_at: now, updated_at: now,
      fields: [
        makeField({ id: "f10", entity_id: e2Id, app_id: appId, name: "_row_number", display_name: "_RowNumber", field_type: "number", display_order: 0, is_system: true }),
        makeField({ id: "f11", entity_id: e2Id, app_id: appId, name: "action",      display_name: "Действие",   field_type: "text",   display_order: 1, is_required: true }),
        makeField({ id: "f12", entity_id: e2Id, app_id: appId, name: "user_id",     display_name: "Пользователь", field_type: "relation", display_order: 2 }),
        makeField({ id: "f13", entity_id: e2Id, app_id: appId, name: "created_at",  display_name: "Создан",     field_type: "datetime", display_order: 3, is_system: true }),
      ],
    },
    {
      id: e3Id, app_id: appId, slug: "main_menu", display_name: "Главное меню",
      name_plural: null, description: null, icon: null, color: null,
      settings: {}, is_system: false, field_order: [],
      created_at: now, updated_at: now,
      fields: [
        makeField({ id: "f20", entity_id: e3Id, app_id: appId, name: "_row_number", display_name: "_RowNumber", field_type: "number", display_order: 0, is_system: true }),
        makeField({ id: "f21", entity_id: e3Id, app_id: appId, name: "label",       display_name: "Название",   field_type: "text",   display_order: 1, is_required: true }),
        makeField({ id: "f22", entity_id: e3Id, app_id: appId, name: "icon",        display_name: "Иконка",     field_type: "image",  display_order: 2 }),
        makeField({ id: "f23", entity_id: e3Id, app_id: appId, name: "route",       display_name: "Маршрут",    field_type: "url",    display_order: 3 }),
      ],
    },
  ];
}

/* entities is keyed by appId */
const entitiesByApp: Record<string, EntityRead[]> = {};

const rules: Rule[] = [
  {
    id: "r1",
    app_id: apps[0].id,
    entity_id: ENTITY_ID,
    name: "insert",
    description: null,
    is_active: false,
    rule_type: "automation" as const,
    trigger: { event: "record.created", watch_fields: [] },
    conditions: {},
    actions: [],
    priority: 100,
    version: 1,
    created_by: MOCK_USER.id,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "r2",
    app_id: apps[0].id,
    entity_id: ENTITY_ID,
    name: "update",
    description: null,
    is_active: false,
    rule_type: "automation" as const,
    trigger: { event: "record.updated", watch_fields: [] },
    conditions: {},
    actions: [],
    priority: 100,
    version: 1,
    created_by: MOCK_USER.id,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "r3",
    app_id: apps[0].id,
    entity_id: ENTITY_ID,
    name: "delete",
    description: null,
    is_active: false,
    rule_type: "automation" as const,
    trigger: { event: "record.deleted", watch_fields: [] },
    conditions: {},
    actions: [],
    priority: 100,
    version: 1,
    created_by: MOCK_USER.id,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "r4",
    app_id: apps[0].id,
    entity_id: ENTITY_ID,
    name: "Отчет TG 2",
    description: null,
    is_active: true,
    rule_type: "automation" as const,
    trigger: { event: "record.created", watch_fields: [] },
    conditions: {},
    actions: [],
    priority: 90,
    version: 1,
    created_by: MOCK_USER.id,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "r5",
    app_id: apps[0].id,
    entity_id: ENTITY_ID,
    name: "(disable) Ошибка отчета",
    description: null,
    is_active: false,
    rule_type: "automation" as const,
    trigger: { event: "record.updated", watch_fields: [] },
    conditions: {},
    actions: [],
    priority: 80,
    version: 1,
    created_by: MOCK_USER.id,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "r6",
    app_id: apps[0].id,
    entity_id: ENTITY_ID,
    name: "New Bot 9",
    description: null,
    is_active: false,
    rule_type: "automation" as const,
    trigger: { event: "record.created", watch_fields: [] },
    conditions: {},
    actions: [],
    priority: 70,
    version: 1,
    created_by: MOCK_USER.id,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "r7",
    app_id: apps[0].id,
    entity_id: ENTITY_ID,
    name: "Аналитические таблицы",
    description: null,
    is_active: true,
    rule_type: "automation" as const,
    trigger: { event: "record.updated", watch_fields: [] },
    conditions: {},
    actions: [],
    priority: 60,
    version: 1,
    created_by: MOCK_USER.id,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "r8",
    app_id: apps[0].id,
    entity_id: ENTITY_ID,
    name: "New Bot 10",
    description: null,
    is_active: false,
    rule_type: "automation" as const,
    trigger: { event: "record.deleted", watch_fields: [] },
    conditions: {},
    actions: [],
    priority: 50,
    version: 1,
    created_by: MOCK_USER.id,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

const mockRuleConflicts = [
  {
    id: "conflict-1",
    entity_id: ENTITY_ID,
    record_id: "00000000-0000-0000-0000-000000000001",
    event: "record.updated",
    field_name: "status",
    winning_rule_id: "r1",
    winning_value: "approved",
    losing_writes: [{ rule_id: "r2", value: "rejected" }],
    execution_batch_id: "batch-1",
    detected_at: new Date().toISOString(),
  },
];

const mockRuleWebhookDeliveries = [
  {
    id: "wh-1",
    entity_id: ENTITY_ID,
    record_id: "00000000-0000-0000-0000-000000000001",
    execution_batch_id: "batch-1",
    url: "https://hooks.example.com/lesovik",
    method: "POST",
    status: "delivered",
    status_code: 200,
    error: null,
    attempt_count: 1,
    created_at: new Date().toISOString(),
  },
  {
    id: "wh-2",
    entity_id: ENTITY_ID,
    record_id: "00000000-0000-0000-0000-000000000002",
    execution_batch_id: "batch-2",
    url: "http://169.254.169.254/latest/meta-data/",
    method: "POST",
    status: "blocked",
    status_code: null,
    error: "Blocked: '169.254.169.254' resolves to non-public address 169.254.169.254",
    attempt_count: 1,
    created_at: new Date().toISOString(),
  },
];

/* ── Mock Records ── */
const mockRecords: RecordRead[] = [
  {
    id: "rec-1", entity_id: ENTITY_ID, payload: { name: "Record 1", status: "active" },
    version: 1, is_deleted: false, deleted_at: null, deleted_by: null,
    created_by: MOCK_USER.id, updated_by: null,
    created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  },
  {
    id: "rec-2", entity_id: ENTITY_ID, payload: { name: "Record 2", status: "active" },
    version: 1, is_deleted: false, deleted_at: null, deleted_by: null,
    created_by: MOCK_USER.id, updated_by: null,
    created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  },
  {
    id: "rec-3", entity_id: ENTITY_ID, payload: { name: "Record 3", status: "active" },
    version: 1, is_deleted: false, deleted_at: null, deleted_by: null,
    created_by: MOCK_USER.id, updated_by: null,
    created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  },
];

const mockTrash: TrashedRecordRead[] = [];

/* ── Mock Views (per entity per app) ── */
const viewsByApp: Record<string, ViewRead[]> = {};

function buildViews(appId: string, entityId: string): ViewRead[] {
  const now = new Date().toISOString();
  return [
    {
      id: `view-${entityId}-table`, app_id: appId, entity_id: entityId,
      name: "Таблица", view_type: "table", config: {}, is_default: true,
      is_public: false, created_by: MOCK_USER.id, created_at: now, updated_at: now,
    },
    {
      id: `view-${entityId}-form`, app_id: appId, entity_id: entityId,
      name: "Форма", view_type: "form", config: {}, is_default: false,
      is_public: false, created_by: MOCK_USER.id, created_at: now, updated_at: now,
    },
  ];
}

function viewsKey(appId: string, entityId: string) { return `${appId}__${entityId}`; }

/* ── Mock Pages (per app) ── */
const pagesByApp: Record<string, PageRead[]> = {};

function buildPages(appId: string): PageRead[] {
  const now = new Date().toISOString();
  return [
    {
      id: `page-${appId}-reports`, app_id: appId, slug: "reports", title: "Отчёты",
      icon: null, nav_order: 0, layout: {}, blocks: [], breakpoints: {}, is_published: false,
      published_at: null, created_at: now, updated_at: now,
    },
    {
      id: `page-${appId}-enterprise`, app_id: appId, slug: "enterprise", title: "Предприятие",
      icon: null, nav_order: 1, layout: {}, blocks: [], breakpoints: {}, is_published: false,
      published_at: null, created_at: now, updated_at: now,
    },
    {
      id: `page-${appId}-main-menu`, app_id: appId, slug: "main-menu", title: "Главное меню",
      icon: null, nav_order: 2, layout: {}, blocks: [], breakpoints: {}, is_published: false,
      published_at: null, created_at: now, updated_at: now,
    },
    {
      id: `page-${appId}-analytics`, app_id: appId, slug: "analytics", title: "Аналитика",
      icon: null, nav_order: 3, layout: {}, blocks: [], breakpoints: {}, is_published: false,
      published_at: null, created_at: now, updated_at: now,
    },
  ];
}

/* ── Mock Workflows ── */
const workflowsByApp: Record<string, WorkflowDefRead[]> = {};
const statesByWorkflow: Record<string, StateDefRead[]> = {};
const chainsByWorkflow: Record<string, ApprovalChainDefRead[]> = {};
const chainInstancesByWfInstance: Record<string, ApprovalChainInstanceRead[]> = {};

function buildWorkflows(appId: string): WorkflowDefRead[] {
  const now = new Date().toISOString();
  const wf1Id = `wf-${appId}-1`;
  const wf2Id = `wf-${appId}-2`;

  statesByWorkflow[wf1Id] = [
    { id: `s-${wf1Id}-1`, workflow_id: wf1Id, name: "new",        display_name: "Новый",      is_terminal: false, color: "#35A7FF", sla_seconds: null, on_enter_actions: [], on_exit_actions: [], sla_breach_actions: [], escalation_levels: [], assignee_type: null, assignee_id: null, approval_chain_id: null },
    { id: `s-${wf1Id}-2`, workflow_id: wf1Id, name: "in_progress", display_name: "В работе",   is_terminal: false, color: "#F59E0B", sla_seconds: 86400, on_enter_actions: [], on_exit_actions: [], sla_breach_actions: [], escalation_levels: [], assignee_type: null, assignee_id: null, approval_chain_id: null },
    { id: `s-${wf1Id}-3`, workflow_id: wf1Id, name: "done",        display_name: "Выполнено",  is_terminal: true,  color: "#10B981", sla_seconds: null, on_enter_actions: [], on_exit_actions: [], sla_breach_actions: [], escalation_levels: [], assignee_type: null, assignee_id: null, approval_chain_id: null },
  ];
  statesByWorkflow[wf2Id] = [
    { id: `s-${wf2Id}-1`, workflow_id: wf2Id, name: "draft",    display_name: "Черновик",   is_terminal: false, color: "#6B7280", sla_seconds: null, on_enter_actions: [], on_exit_actions: [], sla_breach_actions: [], escalation_levels: [], assignee_type: null, assignee_id: null, approval_chain_id: null },
    { id: `s-${wf2Id}-2`, workflow_id: wf2Id, name: "review",   display_name: "На проверке",is_terminal: false, color: "#8B5CF6", sla_seconds: 3600, on_enter_actions: [], on_exit_actions: [], sla_breach_actions: [], escalation_levels: [], assignee_type: null, assignee_id: null, approval_chain_id: null },
    { id: `s-${wf2Id}-3`, workflow_id: wf2Id, name: "approved", display_name: "Одобрено",   is_terminal: true,  color: "#10B981", sla_seconds: null, on_enter_actions: [], on_exit_actions: [], sla_breach_actions: [], escalation_levels: [], assignee_type: null, assignee_id: null, approval_chain_id: null },
  ];
  chainsByWorkflow[wf1Id] = [];
  chainsByWorkflow[wf2Id] = [];

  return [
    {
      id: wf1Id, app_id: appId, entity_id: ENTITY_ID, name: "Основной процесс",
      description: null, initial_state: "new", is_active: true, version: 1,
      created_at: now, updated_at: now,
    },
    {
      id: wf2Id, app_id: appId, entity_id: ENTITY_ID, name: "Процесс согласования",
      description: null, initial_state: "draft", is_active: false, version: 1,
      created_at: now, updated_at: now,
    },
  ];
}

/* ── Mock Webhooks ── */
const webhooksByApp: Record<string, WebhookRead[]> = {};

function buildWebhooks(appId: string): WebhookRead[] {
  const now = new Date().toISOString();
  return [
    {
      id: `wh-${appId}-1`, app_id: appId, name: "Основной вебхук",
      target_url: "https://example.com/webhook", events: ["record.created", "record.updated"],
      is_active: true, custom_headers: {}, timeout_seconds: 30, max_retries: 3,
      created_at: now, updated_at: now,
    },
  ];
}

/* ── Mock file policy ── */
const filePolicy = {
  max_file_size_mb: 100,
  max_files_per_record: 50,
  allowed_extensions: [
    "pdf", "docx", "xlsx", "pptx", "odt", "txt", "rtf",
    "jpg", "jpeg", "png", "gif", "webp", "svg",
    "zip", "rar", "7z",
  ],
  updated_at: new Date().toISOString(),
};

function tokenPair(): TokenPair {
  return {
    access_token: `mock-access-${Date.now()}`,
    refresh_token: `mock-refresh-${Date.now()}`,
    token_type: "bearer",
    expires_in: 3600,
  };
}

const mockInviteLinks: {
  id: string; app_id: string; role: string; allow_signup: boolean; max_uses: number | null;
  use_count: number; expires_at: string | null; created_at: string; token: string; revoked: boolean;
}[] = [];

export const handlers = [
  http.get(`${API}/health`, () =>
    HttpResponse.json({ status: "ok", version: "mock", checks: {} }),
  ),

  http.post(`${API}/auth/login`, async ({ request }) => {
    const body = (await request.json()) as { email?: string; password?: string };
    if (!body.email || !body.password) {
      return HttpResponse.json({ detail: "Invalid credentials" }, { status: 401 });
    }
    if (body.password === "wrong") {
      return HttpResponse.json({ detail: "Неверная почта или пароль" }, { status: 401 });
    }
    return HttpResponse.json(tokenPair());
  }),

  http.post(`${API}/auth/refresh`, () => HttpResponse.json(tokenPair())),

  http.post(`${API}/auth/logout`, () => new HttpResponse(null, { status: 204 })),

  http.get(`${API}/auth/file-policy`, () => HttpResponse.json(filePolicy)),

  http.put(`${API}/auth/file-policy`, async ({ request }) => {
    const body = (await request.json()) as Partial<typeof filePolicy>;
    Object.assign(filePolicy, body, { updated_at: new Date().toISOString() });
    return HttpResponse.json(filePolicy);
  }),

  http.get(`${API}/users/me`, () => HttpResponse.json(MOCK_USER)),

  http.get(`${API}/apps`, () => {
    const page: CursorPage<App> = {
      items: apps,
      next_cursor: null,
      has_more: false,
      total: apps.length,
    };
    return HttpResponse.json(page);
  }),

  http.get(`${API}/apps/:appId/publish/check`, () => {
    const issues = [
      {
        severity: "warning" as const,
        category: "block_no_source" as const,
        message: "Страница «Отчёты» не привязана к источнику данных",
        location: { page_id: "p1" },
      },
      {
        severity: "error" as const,
        category: "relation_invalid" as const,
        message: "Связь «Заказ → Клиент»: поле «client_ref» больше не существует",
        location: { relation_id: "r1" },
      },
    ];
    return HttpResponse.json({ can_publish: false, issues });
  }),

  http.post(`${API}/apps/:appId/publish`, ({ params }) => {
    const app = apps.find((a) => a.id === params.appId);
    if (!app) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    app.is_published = true;
    app.updated_at = new Date().toISOString();
    return HttpResponse.json(app);
  }),

  http.post(`${API}/apps/:appId/unpublish`, ({ params }) => {
    const app = apps.find((a) => a.id === params.appId);
    if (!app) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    app.is_published = false;
    app.updated_at = new Date().toISOString();
    return HttpResponse.json(app);
  }),

  http.post(`${API}/apps`, async ({ request }) => {
    const body = (await request.json()) as { slug: string; name: string; description?: string | null };
    const created = makeApp({ slug: body.slug, name: body.name, description: body.description ?? null });
    apps.push(created);
    return HttpResponse.json(created, { status: 201 });
  }),

  http.get(`${API}/modules`, ({ request }) => {
    const url = new URL(request.url);
    return HttpResponse.json(modulesForApp(url.searchParams.get("app_id")));
  }),

  http.get(`${API}/apps/:appId/modules`, ({ params }) => {
    const appId = params.appId as string;
    const installed = installedModulesByApp[appId] ?? new Set<string>();
    return HttpResponse.json(
      modulesForApp(appId)
        .filter((m) => installed.has(m.code))
        .map((m) => ({
          app_id: appId,
          module_id: m.id,
          module_code: m.code,
          module_name: m.name,
          version: m.current_version,
          status: "installed",
          installed_at: new Date().toISOString(),
          installed_by: MOCK_USER.id,
        })),
    );
  }),

  http.post(`${API}/apps/:appId/modules/:moduleCode/install`, ({ params }) => {
    const appId = params.appId as string;
    const moduleCode = params.moduleCode as string;
    const module = moduleCatalog.find((m) => m.code === moduleCode);
    if (!module) return HttpResponse.json({ detail: "Module not found" }, { status: 404 });
    const installed = installedModulesByApp[appId] ?? new Set<string>();
    installedModulesByApp[appId] = installed;
    module.dependencies.forEach((dep) => installed.add(dep));
    installed.add(module.code);
    const alreadyInstalled = module.dependencies.filter((dep) => installed.has(dep));
    const result: ModuleInstallResult = {
      module: { ...module, installed: true, installed_version: module.current_version },
      installed_dependencies: module.dependencies,
      entities_created: 2,
      fields_created: alreadyInstalled.length > 0 ? 4 : 6,
      pages_created: 1,
      conflicts: alreadyInstalled.flatMap((dep) => [
        { kind: "entity" as const, name: `${dep}_link`, entity: null, source: dep, action: "reused" as const },
      ]),
    };
    return HttpResponse.json(result);
  }),

  http.delete(`${API}/apps/:appId/modules/:moduleCode`, ({ params }) => {
    const appId = params.appId as string;
    const moduleCode = params.moduleCode as string;
    installedModulesByApp[appId]?.delete(moduleCode);
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${API}/apps/:appId/templates/:templateId/install`, ({ params }) => {
    const appId = params.appId as string;
    const templateModules: Record<string, string[]> = {
      trading_company: ["enterprise", "warehouse", "orders", "finance", "analytics"],
      manufacturing_company: ["enterprise", "warehouse", "production", "finance", "analytics"],
      service_company: ["enterprise", "projects", "contracts", "finance", "it_support"],
      hr_department: ["enterprise", "hr", "projects"],
      document_flow: ["enterprise", "documents", "contracts"],
      financial_accounting: ["enterprise", "finance", "analytics"],
      empty: [],
    };
    const modules = templateModules[params.templateId as string] ?? [];
    const installed = installedModulesByApp[appId] ?? new Set<string>();
    installedModulesByApp[appId] = installed;
    modules.forEach((m) => installed.add(m));
    return HttpResponse.json({
      modules_installed: [...installed],
      entities_created: modules.length * 2,
      fields_created: modules.length * 6,
      pages_created: modules.length,
    });
  }),

  // Rules (bots)
  http.get(`${API}/apps/:appId/rules`, () => HttpResponse.json(rules)),

  http.get(`${API}/apps/:appId/rules/conflicts`, () => HttpResponse.json(mockRuleConflicts)),

  http.get(`${API}/apps/:appId/rules/webhook-deliveries`, () => HttpResponse.json(mockRuleWebhookDeliveries)),

  http.patch(`${API}/apps/:appId/rules/:ruleId`, async ({ params, request }) => {
    const idx = rules.findIndex((r) => r.id === params.ruleId);
    if (idx === -1) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const body = (await request.json()) as Partial<Rule>;
    rules[idx] = { ...rules[idx], ...body, updated_at: new Date().toISOString() };
    return HttpResponse.json(rules[idx]);
  }),

  http.delete(`${API}/apps/:appId/rules/:ruleId`, ({ params }) => {
    const idx = rules.findIndex((r) => r.id === params.ruleId);
    if (idx !== -1) rules.splice(idx, 1);
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${API}/apps/:appId/rules/:ruleId/activate`, ({ params }) => {
    const rule = rules.find((r) => r.id === params.ruleId);
    if (!rule) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    rule.is_active = true;
    rule.updated_at = new Date().toISOString();
    return HttpResponse.json(rule);
  }),

  http.post(`${API}/apps/:appId/rules/:ruleId/deactivate`, ({ params }) => {
    const rule = rules.find((r) => r.id === params.ruleId);
    if (!rule) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    rule.is_active = false;
    rule.updated_at = new Date().toISOString();
    return HttpResponse.json(rule);
  }),

  // Users
  http.get(`${API}/users`, ({ request }) => {
    const url = new URL(request.url);
    const search = url.searchParams.get("search")?.toLowerCase() ?? "";
    const isActive = url.searchParams.get("is_active");
    let result = [...mockUsers];
    if (search) result = result.filter(
      (u) => u.display_name.toLowerCase().includes(search) || u.email.toLowerCase().includes(search)
    );
    if (isActive !== null) result = result.filter((u) => u.is_active === (isActive === "true"));
    const page: CursorPage<User> = { items: result, next_cursor: null, has_more: false, total: result.length };
    return HttpResponse.json(page);
  }),

  http.get(`${API}/users/roles`, () => HttpResponse.json(MOCK_ROLES)),

  http.get(`${API}/users/:userId`, ({ params }) => {
    const user = mockUsers.find((u) => u.id === params.userId);
    if (!user) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    return HttpResponse.json(user);
  }),

  http.patch(`${API}/users/:userId`, async ({ params, request }) => {
    const idx = mockUsers.findIndex((u) => u.id === params.userId);
    if (idx === -1) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const body = (await request.json()) as Partial<User>;
    mockUsers[idx] = { ...mockUsers[idx], ...body, updated_at: new Date().toISOString() };
    return HttpResponse.json(mockUsers[idx]);
  }),

  http.delete(`${API}/users/:userId`, ({ params }) => {
    const idx = mockUsers.findIndex((u) => u.id === params.userId);
    if (idx !== -1) mockUsers[idx].is_active = false;
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${API}/users/:userId/set-password`, async ({ params, request }) => {
    const user = mockUsers.find((u) => u.id === params.userId);
    if (!user) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const body = (await request.json()) as { new_password: string };
    if (!body.new_password || body.new_password.length < 8) {
      return HttpResponse.json({ detail: "Минимум 8 символов" }, { status: 422 });
    }
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${API}/users/invite`, async ({ request }) => {
    const body = (await request.json()) as { email: string; display_name?: string; roles?: string[] };
    const existing = mockUsers.find((u) => u.email === body.email);
    if (existing) return HttpResponse.json(existing);
    const now = new Date().toISOString();
    const newUser: User = {
      id: crypto.randomUUID(),
      email: body.email,
      display_name: body.display_name ?? body.email,
      is_active: true,
      is_superuser: false,
      is_blocked: false,
      totp_enabled: false,
      last_login_at: null,
      created_at: now,
      updated_at: now,
      roles: [],
    };
    mockUsers.push(newUser);
    return HttpResponse.json(newUser, { status: 201 });
  }),

  // Invite links
  http.get(`${API}/apps/:appId/invite-links`, ({ params }) =>
    HttpResponse.json(mockInviteLinks.filter((l) => l.app_id === params.appId && !l.revoked).map(({ token: _t, revoked: _r, ...l }) => l)),
  ),
  http.post(`${API}/apps/:appId/invite-links`, async ({ params, request }) => {
    const body = (await request.json()) as { role?: string; expires_in_days?: number | null; max_uses?: number | null };
    const days = body.expires_in_days === undefined ? 7 : body.expires_in_days;
    const link = {
      id: crypto.randomUUID(),
      app_id: params.appId as string,
      role: body.role ?? "editor",
      allow_signup: true,
      max_uses: body.max_uses ?? null,
      use_count: 0,
      expires_at: days ? new Date(Date.now() + days * 86400000).toISOString() : null,
      created_at: new Date().toISOString(),
      token: crypto.randomUUID().replace(/-/g, ""),
      revoked: false,
    };
    mockInviteLinks.push(link);
    const { revoked: _r, ...out } = link;
    return HttpResponse.json(out, { status: 201 });
  }),
  http.delete(`${API}/apps/:appId/invite-links/:linkId`, ({ params }) => {
    const l = mockInviteLinks.find((x) => x.id === params.linkId);
    if (l) l.revoked = true;
    return new HttpResponse(null, { status: 204 });
  }),
  http.get(`${API}/invites/:token`, ({ params }) => {
    const l = mockInviteLinks.find((x) => x.token === params.token && !x.revoked);
    if (!l) return HttpResponse.json({ detail: "Invite link is invalid or expired" }, { status: 410 });
    return HttpResponse.json({ app_id: l.app_id, app_name: "Демо-приложение", role: l.role, allow_signup: l.allow_signup, expires_at: l.expires_at });
  }),
  http.post(`${API}/invites/:token/accept`, ({ params }) => {
    const l = mockInviteLinks.find((x) => x.token === params.token && !x.revoked);
    if (!l) return HttpResponse.json({ detail: "Invite link is invalid or expired" }, { status: 410 });
    l.use_count += 1;
    return HttpResponse.json({ app_id: l.app_id, role: l.role, already_member: false });
  }),
  http.post(`${API}/invites/:token/signup`, ({ params }) => {
    const l = mockInviteLinks.find((x) => x.token === params.token && !x.revoked);
    if (!l) return HttpResponse.json({ detail: "Invite link is invalid or expired" }, { status: 410 });
    l.use_count += 1;
    return HttpResponse.json({ access_token: "mock-access", refresh_token: "mock-refresh", expires_in: 900 }, { status: 201 });
  }),

  // Entities
  http.get(`${API}/apps/:appId/entities`, ({ params }) => {
    const appId = params.appId as string;
    if (!entitiesByApp[appId]) entitiesByApp[appId] = buildEntities(appId);
    return HttpResponse.json(entitiesByApp[appId]);
  }),

  http.post(`${API}/apps/:appId/entities`, async ({ params, request }) => {
    const appId = params.appId as string;
    if (!entitiesByApp[appId]) entitiesByApp[appId] = buildEntities(appId);
    const body = (await request.json()) as { slug: string; display_name: string; [k: string]: unknown };
    const now = new Date().toISOString();
    const entity: EntityRead = {
      id: crypto.randomUUID(), app_id: appId,
      slug: body.slug, display_name: body.display_name,
      name_plural: null, description: null, icon: null, color: null,
      settings: {}, is_system: false, field_order: [], fields: [],
      created_at: now, updated_at: now,
    };
    entitiesByApp[appId].push(entity);
    return HttpResponse.json(entity, { status: 201 });
  }),

  http.patch(`${API}/apps/:appId/entities/:entityId`, async ({ params, request }) => {
    const appId = params.appId as string;
    if (!entitiesByApp[appId]) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const idx = entitiesByApp[appId].findIndex((e) => e.id === params.entityId);
    if (idx === -1) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const body = (await request.json()) as Partial<EntityRead>;
    entitiesByApp[appId][idx] = { ...entitiesByApp[appId][idx], ...body, updated_at: new Date().toISOString() };
    return HttpResponse.json(entitiesByApp[appId][idx]);
  }),

  http.delete(`${API}/apps/:appId/entities/:entityId`, ({ params }) => {
    const appId = params.appId as string;
    if (entitiesByApp[appId]) {
      const idx = entitiesByApp[appId].findIndex((e) => e.id === params.entityId);
      if (idx !== -1) entitiesByApp[appId].splice(idx, 1);
    }
    return new HttpResponse(null, { status: 204 });
  }),

  // Fields
  http.post(`${API}/apps/:appId/entities/:entityId/fields`, async ({ params, request }) => {
    const appId = params.appId as string;
    if (!entitiesByApp[appId]) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const entity = entitiesByApp[appId].find((e) => e.id === params.entityId);
    if (!entity) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const body = (await request.json()) as { name: string; display_name: string; field_type: string; [k: string]: unknown };
    const now = new Date().toISOString();
    const field: FieldRead = {
      id: crypto.randomUUID(), entity_id: entity.id, app_id: appId,
      name: body.name, display_name: body.display_name,
      field_type: body.field_type as FieldRead["field_type"],
      is_required: false, is_unique: false, is_system: false, is_indexed: false,
      is_sensitive: Boolean(body.is_sensitive),
      default_value: null, validation_rules: {}, field_options: {}, formula_definition: null,
      display_order: entity.fields.length,
      created_at: now, updated_at: now,
    };
    entity.fields.push(field);
    return HttpResponse.json(field, { status: 201 });
  }),

  http.patch(`${API}/apps/:appId/entities/:entityId/fields/:fieldId`, async ({ params, request }) => {
    const appId = params.appId as string;
    if (!entitiesByApp[appId]) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const entity = entitiesByApp[appId].find((e) => e.id === params.entityId);
    if (!entity) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const idx = entity.fields.findIndex((f) => f.id === params.fieldId);
    if (idx === -1) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const body = (await request.json()) as Partial<FieldRead>;
    entity.fields[idx] = { ...entity.fields[idx], ...body, updated_at: new Date().toISOString() };
    return HttpResponse.json(entity.fields[idx]);
  }),

  http.delete(`${API}/apps/:appId/entities/:entityId/fields/:fieldId`, ({ params }) => {
    const appId = params.appId as string;
    if (entitiesByApp[appId]) {
      const entity = entitiesByApp[appId].find((e) => e.id === params.entityId);
      if (entity) {
        const idx = entity.fields.findIndex((f) => f.id === params.fieldId);
        if (idx !== -1) entity.fields.splice(idx, 1);
      }
    }
    return new HttpResponse(null, { status: 204 });
  }),

  // Rules create
  http.post(`${API}/apps/:appId/rules`, async ({ params, request }) => {
    const appId = params.appId as string;
    const body = (await request.json()) as {
      name: string; entity_id: string; rule_type?: "automation" | "autofill" | "validation";
      trigger: { event: string; watch_fields?: string[] }; description?: string | null; priority?: number;
      conditions?: Record<string, unknown>; actions?: Record<string, unknown>[];
    };
    const now = new Date().toISOString();
    const rule: Rule = {
      id: crypto.randomUUID(),
      app_id: appId,
      entity_id: body.entity_id,
      name: body.name,
      description: body.description ?? null,
      is_active: false,
      rule_type: body.rule_type ?? "automation",
      trigger: { event: body.trigger.event, watch_fields: body.trigger.watch_fields ?? [] },
      conditions: body.conditions ?? {},
      actions: body.actions ?? [],
      priority: body.priority ?? 100,
      version: 1,
      created_by: MOCK_USER.id,
      created_at: now,
      updated_at: now,
    };
    rules.push(rule);
    return HttpResponse.json(rule, { status: 201 });
  }),

  // Records
  http.get(`${API}/apps/:appId/entities/:entityId/records`, ({ params }) => {
    const entityId = params.entityId as string;
    const items = mockRecords.filter((r) => r.entity_id === entityId);
    const page: CursorPage<RecordRead> = { items, next_cursor: null, has_more: false, total: items.length };
    return HttpResponse.json(page);
  }),

  http.post(`${API}/apps/:appId/entities/:entityId/records`, async ({ params, request }) => {
    const entityId = params.entityId as string;
    const body = (await request.json()) as { payload: Record<string, unknown> };
    const now = new Date().toISOString();
    const record: RecordRead = {
      id: crypto.randomUUID(), entity_id: entityId, payload: body.payload,
      version: 1, is_deleted: false, deleted_at: null, deleted_by: null,
      created_by: MOCK_USER.id, updated_by: null,
      created_at: now, updated_at: now,
    };
    mockRecords.push(record);
    return HttpResponse.json(record, { status: 201 });
  }),

  http.patch(`${API}/apps/:appId/entities/:entityId/records/:recordId`, async ({ params, request }) => {
    const idx = mockRecords.findIndex((r) => r.id === params.recordId);
    if (idx === -1) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const body = (await request.json()) as { payload: Record<string, unknown> };
    mockRecords[idx] = { ...mockRecords[idx], payload: body.payload, updated_at: new Date().toISOString() };
    return HttpResponse.json(mockRecords[idx]);
  }),

  http.delete(`${API}/apps/:appId/entities/:entityId/records/:recordId`, ({ params }) => {
    const idx = mockRecords.findIndex((r) => r.id === params.recordId);
    if (idx === -1) return new HttpResponse(null, { status: 204 });
    const [record] = mockRecords.splice(idx, 1);
    const entity = buildEntities(params.appId as string).find((e) => e.id === params.entityId);
    mockTrash.push({
      id: record.id,
      entity_id: params.entityId as string,
      entity_slug: entity?.slug ?? "unknown",
      entity_display_name: entity?.display_name ?? "Unknown",
      payload: record.payload,
      is_cascade_deleted: false,
      deleted_at: new Date().toISOString(),
      deleted_by: MOCK_USER.id,
    });
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${API}/apps/:appId/entities/:entityId/records/:recordId/restore`, ({ params }) => {
    const idx = mockTrash.findIndex((r) => r.id === params.recordId);
    if (idx === -1) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const [trashed] = mockTrash.splice(idx, 1);
    const now = new Date().toISOString();
    const restored: RecordRead = {
      id: trashed.id, entity_id: trashed.entity_id, payload: trashed.payload,
      version: 1, is_deleted: false, deleted_at: null, deleted_by: null,
      created_by: MOCK_USER.id, updated_by: null, created_at: now, updated_at: now,
    };
    mockRecords.push(restored);
    return HttpResponse.json(restored);
  }),

  http.get(`${API}/apps/:appId/recycle-bin`, ({ request }) => {
    const entityId = new URL(request.url).searchParams.get("entity_id");
    const items = entityId ? mockTrash.filter((r) => r.entity_id === entityId) : mockTrash;
    const page: CursorPage<TrashedRecordRead> = { items, next_cursor: null, has_more: false, total: items.length };
    return HttpResponse.json(page);
  }),

  // Views
  http.get(`${API}/apps/:appId/entities/:entityId/views`, ({ params }) => {
    const appId = params.appId as string;
    const entityId = params.entityId as string;
    const key = viewsKey(appId, entityId);
    if (!viewsByApp[key]) viewsByApp[key] = buildViews(appId, entityId);
    return HttpResponse.json(viewsByApp[key]);
  }),

  http.post(`${API}/apps/:appId/entities/:entityId/views`, async ({ params, request }) => {
    const appId = params.appId as string;
    const entityId = params.entityId as string;
    const key = viewsKey(appId, entityId);
    if (!viewsByApp[key]) viewsByApp[key] = buildViews(appId, entityId);
    const body = (await request.json()) as { name: string; view_type: string; config?: Record<string, unknown>; is_public?: boolean };
    const now = new Date().toISOString();
    const view: ViewRead = {
      id: crypto.randomUUID(), app_id: appId, entity_id: entityId,
      name: body.name, view_type: body.view_type as ViewRead["view_type"],
      config: body.config ?? {}, is_default: false, is_public: body.is_public ?? false,
      created_by: MOCK_USER.id, created_at: now, updated_at: now,
    };
    viewsByApp[key].push(view);
    return HttpResponse.json(view, { status: 201 });
  }),

  http.patch(`${API}/apps/:appId/entities/:entityId/views/:viewId`, async ({ params, request }) => {
    const appId = params.appId as string;
    const entityId = params.entityId as string;
    const key = viewsKey(appId, entityId);
    if (!viewsByApp[key]) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const idx = viewsByApp[key].findIndex((v) => v.id === params.viewId);
    if (idx === -1) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const body = (await request.json()) as Partial<ViewRead>;
    viewsByApp[key][idx] = { ...viewsByApp[key][idx], ...body, updated_at: new Date().toISOString() };
    return HttpResponse.json(viewsByApp[key][idx]);
  }),

  http.delete(`${API}/apps/:appId/entities/:entityId/views/:viewId`, ({ params }) => {
    const appId = params.appId as string;
    const entityId = params.entityId as string;
    const key = viewsKey(appId, entityId);
    if (viewsByApp[key]) {
      const idx = viewsByApp[key].findIndex((v) => v.id === params.viewId);
      if (idx !== -1) viewsByApp[key].splice(idx, 1);
    }
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${API}/apps/:appId/entities/:entityId/views/:viewId/set_default`, ({ params }) => {
    const appId = params.appId as string;
    const entityId = params.entityId as string;
    const key = viewsKey(appId, entityId);
    if (!viewsByApp[key]) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    viewsByApp[key].forEach((v) => { v.is_default = v.id === params.viewId; });
    const view = viewsByApp[key].find((v) => v.id === params.viewId);
    if (!view) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    return HttpResponse.json(view);
  }),

  // Pages
  http.get(`${API}/apps/:appId/pages`, ({ params }) => {
    const appId = params.appId as string;
    if (!pagesByApp[appId]) pagesByApp[appId] = buildPages(appId);
    const sorted = [...pagesByApp[appId]].sort((a, b) => a.nav_order - b.nav_order);
    return HttpResponse.json(sorted);
  }),

  http.post(`${API}/apps/:appId/pages`, async ({ params, request }) => {
    const appId = params.appId as string;
    if (!pagesByApp[appId]) pagesByApp[appId] = buildPages(appId);
    const body = (await request.json()) as { slug: string; title: string; icon?: string | null; nav_order?: number; layout?: Record<string, unknown>; blocks?: Record<string, unknown>[] };
    const now = new Date().toISOString();
    const page: PageRead = {
      id: crypto.randomUUID(), app_id: appId, slug: body.slug, title: body.title,
      icon: body.icon ?? null, nav_order: body.nav_order ?? pagesByApp[appId].length,
      layout: body.layout ?? {}, blocks: body.blocks ?? [], breakpoints: {},
      is_published: false, published_at: null, created_at: now, updated_at: now,
    };
    pagesByApp[appId].push(page);
    return HttpResponse.json(page, { status: 201 });
  }),

  http.patch(`${API}/apps/:appId/pages/:pageId`, async ({ params, request }) => {
    const appId = params.appId as string;
    if (!pagesByApp[appId]) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const idx = pagesByApp[appId].findIndex((p) => p.id === params.pageId);
    if (idx === -1) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const body = (await request.json()) as Partial<PageRead>;
    pagesByApp[appId][idx] = { ...pagesByApp[appId][idx], ...body, updated_at: new Date().toISOString() };
    return HttpResponse.json(pagesByApp[appId][idx]);
  }),

  http.delete(`${API}/apps/:appId/pages/:pageId`, ({ params }) => {
    const appId = params.appId as string;
    if (pagesByApp[appId]) {
      const idx = pagesByApp[appId].findIndex((p) => p.id === params.pageId);
      if (idx !== -1) pagesByApp[appId].splice(idx, 1);
    }
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${API}/apps/:appId/pages/:pageId/publish`, ({ params }) => {
    const appId = params.appId as string;
    if (!pagesByApp[appId]) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const page = pagesByApp[appId].find((p) => p.id === params.pageId);
    if (!page) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    page.is_published = true;
    page.published_at = new Date().toISOString();
    return HttpResponse.json(page);
  }),

  http.post(`${API}/apps/:appId/pages/:pageId/unpublish`, ({ params }) => {
    const appId = params.appId as string;
    if (!pagesByApp[appId]) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const page = pagesByApp[appId].find((p) => p.id === params.pageId);
    if (!page) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    page.is_published = false;
    page.published_at = null;
    return HttpResponse.json(page);
  }),

  // Workflows
  http.get(`${API}/apps/:appId/workflows`, ({ params, request }) => {
    const appId = params.appId as string;
    if (!workflowsByApp[appId]) workflowsByApp[appId] = buildWorkflows(appId);
    const url = new URL(request.url);
    const entityId = url.searchParams.get("entity_id");
    const result = entityId
      ? workflowsByApp[appId].filter((w) => w.entity_id === entityId)
      : workflowsByApp[appId];
    return HttpResponse.json(result);
  }),

  http.post(`${API}/apps/:appId/workflows`, async ({ params, request }) => {
    const appId = params.appId as string;
    if (!workflowsByApp[appId]) workflowsByApp[appId] = buildWorkflows(appId);
    const body = (await request.json()) as { entity_id: string; name: string; description?: string | null; initial_state: string };
    const now = new Date().toISOString();
    const wfId = crypto.randomUUID();
    const wf: WorkflowDefRead = {
      id: wfId, app_id: appId, entity_id: body.entity_id, name: body.name,
      description: body.description ?? null, initial_state: body.initial_state,
      is_active: false, version: 1, created_at: now, updated_at: now,
    };
    workflowsByApp[appId].push(wf);
    statesByWorkflow[wfId] = [];
    return HttpResponse.json(wf, { status: 201 });
  }),

  http.patch(`${API}/apps/:appId/workflows/:workflowId`, async ({ params, request }) => {
    const appId = params.appId as string;
    if (!workflowsByApp[appId]) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const idx = workflowsByApp[appId].findIndex((w) => w.id === params.workflowId);
    if (idx === -1) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const body = (await request.json()) as Partial<WorkflowDefRead>;
    workflowsByApp[appId][idx] = { ...workflowsByApp[appId][idx], ...body, updated_at: new Date().toISOString() };
    return HttpResponse.json(workflowsByApp[appId][idx]);
  }),

  http.delete(`${API}/apps/:appId/workflows/:workflowId`, ({ params }) => {
    const appId = params.appId as string;
    if (workflowsByApp[appId]) {
      const idx = workflowsByApp[appId].findIndex((w) => w.id === params.workflowId);
      if (idx !== -1) workflowsByApp[appId].splice(idx, 1);
    }
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${API}/apps/:appId/workflows/:workflowId/activate`, ({ params }) => {
    const appId = params.appId as string;
    if (!workflowsByApp[appId]) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const wf = workflowsByApp[appId].find((w) => w.id === params.workflowId);
    if (!wf) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    wf.is_active = true;
    wf.updated_at = new Date().toISOString();
    return HttpResponse.json(wf);
  }),

  http.post(`${API}/apps/:appId/workflows/:workflowId/deactivate`, ({ params }) => {
    const appId = params.appId as string;
    if (!workflowsByApp[appId]) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const wf = workflowsByApp[appId].find((w) => w.id === params.workflowId);
    if (!wf) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    wf.is_active = false;
    wf.updated_at = new Date().toISOString();
    return HttpResponse.json(wf);
  }),

  http.get(`${API}/apps/:appId/workflows/:workflowId/states`, ({ params }) => {
    const workflowId = params.workflowId as string;
    return HttpResponse.json(statesByWorkflow[workflowId] ?? []);
  }),

  http.post(`${API}/apps/:appId/workflows/:workflowId/states`, async ({ params, request }) => {
    const workflowId = params.workflowId as string;
    if (!statesByWorkflow[workflowId]) statesByWorkflow[workflowId] = [];
    const body = (await request.json()) as { name: string; display_name: string; is_terminal?: boolean; color?: string | null; sla_seconds?: number | null; assignee_type?: string | null; assignee_id?: string | null; approval_chain_id?: string | null };
    const state: StateDefRead = {
      id: crypto.randomUUID(), workflow_id: workflowId,
      name: body.name, display_name: body.display_name,
      is_terminal: body.is_terminal ?? false, color: body.color ?? null,
      sla_seconds: body.sla_seconds ?? null,
      on_enter_actions: [], on_exit_actions: [], sla_breach_actions: [], escalation_levels: [],
      assignee_type: (body.assignee_type as StateDefRead["assignee_type"]) ?? null,
      assignee_id: body.assignee_id ?? null,
      approval_chain_id: body.approval_chain_id ?? null,
    };
    statesByWorkflow[workflowId].push(state);
    return HttpResponse.json(state, { status: 201 });
  }),

  http.patch(`${API}/apps/:appId/workflows/:workflowId/states/:stateId`, async ({ params, request }) => {
    const workflowId = params.workflowId as string;
    if (!statesByWorkflow[workflowId]) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const idx = statesByWorkflow[workflowId].findIndex((s) => s.id === params.stateId);
    if (idx === -1) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const body = (await request.json()) as Partial<StateDefRead>;
    statesByWorkflow[workflowId][idx] = { ...statesByWorkflow[workflowId][idx], ...body };
    return HttpResponse.json(statesByWorkflow[workflowId][idx]);
  }),

  http.patch(`${API}/apps/:appId/workflows/:workflowId/instances/:instanceId/assign`, async ({ request }) => {
    const body = (await request.json()) as { assigned_user_id?: string | null; assigned_group_id?: string | null };
    const now = new Date().toISOString();
    return HttpResponse.json({
      id: crypto.randomUUID(),
      workflow_id: "mock", app_id: "mock", entity_id: "mock", record_id: "mock",
      current_state: "new", version: 1, sla_deadline: null,
      started_at: now, completed_at: null,
      assigned_user_id: body.assigned_user_id ?? null,
      assigned_group_id: body.assigned_group_id ?? null,
    });
  }),

  http.delete(`${API}/apps/:appId/workflows/:workflowId/states/:stateId`, ({ params }) => {
    const workflowId = params.workflowId as string;
    if (statesByWorkflow[workflowId]) {
      const idx = statesByWorkflow[workflowId].findIndex((s) => s.id === params.stateId);
      if (idx !== -1) statesByWorkflow[workflowId].splice(idx, 1);
    }
    return new HttpResponse(null, { status: 204 });
  }),

  // Approval chain definitions
  http.get(`${API}/apps/:appId/workflows/:workflowId/approval-chains`, ({ params }) => {
    const workflowId = params.workflowId as string;
    return HttpResponse.json(chainsByWorkflow[workflowId] ?? []);
  }),

  http.post(`${API}/apps/:appId/workflows/:workflowId/approval-chains`, async ({ params, request }) => {
    const workflowId = params.workflowId as string;
    if (!chainsByWorkflow[workflowId]) chainsByWorkflow[workflowId] = [];
    const body = (await request.json()) as { name: string; description?: string | null; on_approve_transition?: string | null; on_reject_transition?: string | null; levels?: { level_order: number; display_name: string; assignee_type?: string | null; assignee_id?: string | null }[] };
    const chainId = crypto.randomUUID();
    const chain: ApprovalChainDefRead = {
      id: chainId, workflow_id: workflowId,
      name: body.name, description: body.description ?? null,
      on_approve_transition: body.on_approve_transition ?? null,
      on_reject_transition: body.on_reject_transition ?? null,
      levels: (body.levels ?? []).map((l) => ({ id: crypto.randomUUID(), chain_id: chainId, level_order: l.level_order, display_name: l.display_name, assignee_type: (l.assignee_type as ApprovalChainDefRead["levels"][0]["assignee_type"]) ?? null, assignee_id: l.assignee_id ?? null })),
      created_at: new Date().toISOString(),
    };
    chainsByWorkflow[workflowId].push(chain);
    return HttpResponse.json(chain, { status: 201 });
  }),

  http.patch(`${API}/apps/:appId/workflows/:workflowId/approval-chains/:chainId`, async ({ params, request }) => {
    const workflowId = params.workflowId as string;
    if (!chainsByWorkflow[workflowId]) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const idx = chainsByWorkflow[workflowId].findIndex((c) => c.id === params.chainId);
    if (idx === -1) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const body = (await request.json()) as Partial<ApprovalChainDefRead & { levels?: { level_order: number; display_name: string; assignee_type?: string | null; assignee_id?: string | null }[] }>;
    const existing = chainsByWorkflow[workflowId][idx];
    const chainId = existing.id;
    const updated: ApprovalChainDefRead = {
      ...existing,
      name: body.name ?? existing.name,
      description: body.description !== undefined ? body.description : existing.description,
      on_approve_transition: body.on_approve_transition !== undefined ? body.on_approve_transition : existing.on_approve_transition,
      on_reject_transition: body.on_reject_transition !== undefined ? body.on_reject_transition : existing.on_reject_transition,
      levels: body.levels ? body.levels.map((l) => ({ id: crypto.randomUUID(), chain_id: chainId, level_order: l.level_order, display_name: l.display_name, assignee_type: (l.assignee_type as ApprovalChainDefRead["levels"][0]["assignee_type"]) ?? null, assignee_id: l.assignee_id ?? null })) : existing.levels,
    };
    chainsByWorkflow[workflowId][idx] = updated;
    return HttpResponse.json(updated);
  }),

  http.delete(`${API}/apps/:appId/workflows/:workflowId/approval-chains/:chainId`, ({ params }) => {
    const workflowId = params.workflowId as string;
    if (chainsByWorkflow[workflowId]) {
      const idx = chainsByWorkflow[workflowId].findIndex((c) => c.id === params.chainId);
      if (idx !== -1) chainsByWorkflow[workflowId].splice(idx, 1);
    }
    return new HttpResponse(null, { status: 204 });
  }),

  // Approval chain instances (runtime)
  http.get(`${API}/apps/:appId/workflows/:workflowId/instances/:instanceId/approval-chains`, ({ params }) => {
    const instanceId = params.instanceId as string;
    return HttpResponse.json(chainInstancesByWfInstance[instanceId] ?? []);
  }),

  http.post(`${API}/apps/:appId/workflows/:workflowId/instances/:instanceId/approval-chains/:chainInstanceId/decide`, async ({ params, request }) => {
    const instanceId = params.instanceId as string;
    const chainInstanceId = params.chainInstanceId as string;
    const body = (await request.json()) as { decision: "approved" | "rejected"; comment?: string | null };
    const instances = chainInstancesByWfInstance[instanceId] ?? [];
    const ci = instances.find((c) => c.id === chainInstanceId);
    if (!ci) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const response = { id: crypto.randomUUID(), chain_instance_id: chainInstanceId, level_order: ci.current_level, actor_id: null, decision: body.decision, comment: body.comment ?? null, decided_at: new Date().toISOString() };
    const updatedResponses = [...ci.responses, response];
    const updated: ApprovalChainInstanceRead = {
      ...ci,
      responses: updatedResponses,
      status: body.decision === "rejected" ? "rejected" : (ci.current_level >= 3 ? "approved" : "pending"),
      current_level: body.decision === "approved" && ci.current_level < 3 ? ci.current_level + 1 : ci.current_level,
      completed_at: body.decision === "rejected" || ci.current_level >= 3 ? new Date().toISOString() : null,
    };
    const idx = instances.findIndex((c) => c.id === chainInstanceId);
    if (idx !== -1) instances[idx] = updated;
    chainInstancesByWfInstance[instanceId] = instances;
    return HttpResponse.json(updated);
  }),

  // Webhooks
  http.get(`${API}/apps/:appId/webhooks`, ({ params }) => {
    const appId = params.appId as string;
    if (!webhooksByApp[appId]) webhooksByApp[appId] = buildWebhooks(appId);
    return HttpResponse.json(webhooksByApp[appId]);
  }),

  http.post(`${API}/apps/:appId/webhooks`, async ({ params, request }) => {
    const appId = params.appId as string;
    if (!webhooksByApp[appId]) webhooksByApp[appId] = buildWebhooks(appId);
    const body = (await request.json()) as { name: string; target_url: string; events?: string[]; custom_headers?: Record<string, string>; timeout_seconds?: number; max_retries?: number };
    const now = new Date().toISOString();
    const webhook: WebhookRead & { secret: string } = {
      id: crypto.randomUUID(), app_id: appId, name: body.name,
      target_url: body.target_url, events: body.events ?? [],
      is_active: true, custom_headers: body.custom_headers ?? {},
      timeout_seconds: body.timeout_seconds ?? 30, max_retries: body.max_retries ?? 3,
      created_at: now, updated_at: now,
      secret: crypto.randomUUID(),
    };
    webhooksByApp[appId].push(webhook);
    return HttpResponse.json(webhook, { status: 201 });
  }),

  http.patch(`${API}/apps/:appId/webhooks/:subId`, async ({ params, request }) => {
    const appId = params.appId as string;
    if (!webhooksByApp[appId]) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const idx = webhooksByApp[appId].findIndex((w) => w.id === params.subId);
    if (idx === -1) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    const body = (await request.json()) as Partial<WebhookRead>;
    webhooksByApp[appId][idx] = { ...webhooksByApp[appId][idx], ...body, updated_at: new Date().toISOString() };
    return HttpResponse.json(webhooksByApp[appId][idx]);
  }),

  http.delete(`${API}/apps/:appId/webhooks/:subId`, ({ params }) => {
    const appId = params.appId as string;
    if (webhooksByApp[appId]) {
      const idx = webhooksByApp[appId].findIndex((w) => w.id === params.subId);
      if (idx !== -1) webhooksByApp[appId].splice(idx, 1);
    }
    return new HttpResponse(null, { status: 204 });
  }),

  // ── Email Templates ──────────────────────────────────────────────────
  ...(() => {
    const now = new Date().toISOString();
    const mkTpl = (
      code: string, name: string, description: string,
      subject: string, body_html: string, body_text: string,
      variables: EmailTemplateRead["variables"],
    ): EmailTemplateRead => ({
      id: crypto.randomUUID(),
      code, name, description,
      subject, body_html, body_text,
      variables,
      is_system: true,
      created_at: now,
      updated_at: now,
    });

    const emailTemplates: EmailTemplateRead[] = [
      mkTpl(
        "password_reset", "Сброс пароля", "Отправляется при запросе сброса пароля",
        "Сброс пароля в {{ platform_name | default('Lesovik') }}",
        "<p>Здравствуйте, <b>{{ display_name }}</b>!</p><p><a href=\"{{ reset_url }}\">Сбросить пароль</a></p><p style=\"color:#888;font-size:13px\">Ссылка действительна 1 час.</p>",
        "Здравствуйте, {{ display_name }}!\n\nСсылка для сброса: {{ reset_url }}\n\nСсылка действительна 1 час.",
        [
          { name: "display_name", type: "string", description: "Имя пользователя", example: "Иван Иванов" },
          { name: "reset_url", type: "string", description: "Ссылка для сброса", example: "https://example.com/reset?token=xxx" },
          { name: "platform_name", type: "string", description: "Название платформы", example: "Lesovik" },
        ],
      ),
      mkTpl(
        "invitation", "Приглашение на платформу", "Отправляется при создании нового пользователя",
        "Приглашение в {{ platform_name | default('Lesovik') }}",
        "<p>Здравствуйте, <b>{{ display_name }}</b>!</p><p><b>Email:</b> {{ email }}<br><b>Пароль:</b> <code>{{ temp_password }}</code></p><p><a href=\"{{ platform_url }}\">Войти</a></p>",
        "Здравствуйте, {{ display_name }}!\nEmail: {{ email }}\nПароль: {{ temp_password }}\nВойти: {{ platform_url }}",
        [
          { name: "display_name", type: "string", description: "Имя пользователя", example: "Иван Иванов" },
          { name: "email", type: "string", description: "Email", example: "user@example.com" },
          { name: "temp_password", type: "string", description: "Временный пароль", example: "TmpPass123" },
          { name: "platform_url", type: "string", description: "Ссылка на платформу", example: "https://example.com/editor" },
        ],
      ),
      mkTpl(
        "sla_breach", "Нарушение SLA", "Отправляется при нарушении дедлайна заявки",
        "SLA нарушен: {{ state_name }}",
        "<p>Дедлайн истёк.</p><p><b>Заявка:</b> {{ instance_id }}<br><b>Статус:</b> {{ state_name }}<br><b>Дедлайн:</b> {{ deadline }}</p>",
        "SLA нарушен!\nЗаявка: {{ instance_id }}\nСтатус: {{ state_name }}\nДедлайн: {{ deadline }}",
        [
          { name: "instance_id", type: "string", description: "ID заявки", example: "abc-123" },
          { name: "state_name", type: "string", description: "Текущий статус", example: "На проверке" },
          { name: "deadline", type: "string", description: "Дедлайн", example: "2026-07-10T12:00:00Z" },
        ],
      ),
      mkTpl(
        "sla_escalation", "Эскалация SLA", "Отправляется при эскалации на новый уровень",
        "Эскалация уровня {{ escalation_level }}: {{ state_name }}",
        "<p>Эскалация на уровень <b>{{ escalation_level }}</b>.</p><p><b>Заявка:</b> {{ instance_id }}<br><b>Статус:</b> {{ state_name }}</p>",
        "Эскалация уровня {{ escalation_level }}!\nЗаявка: {{ instance_id }}\nСтатус: {{ state_name }}",
        [
          { name: "instance_id", type: "string", description: "ID заявки", example: "abc-123" },
          { name: "state_name", type: "string", description: "Статус", example: "На проверке" },
          { name: "escalation_level", type: "integer", description: "Уровень (1 или 2)", example: "1" },
        ],
      ),
      mkTpl(
        "workflow_notification", "Уведомление о заявке", "Общее уведомление при изменении статуса",
        "{{ subject | default('Изменение статуса заявки') }}",
        "<p>{{ message | default('Статус вашей заявки изменился.') }}</p><p><b>Заявка:</b> {{ instance_id }}<br><b>Событие:</b> {{ event }}</p>",
        "{{ message | default('Статус изменился.') }}\nЗаявка: {{ instance_id }}\nСобытие: {{ event }}",
        [
          { name: "instance_id", type: "string", description: "ID заявки", example: "abc-123" },
          { name: "event", type: "string", description: "Тип события", example: "transition" },
          { name: "state_name", type: "string", description: "Новый статус", example: "Одобрено" },
          { name: "subject", type: "string", description: "Тема (опционально)", example: "Ваша заявка одобрена" },
          { name: "message", type: "string", description: "Сообщение (опционально)", example: "Заявка успешно одобрена" },
        ],
      ),
    ];

    return [
      http.get(`${API}/email-templates`, () => HttpResponse.json(emailTemplates)),

      http.post(`${API}/email-templates`, async ({ request }) => {
        const body = (await request.json()) as Partial<EmailTemplateRead>;
        const tpl: EmailTemplateRead = {
          id: crypto.randomUUID(),
          code: body.code ?? "new_template",
          name: body.name ?? "Новый шаблон",
          description: body.description ?? null,
          subject: body.subject ?? "",
          body_html: body.body_html ?? "",
          body_text: body.body_text ?? null,
          variables: body.variables ?? [],
          is_system: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        emailTemplates.push(tpl);
        return HttpResponse.json(tpl, { status: 201 });
      }),

      http.patch(`${API}/email-templates/:id`, async ({ params, request }) => {
        const tpl = emailTemplates.find((t) => t.id === params.id);
        if (!tpl) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
        const body = (await request.json()) as Partial<EmailTemplateRead>;
        if (body.name !== undefined) tpl.name = body.name;
        if (body.subject !== undefined) tpl.subject = body.subject;
        if (body.body_html !== undefined) tpl.body_html = body.body_html;
        if ("body_text" in body) tpl.body_text = body.body_text ?? null;
        if (body.description !== undefined) tpl.description = body.description ?? null;
        if (body.variables !== undefined) tpl.variables = body.variables;
        tpl.updated_at = new Date().toISOString();
        return HttpResponse.json(tpl);
      }),

      http.delete(`${API}/email-templates/:id`, ({ params }) => {
        const idx = emailTemplates.findIndex((t) => t.id === params.id);
        if (idx === -1) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
        if (emailTemplates[idx].is_system) return HttpResponse.json({ detail: "System templates cannot be deleted" }, { status: 403 });
        emailTemplates.splice(idx, 1);
        return new HttpResponse(null, { status: 204 });
      }),

      http.post(`${API}/email-templates/:id/preview`, async ({ params, request }) => {
        const tpl = emailTemplates.find((t) => t.id === params.id);
        if (!tpl) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
        const body = (await request.json()) as { context?: Record<string, unknown> };
        const ctx = body.context ?? {};
        // Simple variable substitution for mock preview
        function renderSimple(tmpl: string): string {
          return tmpl.replace(/\{\{\s*([\w.]+)(?:\s*\|\s*default\(['"]([^'"]*)['"]\))?\s*\}\}/g,
            (_, name, fallback) => String(ctx[name] ?? fallback ?? `{{${name}}}`));
        }
        return HttpResponse.json({
          subject: renderSimple(tpl.subject),
          body_html: renderSimple(tpl.body_html),
          body_text: tpl.body_text ? renderSimple(tpl.body_text) : null,
        });
      }),
    ];
  })(),

  // ---- Knowledge base (ТЗ 3.12) ----
  ...(() => {
    interface MockArticle {
      id: string; slug: string; title: string; category: string | null;
      content: string; is_published: boolean; created_by: string | null;
      created_at: string; updated_at: string;
    }
    const articles: MockArticle[] = [
      {
        id: "kb-1", slug: "kak-sozdat-pravilo", title: "Как создать правило",
        category: "Правила",
        content: "<p>Откройте раздел <b>Автоматизация</b> и нажмите «Добавить правило».</p>",
        is_published: true, created_by: MOCK_USER.id,
        created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "kb-2", slug: "import-dannyh", title: "Импорт данных из Excel",
        category: "Импорт",
        content: "<p>Загрузите файл CSV или XLSX и сопоставьте колонки с полями таблицы.</p>",
        is_published: true, created_by: MOCK_USER.id,
        created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "kb-3", slug: "s-chego-nachat", title: "С чего начать работу с приложением",
        category: "Обучение",
        content: "<p>Создайте таблицы в разделе <b>Данные</b>, соберите страницы в <b>Конструкторе</b> и опубликуйте приложение.</p>",
        is_published: true, created_by: MOCK_USER.id,
        created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
      },
    ];
    const excerpt = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 200);

    return [
      http.get(`${API}/kb/articles`, ({ request }) => {
        const url = new URL(request.url);
        const category = url.searchParams.get("category");
        const q = url.searchParams.get("q")?.toLowerCase();
        let items = articles.filter((a) => a.is_published);
        if (category) items = items.filter((a) => a.category === category);
        if (q) items = items.filter((a) => a.title.toLowerCase().includes(q) || a.content.toLowerCase().includes(q));
        return HttpResponse.json(items.map((a) => ({
          id: a.id, slug: a.slug, title: a.title, category: a.category,
          excerpt: excerpt(a.content), is_published: a.is_published, updated_at: a.updated_at,
        })));
      }),

      http.get(`${API}/kb/categories`, () => {
        const cats = [...new Set(articles.filter((a) => a.is_published && a.category).map((a) => a.category!))].sort();
        return HttpResponse.json(cats);
      }),

      http.get(`${API}/kb/articles/:idOrSlug`, ({ params }) => {
        const key = params.idOrSlug as string;
        const article = articles.find((a) => a.id === key || a.slug === key);
        if (!article) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
        return HttpResponse.json(article);
      }),

      http.post(`${API}/kb/articles`, async ({ request }) => {
        const body = (await request.json()) as Partial<MockArticle>;
        const now = new Date().toISOString();
        const article: MockArticle = {
          id: crypto.randomUUID(),
          slug: body.slug || `article-${Math.random().toString(36).slice(2, 8)}`,
          title: body.title ?? "",
          category: body.category ?? null,
          content: body.content ?? "",
          is_published: body.is_published ?? true,
          created_by: MOCK_USER.id,
          created_at: now, updated_at: now,
        };
        articles.push(article);
        return HttpResponse.json(article, { status: 201 });
      }),

      http.patch(`${API}/kb/articles/:idOrSlug`, async ({ params, request }) => {
        const key = params.idOrSlug as string;
        const idx = articles.findIndex((a) => a.id === key || a.slug === key);
        if (idx === -1) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
        const body = (await request.json()) as Partial<MockArticle>;
        articles[idx] = { ...articles[idx], ...body, updated_at: new Date().toISOString() };
        return HttpResponse.json(articles[idx]);
      }),

      http.delete(`${API}/kb/articles/:idOrSlug`, ({ params }) => {
        const key = params.idOrSlug as string;
        const idx = articles.findIndex((a) => a.id === key || a.slug === key);
        if (idx !== -1) articles.splice(idx, 1);
        return new HttpResponse(null, { status: 204 });
      }),

      http.post(`${API}/kb/images`, () => HttpResponse.json({
        id: crypto.randomUUID(),
        url: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='120'%3E%3Crect width='200' height='120' fill='%23EBF4FF'/%3E%3Ctext x='50%25' y='50%25' text-anchor='middle' fill='%230066FF'%3E(mock image)%3C/text%3E%3C/svg%3E",
      }, { status: 201 })),
    ];
  })(),

  // ---- Document registrar + номенклатура дел (ТЗ 3.10) ----
  ...(() => {
    interface MockDocTypeConfig {
      doc_type: string; prefix: string; suffix: string;
      include_department: boolean; seq_padding: number; reset_period: string;
    }
    interface MockFilingCase {
      id: string; parent_id: string | null; index_code: string; title: string;
      retention_years: number | null; storage_location: string | null;
      status: string; close_by: string | null; closed_at: string | null;
      responsible_user_id: string | null; created_at: string;
    }
    interface MockRegistration {
      id: string; entity_id: string; record_id: string; doc_type: string;
      department_code: string | null; registration_no: string;
      filing_case_id: string | null; registered_by: string | null; registered_at: string;
    }

    const docTypeConfigs: Record<string, MockDocTypeConfig> = {
      incoming: { doc_type: "incoming", prefix: "ВХ-", suffix: "", include_department: false, seq_padding: 4, reset_period: "yearly" },
      outgoing: { doc_type: "outgoing", prefix: "ИСХ-", suffix: "", include_department: false, seq_padding: 4, reset_period: "yearly" },
      internal: { doc_type: "internal", prefix: "ВН-", suffix: "", include_department: false, seq_padding: 4, reset_period: "yearly" },
    };
    const filingCases: MockFilingCase[] = [
      {
        id: "case-1", parent_id: null, index_code: "01", title: "Приказы по основной деятельности",
        retention_years: 5, storage_location: null, status: "open", close_by: null, closed_at: null,
        responsible_user_id: null, created_at: "2026-01-01T00:00:00Z",
      },
    ];
    const registrations: MockRegistration[] = [];
    const counters: Record<string, number> = {};

    return [
      http.get(`${API}/apps/:appId/documents/doc-types`, () => HttpResponse.json(Object.values(docTypeConfigs))),

      http.put(`${API}/apps/:appId/documents/doc-types/:docType`, async ({ params, request }) => {
        const docType = params.docType as string;
        const body = (await request.json()) as Partial<MockDocTypeConfig>;
        docTypeConfigs[docType] = { ...docTypeConfigs[docType], ...body };
        return HttpResponse.json(docTypeConfigs[docType]);
      }),

      http.post(`${API}/apps/:appId/documents/register`, async ({ request }) => {
        const body = (await request.json()) as {
          entity_id: string; record_id: string; doc_type: string;
          department_code?: string | null; filing_case_id?: string | null;
        };
        const config = docTypeConfigs[body.doc_type];
        const dept = config.include_department ? (body.department_code || "") : "";
        const key = `${body.doc_type}:${dept}`;
        const seq = (counters[key] ?? 0) + 1;
        counters[key] = seq;
        const year = new Date().getFullYear();
        const parts = [config.prefix];
        if (dept) parts.push(`${dept}-`);
        if (config.reset_period !== "never") parts.push(String(year), "-");
        parts.push(String(seq).padStart(config.seq_padding, "0"), config.suffix);

        const reg: MockRegistration = {
          id: crypto.randomUUID(), entity_id: body.entity_id, record_id: body.record_id,
          doc_type: body.doc_type, department_code: body.department_code ?? null,
          registration_no: parts.join(""), filing_case_id: body.filing_case_id ?? null,
          registered_by: MOCK_USER.id, registered_at: new Date().toISOString(),
        };
        registrations.unshift(reg);
        return HttpResponse.json(reg, { status: 201 });
      }),

      http.get(`${API}/apps/:appId/documents/registrations`, ({ request }) => {
        const docType = new URL(request.url).searchParams.get("doc_type");
        const items = docType ? registrations.filter((r) => r.doc_type === docType) : registrations;
        return HttpResponse.json(items);
      }),

      http.get(`${API}/apps/:appId/documents/filing-cases`, () => HttpResponse.json(filingCases)),

      http.post(`${API}/apps/:appId/documents/filing-cases`, async ({ request }) => {
        const body = (await request.json()) as Partial<MockFilingCase>;
        const now = new Date().toISOString();
        const created: MockFilingCase = {
          id: crypto.randomUUID(), parent_id: body.parent_id ?? null,
          index_code: body.index_code ?? "", title: body.title ?? "",
          retention_years: body.retention_years ?? null, storage_location: body.storage_location ?? null,
          status: "open", close_by: body.close_by ?? null, closed_at: null,
          responsible_user_id: body.responsible_user_id ?? null, created_at: now,
        };
        filingCases.push(created);
        return HttpResponse.json(created, { status: 201 });
      }),

      http.patch(`${API}/apps/:appId/documents/filing-cases/:caseId`, async ({ params, request }) => {
        const idx = filingCases.findIndex((c) => c.id === params.caseId);
        if (idx === -1) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
        const body = (await request.json()) as Partial<MockFilingCase>;
        filingCases[idx] = {
          ...filingCases[idx], ...body,
          closed_at: body.status === "closed" && !filingCases[idx].closed_at ? new Date().toISOString() : filingCases[idx].closed_at,
        };
        return HttpResponse.json(filingCases[idx]);
      }),

      http.delete(`${API}/apps/:appId/documents/filing-cases/:caseId`, ({ params }) => {
        const idx = filingCases.findIndex((c) => c.id === params.caseId);
        if (idx !== -1) filingCases.splice(idx, 1);
        return new HttpResponse(null, { status: 204 });
      }),

      http.get(`${API}/apps/:appId/documents/filing-cases/export`, () => {
        const csv = "index_code,title,status\n" + filingCases.map((c) => `${c.index_code},${c.title},${c.status}`).join("\n");
        return new HttpResponse(csv, { headers: { "Content-Type": "text/csv" } });
      }),
    ];
  })(),
];
