import { useEffect, useRef, useState } from "react";
import {
  DndContext, closestCenter, PointerSensor, useSensor, useSensors, type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext, useSortable, verticalListSortingStrategy, arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Navbar } from "@/components/layout/Navbar";
import { IconRail, type RailModule } from "@/components/layout/IconRail";
import { ViewNavPanel, type NavSection, type SystemNavGroup } from "@/components/layout/ViewNavPanel";
import { TabSwitcher } from "@/components/ui/TabSwitcher";
import { cn } from "@/lib/cn";
import { useApps } from "@/shared/hooks/useApps";
import { useActiveApp } from "@/shared/hooks/useActiveApp";
import { usePages, useUpdatePage, useCreatePage, useDeletePage, usePublishPage, useUnpublishPage, useReorderPages, usePagePermissions, useSetPagePermissions, useViews, useCreateView, useDeleteView, useSetDefaultView, useViewFieldConfigs, useReplaceFieldConfigs } from "@/shared/hooks/useViews";
import type { ViewFieldConfigItem } from "@/shared/api/views";
import type { ViewRead } from "@/shared/api/views";
import { useAllRoles } from "@/shared/hooks/useRbac";
import { useEntities } from "@/shared/hooks/useEntities";
import type { FieldRead } from "@/shared/api/entities";
import { useCreateRecord } from "@/shared/hooks/useRecords";
import { SortingModal, GroupingModal, DensityModal, TableViewsModal, NewActionModal } from "@/components/modals/ViewModals";

/* ── View types ── */
type ViewType =
  | "calendar" | "deck" | "table" | "gallery" | "details" | "map"
  | "chart" | "dashboard" | "form" | "onboarding" | "card";

const VIEW_TYPES: { id: ViewType; label: string; icon: React.ReactNode }[] = [
  { id: "calendar",   label: "Календарь", icon: <CalendarIcon /> },
  { id: "deck",       label: "Колода",    icon: <DeckIcon /> },
  { id: "table",      label: "Таблица",   icon: <TableIcon /> },
  { id: "gallery",    label: "Галерея",   icon: <GridIcon /> },
  { id: "details",    label: "Детали",    icon: <DetailsIcon /> },
  { id: "map",        label: "Карта",     icon: <MapIcon /> },
  { id: "chart",      label: "Диаграмма", icon: <ChartIcon /> },
  { id: "dashboard",  label: "Дашборд",   icon: <DashboardIcon /> },
  { id: "form",       label: "Форма",     icon: <FormIcon /> },
  { id: "onboarding", label: "Онбординг", icon: <GridIcon /> },
  { id: "card",       label: "Карточка",  icon: <CardIcon /> },
];

const POSITIONS = ["первый", "следующий", "средний", "последующий", "последний", "меню", "ссылка"];

const EDITOR_TABS = ["Представления", "Правила формирования", "Дизайн", "Поля"];

type PageBlockType =
  // Input
  | "text_field" | "number_field" | "date_field" | "dropdown" | "toggle" | "checkbox"
  | "file_upload" | "lookup" | "responsible" | "form" | "positions_picker"
  // Display
  | "table" | "record_card" | "metric" | "kpi" | "chart" | "pivot"
  | "calendar" | "kanban" | "gantt" | "tree" | "rich_text" | "view"
  // Action
  | "button" | "import" | "export"
  // Container
  | "modal" | "tabs" | "filter_panel" | "divider" | "iframe";

interface PageBlock {
  id: string;
  type: PageBlockType;
  title: string | null;
  config: Record<string, unknown>;
}

interface PositionsPickerExtra {
  entity_id: string;
  display_field: string;
  label: string;
  field: string;
}

interface RuleCond {
  id: string;
  field: string;
  op: "eq" | "ne" | "gt" | "lt" | "contains" | "empty" | "not_empty";
  value: string;
}

interface DesignConfig {
  accent?: string;
  theme?: "light" | "dark";
  density?: "compact" | "normal" | "spacious";
  show_header?: boolean;
  font_family?: string;
  heading_size?: string;
  body_size?: string;
  input_style?: "outline" | "filled" | "minimal";
  label_position?: "top" | "inline";
  nav_position?: "top" | "bottom" | "burger";
}

const FONT_FAMILIES = ["Inter", "Roboto", "Open Sans", "Montserrat", "Lato", "Playfair Display", "JetBrains Mono"];
const FONT_SIZES    = ["11", "12", "13", "14", "15", "16", "18", "20", "24", "28", "32", "40", "48"];

const OP_LABELS: Record<RuleCond["op"], string> = {
  eq: "равно",
  ne: "не равно",
  gt: "больше",
  lt: "меньше",
  contains: "содержит",
  empty: "пусто",
  not_empty: "не пусто",
};

const ACCENT_COLORS = ["#35A7FF", "#00205F", "#22C55E", "#F59E0B", "#EF4444", "#8B5CF6"];

const BLOCK_TYPE_META: Record<PageBlockType, { label: string; desc?: string; group: string }> = {
  // Input
  text_field:   { label: "Текстовое поле",    desc: "Строка, маска, валидация",             group: "Ввод" },
  number_field: { label: "Числовое поле",     desc: "Число, валюта, единица измерения",     group: "Ввод" },
  date_field:   { label: "Дата / Период",     desc: "Выбор даты или диапазона",             group: "Ввод" },
  dropdown:     { label: "Выпадающий список", desc: "Статичный или динамический источник",  group: "Ввод" },
  toggle:       { label: "Переключатель",     desc: "Булево значение Да / Нет",             group: "Ввод" },
  checkbox:     { label: "Чекбокс",          desc: "Галочка для булевого поля",            group: "Ввод" },
  file_upload:  { label: "Загрузка файла",    desc: "Файлы с контролем формата и размера",  group: "Ввод" },
  lookup:       { label: "Справочник",        desc: "Ссылка на запись другой сущности",     group: "Ввод" },
  responsible:  { label: "Ответственный",     desc: "Список с автоподстановкой текущего пользователя", group: "Ввод" },
  form:             { label: "Форма ввода",       desc: "Группа полей для создания/редактирования записи", group: "Ввод" },
  positions_picker: { label: "Выбор позиций",    desc: "Таблица позиций из каталога (товары, услуги)",    group: "Ввод" },
  // Display
  table:        { label: "Таблица",           desc: "Список записей с сортировкой и фильтром",         group: "Отображение" },
  record_card:  { label: "Карточка записи",   desc: "Детальное отображение одной записи",  group: "Отображение" },
  metric:       { label: "Метрика",           desc: "Числовой показатель",                 group: "Отображение" },
  kpi:          { label: "KPI",              desc: "Показатель с трендом",                group: "Отображение" },
  chart:        { label: "Диаграмма",         desc: "Bar, Line, Pie, Area, Waterfall",     group: "Отображение" },
  pivot:        { label: "Сводная таблица",   desc: "Агрегация по строкам и столбцам",     group: "Отображение" },
  calendar:     { label: "Календарь",         desc: "События на оси времени",              group: "Отображение" },
  kanban:       { label: "Kanban-доска",      desc: "Карточки по статусу",                 group: "Отображение" },
  gantt:        { label: "Gantt-диаграмма",   desc: "Задачи на оси времени",               group: "Отображение" },
  tree:         { label: "Дерево данных",     desc: "Иерархическое отображение",           group: "Отображение" },
  rich_text:    { label: "Текст",             desc: "Форматированный текст",               group: "Отображение" },
  view:         { label: "Представление",     desc: "Встроенное представление",            group: "Отображение" },
  // Action
  button:       { label: "Кнопка",            desc: "Сохранение, переход, расчёт",         group: "Действие" },
  import:       { label: "Блок импорта",      desc: "Загрузка данных из файла с маппингом", group: "Действие" },
  export:       { label: "Блок экспорта",     desc: "Выгрузка в Excel, CSV, PDF",          group: "Действие" },
  // Container
  modal:        { label: "Модальное окно",    desc: "Всплывающий диалог с блоками",        group: "Контейнер" },
  tabs:         { label: "Вкладки",           desc: "Группировка содержимого",             group: "Контейнер" },
  filter_panel: { label: "Панель фильтров",   desc: "Набор условий для фильтрации",        group: "Контейнер" },
  divider:      { label: "Разделитель",       desc: "Горизонтальная линия",                group: "Контейнер" },
  iframe:       { label: "Фрейм",             desc: "Встроенная веб-страница",             group: "Контейнер" },
};

const BLOCK_GROUPS: { id: string; label: string; types: PageBlockType[] }[] = [
  {
    id: "input", label: "Ввод",
    types: ["text_field", "number_field", "date_field", "dropdown", "toggle", "checkbox", "file_upload", "lookup", "responsible", "form", "positions_picker"],
  },
  {
    id: "display", label: "Отображение",
    types: ["table", "record_card", "metric", "kpi", "chart", "pivot", "calendar", "kanban", "gantt", "tree", "rich_text"],
  },
  {
    id: "action", label: "Действие",
    types: ["button", "import", "export"],
  },
  {
    id: "container", label: "Контейнер",
    types: ["modal", "tabs", "filter_panel", "divider", "iframe"],
  },
];


function defaultBlockConfig(type: PageBlockType): Record<string, unknown> {
  if (type === "rich_text")    return { text: "Текстовый блок" };
  if (type === "metric")       return { value: "0", width: "third" };
  if (type === "kpi")          return { value: "0", trend: "+0%", tone: "positive", width: "half" };
  if (type === "chart")        return { chart_type: "bar", source: "records" };
  if (type === "calendar")     return { date_field: "", title_field: "" };
  if (type === "kanban")       return { group_by: "", card_title: "" };
  if (type === "iframe")       return { src: "" };
  if (type === "button")       return { width: "half", actionType: "url", href: "", label: "Кнопка" };
  // Input blocks
  if (type === "text_field")   return { label: "Текстовое поле", field_name: "", placeholder: "", mask: "", required: false, validation: "" };
  if (type === "number_field") return { label: "Число", field_name: "", format: "number", currency: "RUB", unit: "", min: "", max: "", required: false };
  if (type === "date_field")   return { label: "Дата", field_name: "", mode: "single", date_format: "DD.MM.YYYY", required: false, default_today: false };
  if (type === "dropdown")     return { label: "Список", field_name: "", source: "static", options: "Вариант 1\nВариант 2", multiple: false, entity_id: "", display_field: "" };
  if (type === "toggle")       return { label: "Вкл/Выкл", field_name: "", default_value: false };
  if (type === "checkbox")     return { label: "Чекбокс", field_name: "", default_value: false };
  if (type === "file_upload")  return { label: "Файл", field_name: "", accept: "*", max_size_mb: 10, multiple: false, max_files: 50 };
  if (type === "lookup")           return { label: "Справочник", field_name: "", entity_id: "", display_field: "", multiple: false };
  if (type === "responsible")      return { label: "Ответственный", field_name: "", entity_id: "", display_field: "", match_field: "" };
  if (type === "positions_picker") return { label: "Позиции заказа", catalog_entity_id: "", catalog_display_field: "nazvanie", catalog_price_field: "cena", catalog_unit_field: "edinica", extras: [], positions_entity_id: "", parent_field: "", item_field: "", qty_field: "kolichestvo", row_total_field: "", total_field: "" };
  // Display
  if (type === "record_card")  return { entity_id: "", fields: [] };
  if (type === "pivot")        return { entity_id: "", row_field: "", col_field: "", value_field: "", agg: "count" };
  if (type === "gantt")        return { entity_id: "", start_field: "", end_field: "", title_field: "" };
  if (type === "tree")         return { entity_id: "", parent_field: "", label_field: "" };
  // Action
  if (type === "import")       return { entity_id: "", accept: ".xlsx,.csv", has_header: true };
  if (type === "export")       return { entity_id: "", format: "csv", filename: "" };
  // Container
  if (type === "modal")        return { title: "Диалог", trigger_label: "Открыть", trigger_variant: "primary", content: "" };
  if (type === "tabs")         return { tabs: [{ id: "tab1", label: "Вкладка 1", content: "" }, { id: "tab2", label: "Вкладка 2", content: "" }] };
  if (type === "filter_panel") return { entity_id: "", fields: [], position: "top" };
  return {};
}

/**
 * Generate a unique id. `crypto.randomUUID` only exists in secure contexts
 * (HTTPS / localhost); the app is served over plain HTTP, where it is
 * undefined and throws. Fall back to a timestamp+random string.
 */
function genId(): string {
  const c = globalThis.crypto as Crypto | undefined;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function ViewEditorPage() {
  const [railModule, setRailModule] = useState<RailModule>("constructor");
  const [activeView, setActiveView] = useState<string>("");
  const [editorTab, setEditorTab] = useState("Представления");

  const [showSortModal, setShowSortModal] = useState(false);
  const [showGroupModal, setShowGroupModal] = useState(false);
  const [showDensityModal, setShowDensityModal] = useState(false);
  const [showViewsModal, setShowViewsModal] = useState(false);
  const [showActionModal, setShowActionModal] = useState(false);

  const [navCollapsed, setNavCollapsed] = useState(false);
  const [quickAddEntityId, setQuickAddEntityId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [entityDdOpen, setEntityDdOpen] = useState(false);
  const [paramsOpen, setParamsOpen] = useState(true);
  const [blocksOpen, setBlocksOpen] = useState(true);
  const [blocks, setBlocks] = useState<PageBlock[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  // All view settings live in page.layout (JSONB) so everything persists.
  const [layout, setLayout] = useState<Record<string, unknown>>({});
  // Keep a ref so patchLayout always reads the latest layout even if called
  // from a callback that captured a stale closure.
  const layoutRef = useRef<Record<string, unknown>>({});
  useEffect(() => { layoutRef.current = layout; }, [layout]);

  const blocksRef = useRef<PageBlock[]>([]);
  const undoStackRef = useRef<{ blocks: PageBlock[]; layout: Record<string, unknown> }[]>([]);
  const redoStackRef = useRef<{ blocks: PageBlock[]; layout: Record<string, unknown> }[]>([]);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  const viewType = (layout.view_type as ViewType) ?? "table";
  const selectedEntityId = (layout.entity_id as string) ?? "";
  const position = (layout.position as string) ?? "первый";

  const iframeRef = useRef<HTMLIFrameElement>(null);

  const appsQuery = useApps();
  const apps = appsQuery.data?.items ?? [];
  const app = useActiveApp(apps);
  const appId = app?.id;

  const [permissionsPageId, setPermissionsPageId] = useState<string | null>(null);

  const pagesQuery = usePages(appId);
  const pages = pagesQuery.data ?? [];
  const updatePageMutation = useUpdatePage(appId ?? "");
  const createPageMutation = useCreatePage(appId ?? "");
  const deletePageMutation = useDeletePage(appId ?? "");
  const publishPageMutation = usePublishPage(appId ?? "");
  const unpublishPageMutation = useUnpublishPage(appId ?? "");
  const reorderPagesMutation = useReorderPages(appId ?? "");
  const setPagePermissionsMutation = useSetPagePermissions(appId ?? "");
  const allRolesQuery = useAllRoles();
  const allRoles = allRolesQuery.data ?? [];
  const pagePermsQuery = usePagePermissions(appId, permissionsPageId ?? undefined);

  const { data: entities = [] } = useEntities(appId);
  const createRecordMutation = useCreateRecord(appId ?? "", quickAddEntityId ?? "");

  const activePage = pages.find((p) => p.id === activeView) ?? null;

  // Set initial active view when pages load (prefer user pages)
  useEffect(() => {
    if (pages.length > 0 && !activeView) {
      const first = pages.find((p) => !p.layout?.is_system) ?? pages[0];
      setActiveView(first.id);
    }
  }, [pages, activeView]);

  // Sync active page into iframe without reloading it
  useEffect(() => {
    if (activeView && iframeRef.current?.contentWindow) {
      iframeRef.current.contentWindow.postMessage(
        { type: "RT_NAVIGATE", pageId: activeView },
        window.location.origin,
      );
    }
  }, [activeView]);

  // Sync local state from active page.
  // Deps include activePage?.id so that if the page data arrives after
  // activeView is set (e.g. right after creating a new page), the effect
  // re-runs and loads the correct (empty) blocks instead of leaving stale ones.
  useEffect(() => {
    // Always clear first so stale content never bleeds into the next page.
    setBlocks([]);
    setLayout({});
    setName("");
    blocksRef.current = [];
    layoutRef.current = {};
    undoStackRef.current = [];
    redoStackRef.current = [];
    setCanUndo(false);
    setCanRedo(false);
    if (!activePage) return;
    const loadedBlocks = (activePage.blocks ?? []) as unknown as PageBlock[];
    const loadedLayout = activePage.layout ?? {};
    setName(activePage.title);
    setBlocks(loadedBlocks);
    setLayout(loadedLayout);
    blocksRef.current = loadedBlocks;
    layoutRef.current = loadedLayout;
  }, [activeView, activePage?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const userPages   = pages.filter((p) => !p.layout?.is_system);
  const systemPages = pages.filter((p) =>  p.layout?.is_system);

  const navSections: NavSection[] = [
    {
      id: "main",
      title: "Навигация",
      views: userPages.map((p) => ({ id: p.id, label: p.title })),
    },
  ];

  // Group system pages by entity
  const systemGroups: SystemNavGroup[] = entities
    .map((entity) => {
      const views = systemPages
        .filter((p) => p.layout?.entity_id === entity.id)
        .map((p) => ({
          id: p.id,
          label: p.title,
          systemType: (p.layout?.system_type as "detail" | "form") ?? undefined,
        }));
      return { entityId: entity.id, entityName: entity.display_name, views };
    })
    .filter((g) => g.views.length > 0);

  // Warning: non-system pages with no blocks (excluding data-view pages, which
  // render automatically from layout.entity_id and don't need blocks) or
  // data-view pages missing their entity_id.
  const warningPages = pages.filter((p) => {
    const lay = (p.layout ?? {}) as Record<string, unknown>;
    if (lay.is_system) return false;
    const blks = (p.blocks ?? []) as unknown[];
    const isDataView = ["table", "calendar", "deck", "gallery", "gantt", "map"].includes(lay.view_type as string);
    if (isDataView) return !lay.entity_id;
    return blks.length === 0;
  });
  const warnings = warningPages.map((p) => {
    const lay = (p.layout ?? {}) as Record<string, unknown>;
    const blks = (p.blocks ?? []) as unknown[];
    const isDataView = ["table", "calendar", "deck", "gallery", "gantt", "map"].includes(lay.view_type as string);
    const name = p.title || "Без названия";
    if (isDataView && !lay.entity_id) return { pageId: p.id, message: `Представление «${name}» не настроено`, hint: "Выберите таблицу данных для этого представления" };
    if (blks.length === 0) return { pageId: p.id, message: `Страница «${name}» пустая`, hint: "Перейдите и добавьте хотя бы один блок" };
    return { pageId: p.id, message: `«${name}»`, hint: "" };
  });

  function _postRefetch(updatedLayout?: Record<string, unknown>) {
    const win = iframeRef.current?.contentWindow;
    if (!win) return;
    const origin = window.location.origin;
    if (activeView && updatedLayout) {
      win.postMessage({ type: "RT_PAGE_LAYOUT", pageId: activeView, layout: updatedLayout }, origin);
    }
    win.postMessage({ type: "RT_REFETCH" }, origin);
  }

  async function ensureSystemPages(entityId: string) {
    const entity = entities.find((e) => e.id === entityId);
    if (!entity || !appId) return;
    const hasDetail = pages.some(
      (p) => p.layout?.is_system && p.layout?.entity_id === entityId && p.layout?.system_type === "detail",
    );
    const hasForm = pages.some(
      (p) => p.layout?.is_system && p.layout?.entity_id === entityId && p.layout?.system_type === "form",
    );
    const hasInline = pages.some(
      (p) => p.layout?.is_system && p.layout?.entity_id === entityId && p.layout?.system_type === "inline",
    );
    const base = entity.display_name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "entity";
    if (!hasDetail) {
      await createPageMutation.mutateAsync({
        slug: `${base}-detail-sys-${Date.now().toString(36)}`,
        title: `${entity.display_name}_Detail`,
        layout: { is_system: true, system_type: "detail", entity_id: entityId, view_type: "detail" },
      });
    }
    if (!hasForm) {
      await createPageMutation.mutateAsync({
        slug: `${base}-form-sys-${Date.now().toString(36)}`,
        title: `${entity.display_name}_Form`,
        layout: { is_system: true, system_type: "form", entity_id: entityId, view_type: "form" },
      });
    }
    if (!hasInline) {
      await createPageMutation.mutateAsync({
        slug: `${base}-inline-sys-${Date.now().toString(36)}`,
        title: `${entity.display_name}_Inline`,
        layout: { is_system: true, system_type: "inline", entity_id: entityId, view_type: "table" },
      });
    }
    if (!hasDetail || !hasForm || !hasInline) _postRefetch();
  }

  function pushToHistory() {
    undoStackRef.current = [...undoStackRef.current.slice(-49), { blocks: blocksRef.current, layout: layoutRef.current }];
    redoStackRef.current = [];
    setCanUndo(true);
    setCanRedo(false);
  }

  // Merge a partial into page.layout and persist to backend.
  function patchLayout(partial: Record<string, unknown>) {
    pushToHistory();
    const next = { ...layoutRef.current, ...partial };
    setLayout(next);
    if (!activeView || !appId) return;
    const prevEntityId = layoutRef.current?.entity_id as string | undefined;
    updatePageMutation.mutate(
      { pageId: activeView, body: { layout: next } },
      { onSuccess: () => {
        _postRefetch(next);
        if (partial.entity_id && partial.entity_id !== prevEntityId) {
          void ensureSystemPages(partial.entity_id as string);
        }
      }},
    );
  }

  function handleNameBlur() {
    if (!activeView || !appId) return;
    updatePageMutation.mutate(
      { pageId: activeView, body: { title: name } },
      { onSuccess: () => _postRefetch() },
    );
  }

  function handleEntityChange(entityId: string) {
    setEntityDdOpen(false);
    // Reset column/sort config when the table changes — they reference fields.
    patchLayout({ entity_id: entityId, sort: [], group_by: [], hidden_columns: [] });
  }

  function handleViewTypeChange(vt: ViewType) {
    patchLayout({ view_type: vt });
  }

  function handleBlocksChange(newBlocks: PageBlock[]) {
    pushToHistory();
    setBlocks(newBlocks);
    blocksRef.current = newBlocks;
    if (!activeView || !appId) return;
    updatePageMutation.mutate(
      { pageId: activeView, body: { blocks: newBlocks as unknown as Record<string, unknown>[] } },
      { onSuccess: () => _postRefetch() },
    );
  }

  function handleUpdateBlock(blockId: string, patch: Partial<PageBlock>) {
    handleBlocksChange(blocks.map((block) => (
      block.id === blockId ? { ...block, ...patch } : block
    )));
  }

  function handleUndo() {
    const prev = undoStackRef.current.pop();
    if (!prev) return;
    redoStackRef.current.push({ blocks: blocksRef.current, layout: layoutRef.current });
    setBlocks(prev.blocks);
    blocksRef.current = prev.blocks;
    setLayout(prev.layout);
    layoutRef.current = prev.layout;
    setCanUndo(undoStackRef.current.length > 0);
    setCanRedo(true);
    if (activeView && appId) {
      updatePageMutation.mutate(
        { pageId: activeView, body: { blocks: prev.blocks as unknown as Record<string, unknown>[], layout: prev.layout } },
        { onSuccess: () => _postRefetch(prev.layout) },
      );
    }
  }

  function handleRedo() {
    const next = redoStackRef.current.pop();
    if (!next) return;
    undoStackRef.current.push({ blocks: blocksRef.current, layout: layoutRef.current });
    setBlocks(next.blocks);
    blocksRef.current = next.blocks;
    setLayout(next.layout);
    layoutRef.current = next.layout;
    setCanUndo(true);
    setCanRedo(redoStackRef.current.length > 0);
    if (activeView && appId) {
      updatePageMutation.mutate(
        { pageId: activeView, body: { blocks: next.blocks as unknown as Record<string, unknown>[], layout: next.layout } },
        { onSuccess: () => _postRefetch(next.layout) },
      );
    }
  }

  function handleUpdateBlockConfig(blockId: string, patch: Record<string, unknown>) {
    // Read from blocksRef, not the `blocks` state variable — two edits fired in
    // quick succession (e.g. changing two fields of the same extras[] entry)
    // can otherwise race: the second edit's closure still sees pre-first-edit
    // state, and its computed patch silently clobbers the first edit.
    handleBlocksChange(blocksRef.current.map((block) => (
      block.id === blockId ? { ...block, config: { ...block.config, ...patch } } : block
    )));
  }

  function handleAddBlock(type: PageBlockType) {
    const newBlock: PageBlock = {
      id: genId(),
      type,
      title: BLOCK_TYPE_META[type]?.label ?? type,
      config: defaultBlockConfig(type),
    };
    handleBlocksChange([...blocks, newBlock]);
  }

  function handleAddPage(_sectionId: string, viewType?: string) {
    if (!appId) return;
    const title = window.prompt("Название страницы:", "Новая страница");
    if (!title?.trim()) return;
    const base = title.trim().toLowerCase()
      .replace(/[а-яё]/gi, (c) => ({ а:"a",б:"b",в:"v",г:"g",д:"d",е:"e",ё:"yo",ж:"zh",з:"z",и:"i",й:"j",к:"k",л:"l",м:"m",н:"n",о:"o",п:"p",р:"r",с:"s",т:"t",у:"u",ф:"f",х:"h",ц:"ts",ч:"ch",ш:"sh",щ:"sch",ъ:"",ы:"y",ь:"",э:"e",ю:"yu",я:"ya" }[c.toLowerCase()] ?? c))
      .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "page";
    const layout = viewType ? { view_type: viewType === "grid" ? "table" : viewType } : undefined;
    createPageMutation.mutate(
      { slug: `${base}-${Date.now().toString(36)}`, title: title.trim(), ...(layout ? { layout } : {}) },
      { onSuccess: (page) => { setActiveView(page.id); _postRefetch(); } },
    );
  }

  function handleDeletePage(pageId: string) {
    if (!appId) return;
    if (!window.confirm("Удалить страницу?")) return;
    deletePageMutation.mutate(pageId, { onSuccess: () => _postRefetch() });
    if (activeView === pageId) {
      const next = pages.find((p) => p.id !== pageId);
      setActiveView(next?.id ?? "");
    }
  }

  const selectedEntity = entities.find((e) => e.id === selectedEntityId);
  const userFields = (selectedEntity?.fields ?? []).filter((f) => !f.is_system);
  const systemFields = (selectedEntity?.fields ?? []).filter((f) => f.is_system);

  // Entity-scoped saved views
  const viewsQuery = useViews(appId, selectedEntityId || undefined);
  const savedViews: ViewRead[] = viewsQuery.data ?? [];
  const createViewMutation = useCreateView(appId ?? "", selectedEntityId);
  const deleteViewMutation = useDeleteView(appId ?? "", selectedEntityId);
  const setDefaultViewMutation = useSetDefaultView(appId ?? "", selectedEntityId);
  const [saveViewName, setSaveViewName] = useState("");
  const [showSaveViewInput, setShowSaveViewInput] = useState(false);

  // Derived view settings (read from layout with defaults).
  const sortRules = (layout.sort as { field: string; dir: "asc" | "desc" }[]) ?? [];
  const hiddenColumns = (layout.hidden_columns as string[]) ?? [];
  const visibleSystemColumns = (layout.visible_system_columns as string[]) ?? [];
  const columnWidth = (layout.column_width as string) ?? "Средняя";
  const quickEdit = (layout.quick_edit as boolean) ?? true;
  const colMode = (layout.column_order_mode as "auto" | "manual") ?? "manual";
  const rules = (layout.rules as RuleCond[]) ?? [];
  const design = (layout.design as DesignConfig) ?? {};

  if (pagesQuery.isLoading || appsQuery.isLoading) {
    return (
      <div className="relative w-[1920px] h-[1080px] bg-white overflow-hidden flex items-center justify-center">
        <span className="text-[20px] text-primary">Загрузка...</span>
      </div>
    );
  }

  return (
    <div
      className="relative w-[1920px] h-[1080px] bg-white overflow-hidden"
      onClick={() => setEntityDdOpen(false)}
    >
      <Navbar
        onSave={activeView && appId ? () => updatePageMutation.mutate(
          { pageId: activeView, body: { title: name, layout, blocks: blocks as unknown as Record<string, unknown>[] } },
          { onSuccess: () => _postRefetch() },
        ) : undefined}
        onUndo={canUndo ? handleUndo : undefined}
        onRedo={canRedo ? handleRedo : undefined}
      />
      <IconRail active={railModule} onChange={setRailModule} onCollapse={() => setNavCollapsed((v) => !v)} collapsed={navCollapsed} />
      {!navCollapsed && (
        <ViewNavPanel
          sections={navSections}
          activeViewId={activeView}
          onSelect={setActiveView}
          onAddView={handleAddPage}
          onDeleteView={(id) => {
            const page = pages.find((p) => p.id === id);
            if (!page?.layout?.is_system) handleDeletePage(id);
          }}
          onDeleteSystemView={(id) => handleDeletePage(id)}
          onAddRecord={(entityId) => setQuickAddEntityId(entityId)}
          onReorderViews={(_sectionId, orderedIds) => {
            const reorderItems = orderedIds.map((id, idx) => ({ page_id: id, nav_order: idx }));
            reorderPagesMutation.mutate(reorderItems);
          }}
          onPagePermissions={(id) => setPermissionsPageId(id)}
          warnings={warnings}
          systemGroups={systemGroups}
        />
      )}

      {/* ── Top tab bar ── */}
      <div
        className="absolute bg-mainbg rounded-[5px] flex items-center justify-between px-[24px]"
        style={{ left: navCollapsed ? 90 : 380, top: 70, width: navCollapsed ? 1235 : 945, height: 55, transition: "left 0.2s, width 0.2s" }}
      >
        <div className="flex items-center gap-[18px] shrink-0 min-w-0">
          {EDITOR_TABS.map((t) => (
            <button
              key={t}
              onClick={() => setEditorTab(t)}
              className={cn(
                "text-[20px] leading-[150%] font-bold whitespace-nowrap transition-colors shrink-0",
                editorTab === t ? "text-cta" : "text-primary"
              )}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-[8px] shrink-0" style={{ height: 34 }}>
          <a
            href={appId ? `/app/?app=${appId}` : `/app/`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-[8px] px-4 py-[5px]
                       border-2 border-primary rounded-[20px] text-meta font-semibold text-primary
                       hover:bg-cardbg/40 transition-colors h-full whitespace-nowrap"
          >
            Предпросмотр
          </a>
          {activePage && (
            <button
              onClick={() => {
                if (!activeView) return;
                const isPublished = (activePage as { is_published?: boolean }).is_published;
                if (isPublished) {
                  unpublishPageMutation.mutate(activeView);
                } else {
                  publishPageMutation.mutate(activeView);
                }
              }}
              disabled={publishPageMutation.isPending || unpublishPageMutation.isPending}
              className={cn(
                "flex items-center justify-center gap-[8px] px-3 py-[5px] rounded-[20px] text-meta font-semibold transition-colors h-full border-2 disabled:opacity-60 whitespace-nowrap",
                (activePage as { is_published?: boolean }).is_published
                  ? "border-green-500 text-green-600 hover:bg-green-50"
                  : "border-cta text-cta hover:bg-[#EBF4FF]",
              )}
            >
              {(activePage as { is_published?: boolean }).is_published ? "Опубликовано" : "Опубликовать"}
            </button>
          )}
        </div>
      </div>

      {/* ── Editor scroll panel ── */}
      <div
        className="absolute bg-mainbg rounded-[5px] overflow-y-auto"
        style={{ left: navCollapsed ? 90 : 380, top: 130, width: navCollapsed ? 1235 : 945, height: 945, transition: "left 0.2s, width 0.2s" }}
      >
        {pages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-[20px]">
            <span className="text-[20px] text-primary/60">Нет страниц</span>
            <button
              onClick={() => handleAddPage("main")}
              className="px-6 h-[42px] bg-cta text-white rounded-btn text-[16px] font-medium hover:bg-active transition-colors"
            >
              + Создать первую страницу
            </button>
          </div>
        ) : !activePage ? (
          <div className="flex items-center justify-center h-full">
            <span className="text-[20px] text-primary/60">Выберите страницу</span>
          </div>
        ) : editorTab === "Правила формирования" ? (
          <RulesTab
            fields={userFields}
            rules={rules}
            onChange={(r) => patchLayout({ rules: r })}
          />
        ) : editorTab === "Дизайн" ? (
          <DesignTab
            design={design}
            onChange={(d) => patchLayout({ design: d })}
            onOpenDensityModal={() => setShowDensityModal(true)}
          />
        ) : editorTab === "Поля" ? (
          <ViewFieldsTab
            appId={appId ?? ""}
            entityId={selectedEntityId}
            savedViews={savedViews}
            userFields={userFields}
          />
        ) : (
          <div className="flex flex-col gap-[30px] pt-[53px] pb-[40px]">
            {/* Toolbar: добавить представление / действие */}
            <div className="flex items-center gap-[10px] px-[40px]">
              <button
                onClick={() => setShowViewsModal(true)}
                className="flex items-center gap-[6px] h-[34px] px-4 border-2 border-cta text-cta text-[13px] font-medium rounded-btn hover:bg-cta/10 transition-colors"
              >
                <svg viewBox="0 0 16 16" fill="none" className="w-3 h-3"><line x1="8" y1="2" x2="8" y2="14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /><line x1="2" y1="8" x2="14" y2="8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
                Добавить представление
              </button>
              <button
                onClick={() => setShowActionModal(true)}
                className="flex items-center gap-[6px] h-[34px] px-4 border-2 border-cta text-cta text-[13px] font-medium rounded-btn hover:bg-cta/10 transition-colors"
              >
                <svg viewBox="0 0 16 16" fill="none" className="w-3 h-3"><line x1="8" y1="2" x2="8" y2="14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /><line x1="2" y1="8" x2="14" y2="8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
                Новое действие
              </button>
            </div>

            {/* Блоки страницы */}
            <CollapsibleSection
              title="Блоки страницы"
              open={blocksOpen}
              onToggle={() => setBlocksOpen((v) => !v)}
            >
              <BlockCanvas
                blocks={blocks}
                fields={userFields}
                pages={pages}
                entities={entities}
                onBlocksChange={handleBlocksChange}
                onBlockChange={handleUpdateBlock}
                onBlockConfigChange={handleUpdateBlockConfig}
                onAddClick={() => setPickerOpen(true)}
              />
            </CollapsibleSection>

            {/* Название */}
            <FieldRow title="Название" desc="Уникальное название для этого представления.">
              <div className="w-[538px] h-[41px] bg-cardbg rounded-btn px-5 flex items-center">
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onBlur={handleNameBlur}
                  onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
                  className="w-full bg-transparent text-[18px] text-primary outline-none placeholder:text-primary/40"
                  placeholder="Текст"
                />
              </div>
            </FieldRow>

            {/* База данных */}
            <FieldRow title="База данных" desc="Какая таблица будет отображаться.">
              <div className="flex items-center gap-5 w-[538px]" onClick={(e) => e.stopPropagation()}>
                <div className="relative flex-1">
                  <button
                    onClick={() => setEntityDdOpen((v) => !v)}
                    className="flex items-center justify-between gap-5 w-full h-[41px] px-5 bg-cardbg rounded-btn text-[18px] text-primary"
                  >
                    <span className="truncate">
                      {selectedEntity?.display_name ?? (entities.length === 0 ? "Нет таблиц" : "Выберите таблицу")}
                    </span>
                    <span className={cn("w-3 h-3 shrink-0 transition-transform", entityDdOpen && "rotate-180")}>
                      <Chevron open={false} />
                    </span>
                  </button>
                  {entityDdOpen && entities.length > 0 && (
                    <div className="absolute top-[44px] left-0 z-50 w-full bg-white rounded-[20px] shadow-[0_4px_20px_rgba(0,0,0,0.15)] p-[5px] flex flex-col max-h-[280px] overflow-y-auto">
                      {entities.map((ent) => (
                        <button
                          key={ent.id}
                          onClick={() => handleEntityChange(ent.id)}
                          className={cn(
                            "flex items-center px-[20px] py-[10px] rounded-[20px] text-[16px] font-medium text-primary transition-colors text-left",
                            ent.id === selectedEntityId ? "bg-selected text-cta" : "hover:bg-selected/60",
                          )}
                        >
                          {ent.display_name}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <IconButton label="Редактировать"><EditIcon /></IconButton>
              </div>
            </FieldRow>

            {/* Тип представления */}
            <FieldRow title="Тип представления" desc="Каким будет представление." labelWidth={236}>
              <div className="flex flex-wrap gap-x-[6px] gap-y-[17px] w-[540px] py-[7px]">
                {VIEW_TYPES.map((t) => (
                  <TypeTile
                    key={t.id}
                    label={t.label}
                    icon={t.icon}
                    selected={viewType === t.id}
                    onClick={() => handleViewTypeChange(t.id)}
                  />
                ))}
              </div>
            </FieldRow>

            {/* Положение */}
            <FieldRow title="Положение" desc="Где находится кнопка для доступа к представлению.">
              <div className="flex py-[7px]">
                {POSITIONS.map((p, i) => (
                  <button
                    key={p}
                    onClick={() => patchLayout({ position: p })}
                    className={cn(
                      "h-[38px] px-[11px] flex items-center justify-center text-[12px] leading-[150%] font-medium transition-colors whitespace-nowrap box-border",
                      "bg-cardbg",
                      position === p ? "border-2 border-cta text-cta z-10" : "border border-mainbg text-primary",
                      i === 0 && "rounded-l-[18px]",
                      i === POSITIONS.length - 1 && "rounded-r-[18px]"
                    )}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </FieldRow>

            {/* ── Параметры представления ── */}
            <CollapsibleSection
              title="Параметры представления"
              open={paramsOpen}
              onToggle={() => setParamsOpen((v) => !v)}
            >
              {/* Сортировка */}
              <FieldRow title="Сортировка" desc="Отсортируйте строки по одному или нескольким столбцам.">
                <div className="flex flex-col gap-[8px] w-[538px]">
                  <SortConfig
                    fields={userFields}
                    sort={sortRules}
                    onChange={(s) => patchLayout({ sort: s })}
                  />
                  <button
                    onClick={() => setShowSortModal(true)}
                    className="flex items-center gap-[6px] w-fit h-[34px] px-4 bg-cta/10 text-cta text-[13px] font-medium rounded-btn hover:bg-cta/20 transition-colors"
                  >
                    <svg viewBox="0 0 16 16" fill="none" className="w-3 h-3"><line x1="2" y1="4" x2="10" y2="4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /><line x1="2" y1="8" x2="14" y2="8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /><line x1="2" y1="12" x2="8" y2="12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
                    Расширенная сортировка
                  </button>
                </div>
              </FieldRow>

              {/* Группировка */}
              <FieldRow title="Группировка" desc="Сгруппируйте строки по значениям в одном или нескольких их столбцах.">
                <div className="flex flex-col gap-[8px] w-[538px]">
                  <GroupConfig
                    fields={userFields}
                    groupBy={(layout.group_by as string[]) ?? []}
                    onChange={(g) => patchLayout({ group_by: g })}
                  />
                  <button
                    onClick={() => setShowGroupModal(true)}
                    className="flex items-center gap-[6px] w-fit h-[34px] px-4 bg-cta/10 text-cta text-[13px] font-medium rounded-btn hover:bg-cta/20 transition-colors"
                  >
                    <svg viewBox="0 0 16 16" fill="none" className="w-3 h-3"><rect x="2" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.6" /><rect x="9" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.6" /><rect x="2" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.6" /><rect x="9" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.6" /></svg>
                    Настройки группировки
                  </button>
                </div>
              </FieldRow>

              {viewType === "card" ? (
                <FieldRow title="Стиль страницы" desc="Как отображаются страницы форм." labelWidth={252}>
                  <div className="flex flex-col gap-[33px] w-[538px]">
                    <PageStyleSegmented
                      value={(layout.page_style as string) ?? "Карточки"}
                      onChange={(v) => patchLayout({ page_style: v })}
                    />
                    <CardStyleConfig pageStyle={(layout.page_style as string) ?? "Карточки"} />
                  </div>
                </FieldRow>
              ) : (
                <>
                  <FieldRow
                    title="Порядок столбцов"
                    desc="Выберите, какие столбцы показывать в представлении."
                    labelWidth={267}
                  >
                    <ColumnOrder
                      mode={colMode}
                      onMode={(m) => patchLayout({ column_order_mode: m })}
                      fields={userFields}
                      hidden={hiddenColumns}
                      onToggleColumn={(fieldName) => {
                        const next = hiddenColumns.includes(fieldName)
                          ? hiddenColumns.filter((c) => c !== fieldName)
                          : [...hiddenColumns, fieldName];
                        patchLayout({ hidden_columns: next });
                      }}
                      systemFields={systemFields}
                      visibleSystem={visibleSystemColumns}
                      onToggleSystemColumn={(fieldName) => {
                        const next = visibleSystemColumns.includes(fieldName)
                          ? visibleSystemColumns.filter((c) => c !== fieldName)
                          : [...visibleSystemColumns, fieldName];
                        patchLayout({ visible_system_columns: next });
                      }}
                    />
                  </FieldRow>

                  <FieldRow
                    title="Ширина колонки"
                    desc="Насколько широкими должны быть столбцы?"
                  >
                    <div className="py-[7px]">
                      <WidthSegmented value={columnWidth} onChange={(v) => patchLayout({ column_width: v })} />
                    </div>
                  </FieldRow>

                  <FieldRow title="Быстрое редактирование" desc="Разрешить вносить изменения непосредственно в табличное представление.">
                    <div className="py-[7px]">
                      <Toggle on={quickEdit} onChange={() => patchLayout({ quick_edit: !quickEdit })} />
                    </div>
                  </FieldRow>
                </>
              )}
            </CollapsibleSection>

            {/* Сохранённые виды — только если выбрана сущность */}
            {selectedEntityId && (
              <CollapsibleSection title="Сохранённые виды" open={true} onToggle={() => {}}>
                <div className="px-5 pb-4 flex flex-col gap-2">
                  {savedViews.length === 0 && (
                    <span className="text-[13px] text-primary/50">Нет сохранённых видов</span>
                  )}
                  {savedViews.map((v) => (
                    <div key={v.id} className="flex items-center justify-between rounded-[8px] border border-mainbg px-3 py-2">
                      <div className="flex flex-col">
                        <span className="text-[13px] font-medium text-primary">{v.name}</span>
                        <span className="text-[11px] text-primary/50">{v.view_type}{v.is_default ? " · По умолчанию" : ""}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {!v.is_default && (
                          <button
                            onClick={() => setDefaultViewMutation.mutate(v.id)}
                            className="text-[11px] text-cta hover:underline"
                          >
                            Сделать дефолтным
                          </button>
                        )}
                        <button
                          onClick={() => deleteViewMutation.mutate(v.id)}
                          className="text-[11px] text-mistake hover:underline"
                        >
                          Удалить
                        </button>
                      </div>
                    </div>
                  ))}

                  {showSaveViewInput ? (
                    <div className="flex gap-2 mt-1">
                      <input
                        type="text"
                        value={saveViewName}
                        onChange={(e) => setSaveViewName(e.target.value)}
                        placeholder="Название вида"
                        className="flex-1 text-[13px] border border-mainbg rounded-[6px] px-2 py-1 outline-none bg-white text-primary"
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && saveViewName.trim()) {
                            const vtMap: Record<string, string> = { deck: "kanban", details: "detail", map: "table", chart: "table", gantt: "table" };
                            const vt = vtMap[viewType] ?? viewType;
                            createViewMutation.mutate(
                              { name: saveViewName.trim(), view_type: (vt as "table" | "form" | "kanban" | "calendar" | "gallery" | "detail"), config: { sort: layout.sort, group_by: layout.group_by, hidden_columns: layout.hidden_columns, column_width: layout.column_width } },
                              { onSuccess: () => { setSaveViewName(""); setShowSaveViewInput(false); } },
                            );
                          }
                          if (e.key === "Escape") { setShowSaveViewInput(false); setSaveViewName(""); }
                        }}
                        autoFocus
                      />
                      <button
                        onClick={() => {
                          if (!saveViewName.trim()) return;
                          const vtMap: Record<string, string> = { deck: "kanban", details: "detail", map: "table", chart: "table", gantt: "table" };
                          const vt = vtMap[viewType] ?? viewType;
                          createViewMutation.mutate(
                            { name: saveViewName.trim(), view_type: (vt as "table" | "form" | "kanban" | "calendar" | "gallery" | "detail"), config: { sort: layout.sort, group_by: layout.group_by, hidden_columns: layout.hidden_columns, column_width: layout.column_width } },
                            { onSuccess: () => { setSaveViewName(""); setShowSaveViewInput(false); } },
                          );
                        }}
                        className="text-[12px] bg-cta text-white rounded-[6px] px-3 py-1"
                      >
                        Сохранить
                      </button>
                      <button onClick={() => { setShowSaveViewInput(false); setSaveViewName(""); }} className="text-[12px] text-primary/50 hover:text-primary">✕</button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setShowSaveViewInput(true)}
                      className="mt-1 text-[12px] text-cta hover:underline text-left"
                    >
                      + Сохранить текущий вид
                    </button>
                  )}
                </div>
              </CollapsibleSection>
            )}

            <BehaviorSection
              behavior={(layout.behavior as { offline?: boolean; cache?: boolean }) ?? {}}
              onChange={(b) => patchLayout({ behavior: b })}
            />
            <DocumentationSection
              link={(layout.doc_link as string) ?? ""}
              onChange={(l) => patchLayout({ doc_link: l })}
            />
          </div>
        )}
      </div>

      <IframePreview
        appId={appId}
        appName={app?.name ?? "Приложение"}
        activePageId={activeView}
        iframeRef={iframeRef}
        accent={design.accent ?? "#35A7FF"}
      />

      {pickerOpen && (
        <BlockPickerModal
          onAdd={handleAddBlock}
          onClose={() => setPickerOpen(false)}
        />
      )}

      {showSortModal && (
        <SortingModal
          columns={userFields.map((f) => f.display_name)}
          rules={sortRules.map((r) => ({
            column: userFields.find((f) => f.name === r.field)?.display_name ?? r.field,
            direction: r.dir,
          }))}
          onClose={() => setShowSortModal(false)}
          onApply={(rules) => {
            const mapped = rules.map((r) => ({
              field: userFields.find((f) => f.display_name === r.column)?.name ?? r.column,
              dir: r.direction,
            }));
            patchLayout({ sort: mapped });
            setShowSortModal(false);
          }}
        />
      )}

      {showGroupModal && (
        <GroupingModal
          columns={userFields.map((f) => f.display_name)}
          onClose={() => setShowGroupModal(false)}
          onApply={(settings) => {
            const fieldName = userFields.find((f) => f.display_name === settings.groupBy)?.name ?? settings.groupBy;
            patchLayout({ group_by: fieldName ? [fieldName] : [] });
            setShowGroupModal(false);
          }}
          onReset={() => {
            patchLayout({ group_by: [] });
            setShowGroupModal(false);
          }}
        />
      )}

      {showDensityModal && (
        <DensityModal
          current={
            design.density === "compact" ? "compact"
            : design.density === "spacious" ? "spacious"
            : "standard"
          }
          onClose={() => setShowDensityModal(false)}
          onApply={(d) => {
            patchLayout({ design: { ...design, density: d === "standard" ? "normal" : d } });
            setShowDensityModal(false);
          }}
        />
      )}

      {showViewsModal && (
        <TableViewsModal
          onClose={() => setShowViewsModal(false)}
          onAdd={(type) => {
            handleAddPage("main", type);
            setShowViewsModal(false);
          }}
        />
      )}

      {showActionModal && (
        <NewActionModal
          onClose={() => setShowActionModal(false)}
          onConfirm={(name, type) => {
            const actionTypeMap: Record<string, string> = {
              "Добавить строку": "save",
              "Открыть URL":     "url",
              "Изменить строку": "save",
              "Удалить строку":  "url",
              "Отправить уведомление": "url",
              "Запустить процесс":     "url",
            };
            const actionType = actionTypeMap[type] ?? "url";
            const newBlock: PageBlock = {
              id: genId(),
              type: "button",
              title: name || "Кнопка",
              config: { label: name || "Кнопка", actionType, href: "", width: "half" },
            };
            handleBlocksChange([...blocks, newBlock]);
            setShowActionModal(false);
          }}
        />
      )}

      {quickAddEntityId && (
        <QuickAddRecordModal
          entity={entities.find((e) => e.id === quickAddEntityId) ?? null}
          onClose={() => setQuickAddEntityId(null)}
          onSave={(payload) => {
            createRecordMutation.mutate(
              { payload },
              { onSuccess: () => { setQuickAddEntityId(null); _postRefetch(); } },
            );
          }}
          saving={createRecordMutation.isPending}
        />
      )}

      {permissionsPageId && (
        <PagePermissionsModal
          pageTitle={pages.find((p) => p.id === permissionsPageId)?.title ?? "Страница"}
          roles={allRoles}
          permissions={pagePermsQuery.data ?? []}
          saving={setPagePermissionsMutation.isPending}
          onClose={() => setPermissionsPageId(null)}
          onSave={(perms) => {
            setPagePermissionsMutation.mutate(
              { pageId: permissionsPageId, permissions: perms },
              { onSuccess: () => setPermissionsPageId(null) },
            );
          }}
        />
      )}
    </div>
  );
}

/* ── Page permissions modal ── */
function PagePermissionsModal({
  pageTitle,
  roles,
  permissions,
  saving,
  onClose,
  onSave,
}: {
  pageTitle: string;
  roles: { id: string; display_name: string }[];
  permissions: { role_id: string; can_view: boolean }[];
  saving: boolean;
  onClose: () => void;
  onSave: (perms: { role_id: string; can_view: boolean }[]) => void;
}) {
  const [draft, setDraft] = useState<Record<string, boolean>>(() => {
    const map: Record<string, boolean> = {};
    for (const p of permissions) { map[p.role_id] = p.can_view; }
    return map;
  });

  function toggle(roleId: string) {
    setDraft((prev) => ({ ...prev, [roleId]: !prev[roleId] }));
  }

  function handleSave() {
    const perms = roles.map((r) => ({ role_id: r.id, can_view: draft[r.id] !== false }));
    onSave(perms);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-white rounded-[20px] shadow-[0_8px_40px_rgba(0,32,95,0.18)] w-[480px] max-h-[80vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-6 py-5 border-b border-cardbg">
          <div>
            <p className="text-[18px] font-semibold text-primary">Права видимости страницы</p>
            <p className="text-[13px] text-primary/50 mt-0.5 truncate">{pageTitle}</p>
          </div>
          <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-mainbg transition-colors text-primary/40 hover:text-primary text-[20px] leading-none">×</button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-2">
          <p className="text-[13px] text-primary/50 mb-1">Снимите галочку с роли, чтобы скрыть страницу от пользователей с этой ролью.</p>
          {roles.length === 0 && (
            <p className="text-[13px] text-primary/40 py-4 text-center">Нет ролей</p>
          )}
          {roles.map((role) => {
            const canView = draft[role.id] !== false;
            return (
              <div
                key={role.id}
                className="flex items-center justify-between px-4 py-3 rounded-[10px] bg-mainbg"
              >
                <span className="text-[15px] text-primary font-medium">{role.display_name}</span>
                <button
                  onClick={() => toggle(role.id)}
                  role="switch"
                  aria-checked={canView}
                  className="relative w-[46px] h-[24px] rounded-[30px] flex items-center px-[3px] transition-colors shrink-0"
                  style={{ background: canView ? "#35A7FF" : "#C2DBF8" }}
                >
                  <span
                    className="w-[18px] h-[18px] rounded-full bg-white shadow transition-transform"
                    style={{ transform: canView ? "translateX(22px)" : "translateX(0)" }}
                  />
                </button>
              </div>
            );
          })}
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 border-t border-cardbg">
          <button onClick={onClose} className="h-[40px] px-5 rounded-[20px] border border-cardbg text-[14px] text-primary hover:bg-mainbg transition-colors">
            Отмена
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="h-[40px] px-5 rounded-[20px] bg-cta text-white text-[14px] font-semibold hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {saving ? "Сохранение…" : "Сохранить"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Quick-add record modal ── */
function QuickAddRecordModal({
  entity,
  onClose,
  onSave,
  saving,
}: {
  entity: { display_name: string; fields: FieldRead[] } | null;
  onClose: () => void;
  onSave: (payload: Record<string, unknown>) => void;
  saving: boolean;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  if (!entity) return null;
  const fields = entity.fields.filter((f) => !f.is_system);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload: Record<string, unknown> = {};
    fields.forEach((f) => { if (values[f.name] !== undefined && values[f.name] !== "") payload[f.name] = values[f.name]; });
    onSave(payload);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div
        className="bg-white rounded-[20px] shadow-[0_8px_40px_rgba(0,32,95,0.18)] w-[480px] max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-[30px] pt-[24px] pb-[16px]">
          <h3 className="text-[20px] font-bold text-primary">Новая запись — {entity.display_name}</h3>
          <button onClick={onClose} className="text-primary/40 hover:text-primary text-[22px] leading-none transition-colors">×</button>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col gap-[14px] px-[30px] pb-[24px] overflow-y-auto">
          {fields.map((f) => (
            <div key={f.id} className="flex flex-col gap-[4px]">
              <label className="text-[13px] font-medium text-primary/70">
                {f.display_name}{f.is_required && <span className="text-red-500 ml-0.5">*</span>}
              </label>
              {f.field_type === "text" || f.field_type === "email" || f.field_type === "phone" || f.field_type === "url" ? (
                <input
                  type="text"
                  value={values[f.name] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                  required={f.is_required}
                  className="h-[40px] px-[12px] rounded-[10px] border border-primary/20 text-[15px] text-primary outline-none focus:border-cta transition-colors"
                />
              ) : f.field_type === "number" || f.field_type === "decimal" ? (
                <input
                  type="number"
                  value={values[f.name] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                  required={f.is_required}
                  className="h-[40px] px-[12px] rounded-[10px] border border-primary/20 text-[15px] text-primary outline-none focus:border-cta transition-colors"
                />
              ) : f.field_type === "boolean" ? (
                <label className="flex items-center gap-[8px] cursor-pointer">
                  <input
                    type="checkbox"
                    checked={values[f.name] === "true"}
                    onChange={(e) => setValues((v) => ({ ...v, [f.name]: String(e.target.checked) }))}
                    className="w-4 h-4 accent-cta"
                  />
                  <span className="text-[14px] text-primary">Да</span>
                </label>
              ) : (
                <input
                  type="text"
                  value={values[f.name] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                  required={f.is_required}
                  className="h-[40px] px-[12px] rounded-[10px] border border-primary/20 text-[15px] text-primary outline-none focus:border-cta transition-colors"
                />
              )}
            </div>
          ))}
          {fields.length === 0 && (
            <p className="text-[14px] text-primary/40">Нет полей для заполнения</p>
          )}
          <div className="flex justify-end gap-[10px] mt-[6px]">
            <button type="button" onClick={onClose} className="h-[40px] px-[20px] rounded-[20px] border-2 border-primary/20 text-[15px] text-primary hover:bg-cardbg transition-colors">
              Отмена
            </button>
            <button
              type="submit"
              disabled={saving}
              className="h-[40px] px-[20px] rounded-[20px] bg-cta text-white text-[15px] font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {saving ? "Сохранение…" : "Добавить"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ── Layout helpers ── */
function FieldRow({
  title,
  desc,
  labelWidth = 232,
  children,
}: {
  title: string;
  desc: string;
  labelWidth?: number;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start pl-[40px] pr-[37px] gap-[40px]">
      <div className="flex flex-col shrink-0" style={{ width: labelWidth }}>
        <span className="text-[20px] leading-[150%] font-medium text-primary">{title}</span>
        <span className="text-[14px] leading-[150%] text-primary">{desc}</span>
      </div>
      <div className="flex-1 flex justify-end">{children}</div>
    </div>
  );
}

function CollapsibleSection({
  title,
  open,
  onToggle,
  children,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="border-y-2 border-white py-[10px] flex flex-col gap-[20px]">
      <button onClick={onToggle} className="flex items-center justify-between px-[40px] py-[7px]">
        <span className="text-[20px] leading-[150%] font-bold text-primary">{title}</span>
        <span className="w-3 h-3 shrink-0"><Chevron open={open} /></span>
      </button>
      {open && <div className="flex flex-col gap-[30px]">{children}</div>}
    </div>
  );
}


function BehaviorSection({
  behavior,
  onChange,
}: {
  behavior: { offline?: boolean; cache?: boolean };
  onChange: (b: { offline?: boolean; cache?: boolean }) => void;
}) {
  const [open, setOpen] = useState(false);
  const offlineEnabled = behavior.offline ?? true;
  const cacheContent = behavior.cache ?? true;
  const setOfflineEnabled = () => onChange({ ...behavior, offline: !offlineEnabled });
  const setCacheContent = () => onChange({ ...behavior, cache: !cacheContent });

  return (
    <div className="border-y-2 border-white py-[10px] flex flex-col gap-[20px]">
      <button onClick={() => setOpen((v) => !v)} className="flex items-center justify-between px-[40px] py-[7px]">
        <span className="text-[20px] leading-[150%] font-bold text-primary">Поведение</span>
        <span className="w-3 h-3 shrink-0"><Chevron open={open} /></span>
      </button>
      {open && (
        <div className="flex flex-col gap-[20px] px-[40px] pb-[10px]">
          {/* Info banner */}
          <div className="flex items-center gap-[10px] px-5 py-[10px] bg-[#CBE3FF] rounded-[5px]">
            <svg viewBox="0 0 20 20" fill="none" className="w-5 h-5 shrink-0">
              <circle cx="10" cy="10" r="8" stroke="#35A7FF" strokeWidth="2" />
              <line x1="10" y1="9" x2="10" y2="14" stroke="#35A7FF" strokeWidth="2" strokeLinecap="round" />
              <circle cx="10" cy="6.5" r="1" fill="#35A7FF" />
            </svg>
            <span className="text-[16px] text-primary">Настройте приложение для работы в автономном режиме.</span>
          </div>

          <div className="flex flex-col gap-[0px] bg-white rounded-[5px] overflow-hidden">
            <div className="px-5 py-[15px] bg-[#CBE3FF]">
              <span className="text-[18px] font-semibold text-primary">Автономное использование</span>
            </div>
            {/* Row 1 */}
            <div className="flex items-center justify-between px-5 py-[20px] border-b border-mainbg">
              <div className="flex flex-col gap-[5px] max-w-[440px]">
                <span className="text-[18px] font-semibold text-primary">Приложение может запускаться в автономном режиме</span>
                <span className="text-[14px] text-primary/70 leading-[1.4]">Разрешите приложению запускаться даже при отсутствии подключения к Интернету. Изменения не будут синхронизированы, пока пользователь снова не подключится к Интернету.</span>
              </div>
              <OfflineToggle on={offlineEnabled} onChange={setOfflineEnabled} />
            </div>
            {/* Row 2 */}
            <div className="flex items-center justify-between px-5 py-[20px]">
              <div className="flex flex-col gap-[5px] max-w-[440px]">
                <span className="text-[18px] font-semibold text-primary">Сохранить контент для использования в автономном режиме</span>
                <span className="text-[14px] text-primary/70 leading-[1.4]">Сделать все изображения и файлы доступными в автономном режиме.</span>
              </div>
              <OfflineToggle on={cacheContent} onChange={setCacheContent} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function OfflineToggle({ on, onChange }: { on: boolean; onChange: () => void }) {
  return (
    <button
      onClick={onChange}
      role="switch"
      aria-checked={on}
      className="relative w-[55px] h-[28px] rounded-[30px] flex items-center px-[3px] transition-colors shrink-0"
      style={{ background: on ? "#35A7FF" : "#C2DBF8" }}
    >
      <span
        className="w-[22px] h-[22px] rounded-full bg-white shadow transition-transform"
        style={{ transform: on ? "translateX(27px)" : "translateX(0)" }}
      />
    </button>
  );
}

function DocumentationSection({
  link,
  onChange,
}: {
  link: string;
  onChange: (l: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(link);
  useEffect(() => { setDraft(link); }, [link]);

  return (
    <div className="border-y-2 border-white py-[10px] flex flex-col gap-[20px]">
      <button onClick={() => setOpen((v) => !v)} className="flex items-center justify-between px-[40px] py-[7px]">
        <span className="text-[20px] leading-[150%] font-bold text-primary">Документация</span>
        <span className="w-3 h-3 shrink-0"><Chevron open={open} /></span>
      </button>
      {open && (
        <div className="flex items-start px-[40px] gap-[40px] pb-[10px]">
          <div className="flex flex-col shrink-0" style={{ width: 232 }}>
            <span className="text-[20px] leading-[150%] font-medium text-primary">Ссылка на приложение</span>
            <span className="text-[14px] leading-[150%] text-primary">Комментарии помогут вам и вашим сотрудникам лучше зафиксировать и понять структуру приложения.</span>
          </div>
          <div className="flex-1 flex justify-end">
            <div className="w-[538px] h-[41px] bg-cardbg rounded-btn px-5 flex items-center">
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={() => draft !== link && onChange(draft)}
                onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
                placeholder="https://..."
                className="w-full bg-transparent text-[18px] text-primary outline-none placeholder:text-primary/30"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Controls ── */
function DropdownPill({ value, className }: { value: string; className?: string }) {
  return (
    <button
      disabled
      title="В разработке"
      className={cn(
        "flex items-center justify-between gap-5 h-[41px] px-5 bg-cardbg rounded-btn text-[18px] text-primary/50 cursor-not-allowed",
        className
      )}
    >
      <span className="truncate">{value}</span>
      <span className="w-3 h-3 shrink-0"><Chevron open={false} /></span>
    </button>
  );
}

function IconButton({ label, children, onClick }: { label: string; children: React.ReactNode; onClick?: () => void }) {
  const inert = !onClick;
  return (
    <button
      aria-label={label}
      title={inert ? `${label} (в разработке)` : label}
      onClick={onClick}
      disabled={inert}
      className={cn(
        "w-10 h-10 flex items-center justify-center rounded-full transition-colors shrink-0",
        inert ? "opacity-40 cursor-not-allowed" : "hover:bg-cardbg/40",
      )}
    >
      {children}
    </button>
  );
}

function TypeTile({
  label,
  icon,
  selected,
  onClick,
}: {
  label: string;
  icon: React.ReactNode;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-[85px] h-[75px] flex flex-col items-center justify-center gap-[5px] rounded-[5px] box-border transition-all",
        "bg-cardbg/85",
        selected ? "border-2 border-cta" : "border-2 border-transparent"
      )}
    >
      <span className={cn("w-[35px] h-[35px]", selected && "text-cta")}>{icon}</span>
      <span className={cn("text-[12px] leading-[150%] font-medium", selected ? "text-cta" : "text-primary")}>
        {label}
      </span>
    </button>
  );
}

/* ── Sort config (real fields, persisted) ── */
function SortConfig({
  fields,
  sort,
  onChange,
}: {
  fields: FieldRead[];
  sort: { field: string; dir: "asc" | "desc" }[];
  onChange: (s: { field: string; dir: "asc" | "desc" }[]) => void;
}) {
  const usedFields = new Set(sort.map((s) => s.field));
  const available = fields.filter((f) => !usedFields.has(f.name));

  function addSort() {
    const first = available[0];
    if (!first) return;
    onChange([...sort, { field: first.name, dir: "asc" }]);
  }
  function updateSort(idx: number, patch: Partial<{ field: string; dir: "asc" | "desc" }>) {
    onChange(sort.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  }
  function removeSort(idx: number) {
    onChange(sort.filter((_, i) => i !== idx));
  }

  return (
    <div className="flex flex-col gap-[8px] w-[538px]">
      {sort.length === 0 && (
        <span className="text-[14px] text-primary/40">Сортировка не задана</span>
      )}
      {sort.map((s, idx) => {
        const fieldLabel = fields.find((f) => f.name === s.field)?.display_name ?? s.field;
        return (
          <div key={idx} className="flex items-center gap-[12px]">
            <div className="flex-1 flex items-center gap-[10px] h-[41px] px-3 bg-white rounded-btn">
              <span className="w-5 h-5 opacity-40"><DragVert /></span>
              <select
                value={s.field}
                onChange={(e) => updateSort(idx, { field: e.target.value })}
                className="flex-1 bg-cardbg rounded-btn h-[33px] px-3 text-[16px] text-primary outline-none"
              >
                <option value={s.field}>{fieldLabel}</option>
                {available.map((f) => (
                  <option key={f.id} value={f.name}>{f.display_name}</option>
                ))}
              </select>
              <button
                onClick={() => updateSort(idx, { dir: s.dir === "asc" ? "desc" : "asc" })}
                className="bg-cardbg rounded-btn h-[33px] px-3 text-[15px] text-primary whitespace-nowrap"
              >
                {s.dir === "asc" ? "По возрастанию" : "По убыванию"}
              </button>
            </div>
            <IconButton label="Удалить"><span onClick={() => removeSort(idx)}><TrashIcon /></span></IconButton>
          </div>
        );
      })}
      {available.length > 0 && (
        <button
          onClick={addSort}
          className="flex items-center gap-[6px] w-fit h-[36px] px-4 bg-white rounded-btn text-[14px] font-medium text-cta hover:bg-cardbg/40 transition-colors"
        >
          <PlusGlyph /> Добавить сортировку
        </button>
      )}
    </div>
  );
}

/* ── Group config (real fields, persisted) ── */
function GroupConfig({
  fields,
  groupBy,
  onChange,
}: {
  fields: FieldRead[];
  groupBy: string[];
  onChange: (g: string[]) => void;
}) {
  const groupable = fields.filter((f) =>
    ["select", "boolean", "text", "multi_select"].includes(f.field_type),
  );
  const used = new Set(groupBy);
  const available = groupable.filter((f) => !used.has(f.name));

  return (
    <div className="flex flex-col gap-[8px] w-[538px] py-[7px]">
      {groupBy.map((g) => {
        const label = fields.find((f) => f.name === g)?.display_name ?? g;
        return (
          <div key={g} className="flex items-center justify-between h-[41px] px-5 bg-white rounded-btn">
            <span className="text-[16px] text-primary">{label}</span>
            <button onClick={() => onChange(groupBy.filter((x) => x !== g))} className="w-6 h-6"><TrashIcon /></button>
          </div>
        );
      })}
      {available.length > 0 && (
        <select
          value=""
          onChange={(e) => e.target.value && onChange([...groupBy, e.target.value])}
          className="w-fit h-[36px] px-4 bg-white rounded-btn text-[14px] font-medium text-cta outline-none"
        >
          <option value="">+ Добавить группировку</option>
          {available.map((f) => (
            <option key={f.id} value={f.name}>{f.display_name}</option>
          ))}
        </select>
      )}
      {groupBy.length === 0 && available.length === 0 && (
        <span className="text-[14px] text-primary/40">Нет полей для группировки</span>
      )}
    </div>
  );
}

function PlusGlyph() {
  return (
    <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4">
      <line x1="8" y1="3" x2="8" y2="13" stroke="#35A7FF" strokeWidth="2" strokeLinecap="round" />
      <line x1="3" y1="8" x2="13" y2="8" stroke="#35A7FF" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

/* ── Column order (real fields, show/hide persisted) ── */
function ColumnOrder({
  mode,
  onMode,
  fields,
  hidden,
  onToggleColumn,
  systemFields = [],
  visibleSystem = [],
  onToggleSystemColumn,
}: {
  mode: "auto" | "manual";
  onMode: (m: "auto" | "manual") => void;
  fields: FieldRead[];
  hidden: string[];
  onToggleColumn: (fieldName: string) => void;
  systemFields?: FieldRead[];
  visibleSystem?: string[];
  onToggleSystemColumn?: (fieldName: string) => void;
}) {
  return (
    <div className="w-[538px]">
      {/* Tabs */}
      <div className="flex">
        <button
          onClick={() => onMode("auto")}
          className={cn(
            "h-[40px] px-5 flex items-center text-[20px] font-semibold text-primary rounded-t-[20px] transition-colors",
            mode === "auto" ? "bg-white" : "bg-transparent"
          )}
        >
          Автоматически
        </button>
        <button
          onClick={() => onMode("manual")}
          className={cn(
            "h-[34px] mt-[3px] px-5 flex items-center text-[20px] font-semibold text-primary rounded-[36px] transition-colors",
            mode === "manual" ? "bg-cardbg" : "bg-transparent"
          )}
        >
          Вручную
        </button>
      </div>

      {/* Panel */}
      <div className="bg-white rounded-[0_10px_10px_10px] py-[15px] flex flex-col gap-3 px-[25px]">
        {fields.length === 0 && (
          <span className="text-[14px] text-primary/40">Выберите таблицу, чтобы настроить столбцы</span>
        )}
        {mode === "auto" && fields.length > 0 && (
          <span className="text-[14px] text-primary/50">Все столбцы показываются автоматически</span>
        )}
        {mode === "manual" && fields.map((f) => {
          const visible = !hidden.includes(f.name);
          return (
            <div key={f.id} className="flex items-center justify-between h-[41px] px-5 bg-mainbg rounded-btn">
              <button onClick={() => onToggleColumn(f.name)} className="flex items-center gap-[15px]">
                <span className={cn(
                  "w-[23px] h-[23px] rounded-[5px] border-2 border-primary flex items-center justify-center",
                  visible && "bg-primary",
                )}>
                  {visible && (
                    <svg viewBox="0 0 16 16" className="w-3 h-3"><path d="M3 8 L7 12 L13 4" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
                  )}
                </span>
                <span className="text-[18px] text-primary">{f.display_name}</span>
              </button>
              <span className="text-[13px] text-primary/40">{f.field_type}</span>
            </div>
          );
        })}
        {mode === "manual" && systemFields.length > 0 && (
          <>
            <span className="text-[12px] font-medium text-primary/40 uppercase tracking-wide pt-2">Системные поля</span>
            {systemFields.map((f) => {
              const visible = visibleSystem.includes(f.name);
              return (
                <div key={f.id} className="flex items-center justify-between h-[41px] px-5 bg-mainbg rounded-btn">
                  <button onClick={() => onToggleSystemColumn?.(f.name)} className="flex items-center gap-[15px]">
                    <span className={cn(
                      "w-[23px] h-[23px] rounded-[5px] border-2 border-primary flex items-center justify-center",
                      visible && "bg-primary",
                    )}>
                      {visible && (
                        <svg viewBox="0 0 16 16" className="w-3 h-3"><path d="M3 8 L7 12 L13 4" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
                      )}
                    </span>
                    <span className="text-[18px] text-primary/60">{f.display_name}</span>
                  </button>
                  <span className="text-[13px] text-primary/40">{f.field_type}</span>
                </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}

function WidthSegmented({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const OPTS = ["Узкая", "Средняя", "Широкая"];
  return (
    <div className="flex">
      {OPTS.map((o, i) => (
        <button
          key={o}
          onClick={() => onChange(o)}
          className={cn(
            "h-[41px] px-5 flex items-center text-[18px] font-medium text-primary bg-cardbg border-r border-white",
            i === 0 && "rounded-l-btn",
            i === OPTS.length - 1 && "rounded-r-btn border-r-0",
            value === o && "border-2 border-cta text-cta z-10"
          )}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

function PageStyleSegmented({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const OPTS = ["Полная", "Карточки", "Список", "Сетка"];
  return (
    <div className="flex">
      {OPTS.map((o, i) => (
        <button
          key={o}
          onClick={() => onChange(o)}
          className={cn(
            "h-[38px] px-[27px] flex items-center justify-center text-[16px] font-medium text-primary bg-cardbg border-r border-white box-border whitespace-nowrap",
            i === 0 && "rounded-l-btn",
            i === OPTS.length - 1 && "rounded-r-btn border-r-0",
            value === o && "border-2 border-cta z-10"
          )}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

function CardStyleConfig({ pageStyle }: { pageStyle: string }) {
  const ROWS_BY_STYLE: Record<string, { id: string; label: string; value: string }[]> = {
    "Карточки": [
      { id: "icon",     label: "Иконка",       value: "Отправить CMS" },
      { id: "title",    label: "Заголовок",    value: "Заголовок" },
      { id: "subtitle", label: "Подзаголовок", value: "Отправить CMS" },
      { id: "image",    label: "Изображение",  value: "Отправить" },
    ],
    "Полная": [
      { id: "title",    label: "Заголовок",    value: "Заголовок" },
      { id: "subtitle", label: "Подзаголовок", value: "Отправить CMS" },
    ],
    "Список": [
      { id: "icon",     label: "Иконка",       value: "Отправить CMS" },
      { id: "title",    label: "Заголовок",    value: "Заголовок" },
      { id: "subtitle", label: "Подзаголовок", value: "Отправить CMS" },
    ],
    "Сетка": [
      { id: "icon",     label: "Иконка",       value: "Отправить CMS" },
      { id: "title",    label: "Заголовок",    value: "Заголовок" },
      { id: "image",    label: "Изображение",  value: "Отправить" },
    ],
  };
  const rows = ROWS_BY_STYLE[pageStyle] ?? ROWS_BY_STYLE["Карточки"];

  const preview =
    pageStyle === "Список" ? (
      /* Список: горизонтальная строка */
      <div className="w-[290px] flex items-center gap-[12px] bg-white px-[14px] py-[12px] shrink-0">
        <span className="w-[44px] h-[44px] rounded-full bg-cardbg shrink-0" />
        <div className="flex flex-col">
          <span className="text-[16px] font-medium text-primary leading-snug">Заголовок</span>
          <span className="text-[12px] text-primary/60 leading-snug">Подзаголовок</span>
        </div>
      </div>
    ) : pageStyle === "Сетка" ? (
      /* Сетка: квадратная карточка */
      <div className="w-[140px] flex flex-col bg-white shrink-0">
        <div className="w-full h-[100px] bg-cardbg" />
        <div className="flex items-center gap-[8px] p-[8px]">
          <span className="w-[28px] h-[28px] rounded-full bg-cardbg/60 shrink-0" />
          <span className="text-[13px] font-medium text-primary leading-snug">Заголовок</span>
        </div>
      </div>
    ) : pageStyle === "Полная" ? (
      /* Полная: широкая карточка без аватара */
      <div className="w-[290px] flex flex-col bg-white shrink-0 p-[16px] gap-[8px]">
        <span className="text-[20px] font-semibold text-primary">Заголовок</span>
        <span className="text-[14px] text-primary/60">Подзаголовок</span>
        <div className="w-full h-[80px] bg-cardbg rounded mt-[4px]" />
      </div>
    ) : (
      /* Карточки (default) */
      <div className="w-[290px] flex flex-col justify-end bg-white shrink-0">
        <div className="flex items-center p-[10px] h-[76px]">
          <span className="w-[56px] h-[56px] rounded-full bg-cardbg shrink-0" />
          <div className="flex flex-col px-[15px]">
            <span className="text-[20px] leading-[150%] font-medium text-primary">Заголовок</span>
            <span className="text-[14px] leading-[150%] text-primary">Подзаголовок</span>
          </div>
        </div>
        <div className="w-full h-[149px] bg-cardbg" />
      </div>
    );

  return (
    <div className="flex items-start gap-[40px]">
      {preview}

      {/* Config rows */}
      <div className="flex flex-col gap-[20px] w-[431px]">
        {rows.map((r) => (
          <div key={r.id} className="flex items-center gap-[10px]">
            <div className="flex items-center justify-between gap-[31px] flex-1 h-[41px] pl-5 bg-white rounded-btn">
              <span className="text-[18px] text-primary whitespace-nowrap">{r.label}</span>
              <DropdownPill value={r.value} className="w-[219px] pl-[30px]" />
            </div>
            <IconButton label="Редактировать"><EditIcon /></IconButton>
          </div>
        ))}
      </div>
    </div>
  );
}

function Toggle({ on, onChange }: { on: boolean; onChange: () => void }) {
  return (
    <button
      onClick={onChange}
      role="switch"
      aria-checked={on}
      className={cn(
        "w-[55px] h-[31px] rounded-[30px] flex items-center transition-colors px-[3px]",
        on ? "bg-cardbg" : "bg-white border-2 border-cardbg"
      )}
    >
      <span
        className={cn(
          "w-[23px] h-[23px] rounded-full bg-cta transition-transform",
          on ? "translate-x-[24px]" : "translate-x-0 bg-primary/30"
        )}
      />
    </button>
  );
}

/* ── Tab: Правила формирования (conditions stored in layout.rules) ── */
function RulesTab({
  fields,
  rules,
  onChange,
}: {
  fields: FieldRead[];
  rules: RuleCond[];
  onChange: (r: RuleCond[]) => void;
}) {
  function addRule() {
    const first = fields[0];
    onChange([...rules, { id: genId(), field: first?.name ?? "", op: "eq", value: "" }]);
  }
  function update(id: string, patch: Partial<RuleCond>) {
    onChange(rules.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }
  function remove(id: string) {
    onChange(rules.filter((r) => r.id !== id));
  }
  const needsValue = (op: RuleCond["op"]) => op !== "empty" && op !== "not_empty";

  return (
    <div className="flex flex-col gap-[24px] pt-[36px] px-[40px] pb-[40px]">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-[20px] font-bold text-primary">Правила формирования</h2>
          <p className="text-[14px] text-primary/55 mt-1 max-w-[480px]">
            Показываются только строки, удовлетворяющие всем условиям.
          </p>
        </div>
        {fields.length > 0 && (
          <button
            onClick={addRule}
            className="flex items-center gap-[6px] h-[36px] px-4 bg-cta text-white text-[13px] font-medium rounded-[8px] hover:bg-active transition-colors shrink-0"
          >
            <PlusGlyphWhite /> Добавить условие
          </button>
        )}
      </div>

      {/* No table selected */}
      {fields.length === 0 && (
        <div className="flex items-center gap-3 px-5 py-4 bg-[#EBF4FF] rounded-[10px]">
          <svg viewBox="0 0 20 20" fill="none" className="w-5 h-5 shrink-0 text-cta">
            <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.8" />
            <line x1="10" y1="9" x2="10" y2="14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            <circle cx="10" cy="6.5" r="1" fill="currentColor" />
          </svg>
          <span className="text-[14px] text-primary">Сначала выберите таблицу на вкладке «Представления».</span>
        </div>
      )}

      {/* Empty state */}
      {rules.length === 0 && fields.length > 0 && (
        <div className="flex flex-col items-center gap-3 py-10 text-center">
          <svg viewBox="0 0 48 48" fill="none" className="w-12 h-12 text-primary/20">
            <rect x="6" y="12" width="36" height="6" rx="3" fill="currentColor" />
            <rect x="6" y="24" width="28" height="6" rx="3" fill="currentColor" />
            <rect x="6" y="36" width="20" height="6" rx="3" fill="currentColor" />
          </svg>
          <p className="text-[14px] text-primary/40">Правил нет — отображаются все записи</p>
          <button
            onClick={addRule}
            className="mt-1 flex items-center gap-2 h-[36px] px-5 border-2 border-cta text-cta text-[13px] font-medium rounded-[8px] hover:bg-cta/10 transition-colors"
          >
            <PlusGlyphWhite /> Добавить первое условие
          </button>
        </div>
      )}

      {/* Rules list */}
      {rules.length > 0 && (
        <div className="flex flex-col">
          {rules.map((r, idx) => (
            <div key={r.id}>
              {/* AND connector */}
              {idx > 0 && (
                <div className="flex items-center gap-3 my-2 pl-1">
                  <div className="flex-1 h-px bg-cardbg" />
                  <span className="text-[11px] font-bold text-primary/35 uppercase tracking-widest px-2">И</span>
                  <div className="flex-1 h-px bg-cardbg" />
                </div>
              )}
              {/* Rule card */}
              <div className="flex items-center gap-3 bg-white rounded-[10px] px-4 py-3 border border-cardbg">
                <span className="text-[12px] font-semibold text-primary/35 w-[28px] shrink-0">
                  {idx === 0 ? "где" : "и"}
                </span>

                {/* Field */}
                <div className="relative flex-1 min-w-[130px]">
                  <select
                    value={r.field}
                    onChange={(e) => update(r.id, { field: e.target.value })}
                    className="w-full h-[36px] appearance-none bg-cardbg rounded-[8px] pl-3 pr-8 text-[14px] text-primary outline-none focus:ring-1 focus:ring-cta/30 cursor-pointer"
                  >
                    {fields.map((f) => (
                      <option key={f.id} value={f.name}>{f.display_name}</option>
                    ))}
                  </select>
                  <svg viewBox="0 0 16 16" fill="none" className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-primary/40 pointer-events-none">
                    <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>

                {/* Operator */}
                <div className="relative shrink-0">
                  <select
                    value={r.op}
                    onChange={(e) => update(r.id, { op: e.target.value as RuleCond["op"] })}
                    className="h-[36px] appearance-none bg-cardbg rounded-[8px] pl-3 pr-8 text-[14px] text-primary outline-none focus:ring-1 focus:ring-cta/30 cursor-pointer"
                  >
                    {(Object.keys(OP_LABELS) as RuleCond["op"][]).map((op) => (
                      <option key={op} value={op}>{OP_LABELS[op]}</option>
                    ))}
                  </select>
                  <svg viewBox="0 0 16 16" fill="none" className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-primary/40 pointer-events-none">
                    <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>

                {/* Value */}
                {needsValue(r.op) ? (
                  <input
                    value={r.value}
                    onChange={(e) => update(r.id, { value: e.target.value })}
                    placeholder="значение"
                    className="flex-1 h-[36px] bg-cardbg rounded-[8px] px-3 text-[14px] text-primary outline-none focus:ring-1 focus:ring-cta/30 placeholder:text-primary/25 min-w-[80px]"
                  />
                ) : (
                  <div className="flex-1" />
                )}

                {/* Delete */}
                <button
                  onClick={() => remove(r.id)}
                  className="w-7 h-7 shrink-0 flex items-center justify-center rounded-full hover:bg-red-50 text-primary/30 hover:text-red-500 transition-colors"
                >
                  <TrashIcon />
                </button>
              </div>
            </div>
          ))}

          {/* Add another rule */}
          <button
            onClick={addRule}
            className="mt-3 self-start flex items-center gap-2 h-[34px] px-4 bg-cta/8 text-cta text-[13px] font-medium rounded-[8px] hover:bg-cta/15 transition-colors"
          >
            <PlusGlyph /> Ещё условие
          </button>
        </div>
      )}
    </div>
  );
}

function PlusGlyphWhite() {
  return (
    <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4">
      <line x1="8" y1="3" x2="8" y2="13" stroke="white" strokeWidth="2" strokeLinecap="round" />
      <line x1="3" y1="8" x2="13" y2="8" stroke="white" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

/* ── Tab: Дизайн (stored in layout.design) ── */
function DesignTab({
  design,
  onChange,
  onOpenDensityModal,
}: {
  design: DesignConfig;
  onChange: (d: DesignConfig) => void;
  onOpenDensityModal: () => void;
}) {
  const accent = design.accent ?? "#35A7FF";
  const theme = design.theme ?? "light";
  const density = design.density ?? "normal";
  const showHeader = design.show_header ?? true;
  const navPosition = design.nav_position ?? "top";

  return (
    <div className="flex flex-col gap-[30px] pt-[40px] px-[40px] pb-[40px]">
      <div className="flex flex-col gap-[6px]">
        <h2 className="text-[22px] font-bold text-primary">Дизайн</h2>
        <p className="text-[15px] text-primary/70">Оформление страницы в работающем приложении.</p>
      </div>

      {/* Accent color */}
      <div className="flex flex-col gap-[10px]">
        <span className="text-[18px] font-medium text-primary">Акцентный цвет</span>
        <div className="flex items-center gap-[12px]">
          {ACCENT_COLORS.map((c) => (
            <button
              key={c}
              onClick={() => onChange({ ...design, accent: c })}
              className={cn(
                "w-[44px] h-[44px] rounded-full transition-transform",
                accent === c ? "ring-4 ring-offset-2 ring-primary/30 scale-110" : "hover:scale-105",
              )}
              style={{ background: c }}
              aria-label={c}
            />
          ))}
        </div>
      </div>

      {/* Theme */}
      <div className="flex flex-col gap-[10px]">
        <span className="text-[18px] font-medium text-primary">Тема</span>
        <div className="flex">
          {(["light", "dark"] as const).map((t, i) => (
            <button
              key={t}
              onClick={() => onChange({ ...design, theme: t })}
              className={cn(
                "h-[41px] px-7 flex items-center text-[16px] font-medium bg-cardbg border-r border-white",
                i === 0 ? "rounded-l-btn" : "rounded-r-btn border-r-0",
                theme === t ? "border-2 border-cta text-cta z-10" : "text-primary",
              )}
            >
              {t === "light" ? "Светлая" : "Тёмная"}
            </button>
          ))}
        </div>
      </div>

      {/* Density */}
      <div className="flex flex-col gap-[10px]">
        <span className="text-[18px] font-medium text-primary">Плотность</span>
        <div className="flex items-center gap-[10px]">
          <div className="flex">
            {(["compact", "normal", "spacious"] as const).map((d, i, arr) => (
              <button
                key={d}
                onClick={() => onChange({ ...design, density: d })}
                className={cn(
                  "h-[41px] px-7 flex items-center text-[16px] font-medium bg-cardbg border-r border-white",
                  i === 0 && "rounded-l-btn",
                  i === arr.length - 1 && "rounded-r-btn border-r-0",
                  density === d ? "border-2 border-cta text-cta z-10" : "text-primary",
                )}
              >
                {d === "compact" ? "Компактная" : d === "normal" ? "Обычная" : "Просторная"}
              </button>
            ))}
          </div>
          <button
            onClick={onOpenDensityModal}
            className="h-[41px] px-4 border-2 border-cta text-cta text-[14px] font-medium rounded-btn hover:bg-cta/10 transition-colors"
          >
            Выбрать визуально
          </button>
        </div>
      </div>

      {/* Show header */}
      <div className="flex items-center justify-between max-w-[538px]">
        <div className="flex flex-col">
          <span className="text-[18px] font-medium text-primary">Показывать заголовок страницы</span>
          <span className="text-[14px] text-primary/60">Название страницы вверху в приложении.</span>
        </div>
        <Toggle on={showHeader} onChange={() => onChange({ ...design, show_header: !showHeader })} />
      </div>

      {/* Nav position */}
      <div className="flex flex-col gap-[10px]">
        <div className="flex flex-col">
          <span className="text-[18px] font-medium text-primary">Позиция меню навигации</span>
          <span className="text-[14px] text-primary/60">Где показывать вкладки страниц на смартфоне.</span>
        </div>
        <div className="flex">
          {(["top", "bottom", "burger"] as const).map((pos, i, arr) => (
            <button
              key={pos}
              onClick={() => onChange({ ...design, nav_position: pos })}
              className={cn(
                "h-[41px] px-7 flex items-center text-[16px] font-medium bg-cardbg border-r border-white",
                i === 0 && "rounded-l-btn",
                i === arr.length - 1 && "rounded-r-btn border-r-0",
                navPosition === pos ? "border-2 border-cta text-cta z-10" : "text-primary",
              )}
            >
              {pos === "top" ? "Сверху" : pos === "bottom" ? "Снизу" : "Бургер"}
            </button>
          ))}
        </div>
      </div>

      {/* ── Typography ── */}
      <div className="flex flex-col gap-[14px]">
        <div className="flex items-center gap-3">
          <span className="text-[18px] font-semibold text-primary">Типографика</span>
          <div className="flex-1 h-px bg-cardbg" />
        </div>

        <div className="flex flex-col gap-[12px] max-w-[538px]">
          {/* Font family */}
          <div className="flex items-center justify-between">
            <div>
              <span className="text-[16px] font-medium text-primary">Шрифт</span>
              <p className="text-[13px] text-primary/50">Применяется ко всем текстам страницы</p>
            </div>
            <div className="relative w-[200px]">
              <select
                value={design.font_family ?? "Inter"}
                onChange={(e) => onChange({ ...design, font_family: e.target.value })}
                className="w-full h-[38px] appearance-none bg-cardbg rounded-[8px] pl-3 pr-8 text-[14px] text-primary outline-none cursor-pointer"
                style={{ fontFamily: design.font_family ?? "Inter" }}
              >
                {FONT_FAMILIES.map((f) => (
                  <option key={f} value={f} style={{ fontFamily: f }}>{f}</option>
                ))}
              </select>
              <svg viewBox="0 0 16 16" fill="none" className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-primary/40 pointer-events-none">
                <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          </div>

          {/* Heading size */}
          <div className="flex items-center justify-between">
            <div>
              <span className="text-[16px] font-medium text-primary">Размер заголовков</span>
            </div>
            <div className="flex h-[36px] bg-cardbg rounded-[8px] p-[3px] gap-[2px] w-[200px]">
              {([["sm","Малый"],["md","Средний"],["lg","Крупный"]] as const).map(([v,l]) => (
                <button
                  key={v}
                  onClick={() => onChange({ ...design, heading_size: v })}
                  className={cn(
                    "flex-1 rounded-[6px] text-[12px] font-medium transition-all",
                    (design.heading_size ?? "md") === v ? "bg-cta text-white shadow-sm" : "text-primary/60 hover:text-primary"
                  )}
                >{l}</button>
              ))}
            </div>
          </div>

          {/* Body size */}
          <div className="flex items-center justify-between">
            <div>
              <span className="text-[16px] font-medium text-primary">Размер текста</span>
            </div>
            <div className="flex h-[36px] bg-cardbg rounded-[8px] p-[3px] gap-[2px] w-[200px]">
              {([["sm","12px"],["md","14px"],["lg","16px"]] as const).map(([v,l]) => (
                <button
                  key={v}
                  onClick={() => onChange({ ...design, body_size: v })}
                  className={cn(
                    "flex-1 rounded-[6px] text-[12px] font-medium transition-all",
                    (design.body_size ?? "md") === v ? "bg-cta text-white shadow-sm" : "text-primary/60 hover:text-primary"
                  )}
                >{l}</button>
              ))}
            </div>
          </div>
        </div>

        {/* Font preview */}
        <div
          className="px-4 py-3 bg-cardbg rounded-[10px] max-w-[538px]"
          style={{ fontFamily: design.font_family ?? "Inter" }}
        >
          <p className={cn("font-bold text-primary mb-1", design.heading_size === "sm" ? "text-[16px]" : design.heading_size === "lg" ? "text-[24px]" : "text-[20px]")}>
            Заголовок страницы
          </p>
          <p className={cn("text-primary/70", design.body_size === "sm" ? "text-[12px]" : design.body_size === "lg" ? "text-[16px]" : "text-[14px]")}>
            Обычный текст страницы с примером содержимого.
          </p>
        </div>
      </div>

      {/* ── Form settings ── */}
      <div className="flex flex-col gap-[14px]">
        <div className="flex items-center gap-3">
          <span className="text-[18px] font-semibold text-primary">Поля форм</span>
          <div className="flex-1 h-px bg-cardbg" />
        </div>

        <div className="flex flex-col gap-[12px] max-w-[538px]">
          {/* Input style */}
          <div className="flex items-center justify-between">
            <div>
              <span className="text-[16px] font-medium text-primary">Стиль полей</span>
              <p className="text-[13px] text-primary/50">Внешний вид полей ввода в формах</p>
            </div>
            <div className="flex h-[36px] bg-cardbg rounded-[8px] p-[3px] gap-[2px] w-[220px]">
              {([["outline","Рамка"],["filled","Заливка"],["minimal","Линия"]] as const).map(([v,l]) => (
                <button
                  key={v}
                  onClick={() => onChange({ ...design, input_style: v })}
                  className={cn(
                    "flex-1 rounded-[6px] text-[12px] font-medium transition-all",
                    (design.input_style ?? "filled") === v ? "bg-cta text-white shadow-sm" : "text-primary/60 hover:text-primary"
                  )}
                >{l}</button>
              ))}
            </div>
          </div>

          {/* Label position */}
          <div className="flex items-center justify-between">
            <div>
              <span className="text-[16px] font-medium text-primary">Позиция лейбла</span>
            </div>
            <div className="flex h-[36px] bg-cardbg rounded-[8px] p-[3px] gap-[2px] w-[180px]">
              {([["top","Сверху"],["inline","Внутри"]] as const).map(([v,l]) => (
                <button
                  key={v}
                  onClick={() => onChange({ ...design, label_position: v })}
                  className={cn(
                    "flex-1 rounded-[6px] text-[12px] font-medium transition-all",
                    (design.label_position ?? "top") === v ? "bg-cta text-white shadow-sm" : "text-primary/60 hover:text-primary"
                  )}
                >{l}</button>
              ))}
            </div>
          </div>

          {/* Field preview */}
          <div className="flex flex-col gap-2 p-4 bg-cardbg rounded-[10px]">
            {(design.label_position ?? "top") === "top" ? (
              <>
                <label className="flex flex-col gap-1">
                  <span className="text-[12px] text-primary/60 font-medium">Имя клиента</span>
                  <div className={cn(
                    "h-[36px] rounded-[8px] flex items-center px-3 text-[14px] text-primary/30",
                    (design.input_style ?? "filled") === "outline" ? "border-2 border-cardbg bg-white" :
                    (design.input_style ?? "filled") === "minimal" ? "border-b-2 border-cardbg rounded-none bg-transparent" :
                    "bg-white"
                  )}>Иван Петров</div>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[12px] text-primary/60 font-medium">Статус</span>
                  <div className={cn(
                    "h-[36px] rounded-[8px] flex items-center px-3 text-[14px] text-primary/30",
                    (design.input_style ?? "filled") === "outline" ? "border-2 border-cardbg bg-white" :
                    (design.input_style ?? "filled") === "minimal" ? "border-b-2 border-cardbg rounded-none bg-transparent" :
                    "bg-white"
                  )}>Активен</div>
                </label>
              </>
            ) : (
              <>
                {["Имя клиента","Статус"].map((label) => (
                  <div key={label} className={cn(
                    "h-[42px] rounded-[8px] flex items-center px-3 gap-3",
                    (design.input_style ?? "filled") === "outline" ? "border-2 border-cardbg bg-white" :
                    (design.input_style ?? "filled") === "minimal" ? "border-b-2 border-cardbg rounded-none bg-transparent" :
                    "bg-white"
                  )}>
                    <span className="text-[12px] text-primary/50 w-[90px] shrink-0">{label}</span>
                    <span className="text-[14px] text-primary/30">Введите значение</span>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Live mini-preview of accent */}
      <div className="flex flex-col gap-[10px]">
        <span className="text-[14px] text-primary/50">Предпросмотр кнопки</span>
        <button
          className="w-fit px-6 h-[42px] rounded-btn text-white text-[15px] font-medium"
          style={{ background: accent, fontFamily: design.font_family ?? "Inter" }}
        >
          Кнопка действия
        </button>
      </div>
    </div>
  );
}

/* ── Iframe preview panel (right side, mirrors RuntimeApp at real scale) ── */
export function IframePreview({
  appId,
  appName,
  activePageId,
  iframeRef,
  accent,
}: {
  appId: string | undefined;
  appName: string;
  activePageId: string;
  iframeRef: React.RefObject<HTMLIFrameElement>;
  accent: string;
}) {
  const [device, setDevice] = useState<"mobile" | "tablet">("mobile");

  const src = appId
    ? `/app/?app=${appId}&preview=true&page=${activePageId}`
    : "";

  function handleDeviceChange(id: string) {
    if (id === "desktop") {
      if (src) window.open(src, "_blank", "noopener,noreferrer");
      return;
    }
    setDevice(id as "mobile" | "tablet");
  }

  const tabs = [
    { id: "mobile", label: "Смартфон", icon: (
      <svg viewBox="0 0 23 23" fill="none" className="w-full h-full">
        <rect x="4" y="1" width="15" height="21" rx="3" stroke="#00205F" strokeWidth="2"/>
        <circle cx="11.5" cy="18.5" r="1" fill="#00205F"/>
      </svg>
    )},
    { id: "tablet", label: "Планшет", icon: (
      <svg viewBox="0 0 23 23" fill="none" className="w-full h-full">
        <rect x="3" y="1" width="17" height="21" rx="2" stroke="#00205F" strokeWidth="2"/>
        <circle cx="11.5" cy="18" r="0.8" fill="#00205F"/>
      </svg>
    )},
    { id: "desktop", label: "Десктоп ↗", disabled: !src, title: src ? "Открыть в новой вкладке" : "Выберите приложение", icon: (
      <svg viewBox="0 0 23 23" fill="none" className="w-full h-full">
        <rect x="1" y="2" width="21" height="14" rx="2" stroke="#00205F" strokeWidth="2"/>
        <path d="M7 20 L16 20" stroke="#00205F" strokeWidth="2" strokeLinecap="round"/>
        <path d="M11.5 16 L11.5 20" stroke="#00205F" strokeWidth="2" strokeLinecap="round"/>
      </svg>
    )},
  ];

  // Mobile: 380×800 phone frame. Tablet: 460×620, 768px content scaled down.
  const DEVICE_CFG = {
    mobile:  { frameW: 380, frameH: 800, iframeW: 390,  borderR: 40 },
    tablet:  { frameW: 460, frameH: 620, iframeW: 768,  borderR: 24 },
  } as const;
  const cfg = DEVICE_CFG[device];
  const scale = cfg.frameW / cfg.iframeW;
  const iframeH = Math.ceil(cfg.frameH / scale);

  return (
    <div
      className="absolute top-[70px] right-0 bg-mainbg flex flex-col items-center gap-[20px] pt-[7px]"
      style={{ width: 580, height: 1000, borderRadius: "5px 20px 20px 5px" }}
    >
      <TabSwitcher
        tabs={tabs}
        activeId={device}
        onChange={handleDeviceChange}
      />

      {/* Device frame */}
      <div
        className="shrink-0 shadow-[0_8px_30px_rgba(0,0,0,0.12)] overflow-hidden relative"
        style={{
          width: cfg.frameW,
          height: cfg.frameH,
          borderRadius: cfg.borderR,
          transition: "width 0.25s, height 0.25s, border-radius 0.25s",
        }}
      >
        {src ? (
          // A scaled iframe won't reliably clip to a rounded ancestor in
          // every browser (its content is its own compositing layer) —
          // rather than rely on border-radius on the iframe itself, mask it
          // with a plain div (guaranteed to clip) sized/scaled identically,
          // and let the iframe just fill that div at 100%.
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: cfg.iframeW,
              height: iframeH,
              borderRadius: cfg.borderR / scale,
              overflow: "hidden",
              transformOrigin: "top left",
              transform: `scale(${scale})`,
            }}
          >
            <iframe
              ref={iframeRef}
              src={src}
              style={{ width: "100%", height: "100%", border: 0, display: "block" }}
              title="Предпросмотр приложения"
            />
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-primary/30 text-[14px]">
            Выберите приложение
          </div>
        )}
      </div>

      <a
        href={appId ? `/app/?app=${appId}` : "/app/"}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center justify-center gap-3 text-white text-[17px] font-medium rounded-btn px-10 py-[10px] hover:opacity-90 transition-opacity"
        style={{ width: 331, background: accent }}
      >
        Открыть {appName}
      </a>
    </div>
  );
}


/* ── Sortable block row ── */
const BLOCK_ICONS: Record<string, React.ReactNode> = {
  // Input
  text_field:   <InputBlockIcon />,
  number_field: <NumberBlockIcon />,
  date_field:   <CalendarIcon />,
  dropdown:     <SelectBlockIcon />,
  toggle:       <ToggleBlockIcon />,
  file_upload:  <FileBlockIcon />,
  lookup:       <LookupBlockIcon />,
  form:         <FormIcon />,
  // Display
  table:        <TableIcon />,
  record_card:  <CardIcon />,
  metric:       <ChartIcon />,
  kpi:          <DashboardIcon />,
  chart:        <ChartIcon />,
  pivot:        <PivotBlockIcon />,
  calendar:     <CalendarIcon />,
  kanban:       <DeckIcon />,
  gantt:        <GanttBlockIcon />,
  tree:         <TreeBlockIcon />,
  rich_text:    <DetailsIcon />,
  view:         <TableIcon />,
  // Action
  button:       <ButtonBlockIcon />,
  import:       <ImportBlockIcon />,
  export:       <ExportBlockIcon />,
  // Container
  modal:        <ModalBlockIcon />,
  tabs:         <TabsBlockIcon />,
  filter_panel: <FilterBlockIcon />,
  divider:      <DividerBlockIcon />,
  iframe:       <MapIcon />,
};

function SortableBlockRow({
  block,
  fields,
  pages,
  entities,
  onChange,
  onConfigChange,
  onDelete,
}: {
  block: PageBlock;
  fields: FieldRead[];
  pages: import("@/shared/api/views").PageRead[];
  entities: { id: string; display_name: string; fields: FieldRead[] }[];
  onChange: (patch: Partial<PageBlock>) => void;
  onConfigChange: (patch: Record<string, unknown>) => void;
  onDelete: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: block.id });

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.4 : 1 }}
      className="rounded-btn bg-white"
    >
      <div className="flex items-center gap-[12px] min-h-[50px] px-5">
        <button
          {...attributes} {...listeners}
          className="w-5 h-5 shrink-0 cursor-grab active:cursor-grabbing text-primary/30 hover:text-primary/60 touch-none"
          title="Перетащить"
        >
          <DragVert />
        </button>
        <span className="w-[22px] h-[22px] shrink-0 text-primary/60">
          {BLOCK_ICONS[block.type] ?? <TableIcon />}
        </span>
        <input
          value={block.title ?? ""}
          onChange={(event) => onChange({ title: event.target.value })}
          className="flex-1 text-[16px] text-primary font-medium bg-transparent outline-none"
          placeholder={BLOCK_TYPE_META[block.type]?.label ?? block.type}
        />
        <span className="text-[12px] text-primary/40 shrink-0">
          {BLOCK_TYPE_META[block.type]?.label}
        </span>
        {!!block.config.visibility_condition && (
          <span title="Есть условие видимости" className="shrink-0">
            <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5 text-cta" stroke="currentColor" strokeWidth="1.6">
              <path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z" />
              <circle cx="8" cy="8" r="2" />
            </svg>
          </span>
        )}
        <button
          onClick={onDelete}
          className="shrink-0 hover:bg-red-50 rounded-full p-1 transition-colors"
          title="Удалить блок"
        >
          <TrashIcon />
        </button>
      </div>
      <BlockInlineSettings block={block} fields={fields} pages={pages} entities={entities} onConfigChange={onConfigChange} />
    </div>
  );
}

function BlockInlineSettings({
  block,
  fields,
  pages,
  entities,
  onConfigChange,
}: {
  block: PageBlock;
  fields: FieldRead[];
  pages: import("@/shared/api/views").PageRead[];
  entities: { id: string; display_name: string; fields: FieldRead[] }[];
  onConfigChange: (patch: Record<string, unknown>) => void;
}) {
  if (block.type === "divider") return null;

  const entityOptions = [
    { value: "", label: "— выберите сущность —" },
    ...entities.map((e) => ({ value: e.id, label: e.display_name })),
  ];

  const entityFields = (entityId: string) => {
    const ent = entities.find((e) => e.id === entityId);
    return ent?.fields ?? [];
  };

  const visibilityCond = (block.config.visibility_condition ?? null) as VisibilityCond | null;

  return (
    <div className="flex flex-col">
      {block.type !== "table" && block.type !== "form" && (
      <div className="grid grid-cols-2 gap-x-[12px] gap-y-[10px] px-5 pb-4 pt-1 border-t border-mainbg mt-0">
      {block.type === "rich_text" && (
        <>
          <ConfigInput
            label="Текст"
            value={(block.config.text as string) ?? ""}
            onChange={(value) => onConfigChange({ text: value })}
          />
          <ConfigSelect
            label="Шрифт"
            value={(block.config.fontFamily as string) ?? "Inter"}
            options={FONT_FAMILIES.map((f) => ({ value: f, label: f }))}
            onChange={(fontFamily) => onConfigChange({ fontFamily })}
          />
          <ConfigSelect
            label="Размер"
            value={(block.config.fontSize as string) ?? "14"}
            options={FONT_SIZES.map((s) => ({ value: s, label: s + "px" }))}
            onChange={(fontSize) => onConfigChange({ fontSize })}
          />
          <ConfigSegmented
            label="Начертание"
            value={(block.config.fontWeight as string) ?? "normal"}
            options={[
              { value: "normal",  label: "Обычный" },
              { value: "medium",  label: "Средний" },
              { value: "bold",    label: "Жирный" },
            ]}
            onChange={(fontWeight) => onConfigChange({ fontWeight })}
          />
          <ConfigSegmented
            label="Выравнивание"
            value={(block.config.textAlign as string) ?? "left"}
            options={[
              { value: "left",    label: "←" },
              { value: "center",  label: "≡" },
              { value: "right",   label: "→" },
            ]}
            onChange={(textAlign) => onConfigChange({ textAlign })}
          />
        </>
      )}
      {(block.type === "metric" || block.type === "kpi") && (
        <>
          <ConfigInput
            label="Значение"
            value={(block.config.value as string) ?? ""}
            onChange={(value) => onConfigChange({ value })}
          />
          <ConfigSelect
            label="Поле формы"
            value={(block.config.dynamic_field as string) ?? ""}
            options={[{ value: "", label: "— статичное значение —" }, ...fields.map((f) => ({ value: f.name, label: f.display_name }))]}
            onChange={(dynamic_field) => onConfigChange({ dynamic_field: dynamic_field || undefined })}
          />
          {block.type === "kpi" && (
            <ConfigInput
              label="Динамика"
              value={(block.config.trend as string) ?? ""}
              onChange={(trend) => onConfigChange({ trend })}
            />
          )}
          <ConfigSelect
            label="Размер числа"
            value={(block.config.fontSize as string) ?? "32"}
            options={["20","24","28","32","40","48","56"].map((s) => ({ value: s, label: s + "px" }))}
            onChange={(fontSize) => onConfigChange({ fontSize })}
          />
        </>
      )}
      {block.type === "chart" && (
        <>
          <ConfigSelect
            label="Тип"
            value={(block.config.chart_type as string) ?? "bar"}
            options={[
              { value: "bar", label: "Столбцы" },
              { value: "line", label: "Линия" },
            ]}
            onChange={(chart_type) => onConfigChange({ chart_type })}
          />
          <ConfigSelect
            label="Поле"
            value={(block.config.value_field as string) ?? ""}
            options={fieldOptions(fields, "Любое число")}
            onChange={(value_field) => onConfigChange({ value_field })}
          />
        </>
      )}
      {block.type === "calendar" && (
        <>
          <ConfigSelect
            label="Дата"
            value={(block.config.date_field as string) ?? ""}
            options={fieldOptions(fields, "Авто")}
            onChange={(date_field) => onConfigChange({ date_field })}
          />
          <ConfigSelect
            label="Заголовок"
            value={(block.config.title_field as string) ?? ""}
            options={fieldOptions(fields, "Первое поле")}
            onChange={(title_field) => onConfigChange({ title_field })}
          />
        </>
      )}
      {block.type === "kanban" && (
        <>
          <ConfigSelect
            label="Группировать"
            value={(block.config.group_by as string) ?? ""}
            options={fieldOptions(fields, "Авто")}
            onChange={(group_by) => onConfigChange({ group_by })}
          />
          <ConfigSelect
            label="Заголовок"
            value={(block.config.card_title as string) ?? ""}
            options={fieldOptions(fields, "Первое поле")}
            onChange={(card_title) => onConfigChange({ card_title })}
          />
        </>
      )}
      {block.type === "iframe" && (
        <ConfigInput
          label="URL"
          value={(block.config.src as string) ?? ""}
          onChange={(src) => onConfigChange({ src })}
        />
      )}

      {/* ── Input blocks ── */}
      {(block.type === "text_field" || block.type === "number_field" || block.type === "date_field" ||
        block.type === "dropdown" || block.type === "toggle" || block.type === "checkbox" ||
        block.type === "file_upload" || block.type === "lookup" || block.type === "responsible") && (
        <ConfigInput
          label="Подпись поля"
          value={(block.config.label as string) ?? ""}
          onChange={(label) => onConfigChange({ label })}
        />
      )}

      {(block.type === "text_field" || block.type === "number_field" ||
        block.type === "dropdown" || block.type === "toggle" || block.type === "checkbox") && (
        <ConfigSelect
          label="Поле"
          value={(block.config.field_name as string) ?? ""}
          options={fieldOptions(fields, "— выберите —")}
          onChange={(field_name) => onConfigChange({ field_name })}
        />
      )}

      {(block.type === "text_field") && (
        <>
          <ConfigInput
            label="Подсказка"
            value={(block.config.placeholder as string) ?? ""}
            onChange={(placeholder) => onConfigChange({ placeholder })}
          />
          <ConfigInput
            label="Маска"
            value={(block.config.mask as string) ?? ""}
            onChange={(mask) => onConfigChange({ mask })}
            placeholder="+7 (___) ___-__-__"
          />
          <ConfigInput
            label="Валидация (regex)"
            value={(block.config.validation as string) ?? ""}
            onChange={(validation) => onConfigChange({ validation })}
            placeholder="^[a-zA-Z]+$"
          />
          <ConfigSegmented
            label="Обязательное"
            value={(block.config.required as boolean) ? "yes" : "no"}
            options={[{ value: "yes", label: "Да" }, { value: "no", label: "Нет" }]}
            onChange={(v) => onConfigChange({ required: v === "yes" })}
          />
        </>
      )}

      {block.type === "number_field" && (
        <>
          <ConfigSelect
            label="Формат"
            value={(block.config.format as string) ?? "number"}
            options={[
              { value: "number",   label: "Число" },
              { value: "currency", label: "Валюта" },
              { value: "percent",  label: "Процент" },
            ]}
            onChange={(format) => onConfigChange({ format })}
          />
          {block.config.format === "currency" && (
            <ConfigSelect
              label="Валюта"
              value={(block.config.currency as string) ?? "RUB"}
              options={[
                { value: "RUB", label: "₽ Рубль" },
                { value: "USD", label: "$ Доллар" },
                { value: "EUR", label: "€ Евро" },
              ]}
              onChange={(currency) => onConfigChange({ currency })}
            />
          )}
          <ConfigInput
            label="Единица изм."
            value={(block.config.unit as string) ?? ""}
            onChange={(unit) => onConfigChange({ unit })}
            placeholder="кг, м², шт."
          />
          <ConfigInput label="Мин" value={(block.config.min as string) ?? ""} onChange={(min) => onConfigChange({ min })} />
          <ConfigInput label="Макс" value={(block.config.max as string) ?? ""} onChange={(max) => onConfigChange({ max })} />
          <ConfigSegmented
            label="Обязательное"
            value={(block.config.required as boolean) ? "yes" : "no"}
            options={[{ value: "yes", label: "Да" }, { value: "no", label: "Нет" }]}
            onChange={(v) => onConfigChange({ required: v === "yes" })}
          />
        </>
      )}

      {block.type === "date_field" && (
        <>
          <ConfigSelect
            label="Поле"
            value={(block.config.field_name as string) ?? ""}
            options={fieldOptions(fields, "— выберите —")}
            onChange={(field_name) => onConfigChange({ field_name })}
          />
          <ConfigSegmented
            label="Режим"
            value={(block.config.mode as string) ?? "single"}
            options={[{ value: "single", label: "Дата" }, { value: "range", label: "Период" }]}
            onChange={(mode) => onConfigChange({ mode })}
          />
          <ConfigSelect
            label="Формат"
            value={(block.config.date_format as string) ?? "DD.MM.YYYY"}
            options={[
              { value: "DD.MM.YYYY", label: "ДД.ММ.ГГГГ" },
              { value: "YYYY-MM-DD", label: "ГГГГ-ММ-ДД" },
              { value: "DD/MM/YYYY", label: "ДД/ММ/ГГГГ" },
            ]}
            onChange={(date_format) => onConfigChange({ date_format })}
          />
          <ConfigSegmented
            label="Обязательное"
            value={(block.config.required as boolean) ? "yes" : "no"}
            options={[{ value: "yes", label: "Да" }, { value: "no", label: "Нет" }]}
            onChange={(v) => onConfigChange({ required: v === "yes" })}
          />
          <ConfigSegmented
            label="По умолчанию"
            value={(block.config.default_today as boolean) ? "today" : "none"}
            options={[{ value: "none", label: "Нет" }, { value: "today", label: "Сегодня" }]}
            onChange={(v) => onConfigChange({ default_today: v === "today" })}
          />
        </>
      )}

      {block.type === "dropdown" && (
        <>
          <ConfigSegmented
            label="Источник"
            value={(block.config.source as string) ?? "static"}
            options={[{ value: "static", label: "Список" }, { value: "entity", label: "Сущность" }]}
            onChange={(source) => onConfigChange({ source })}
          />
          {(block.config.source === "static" || !block.config.source) && (
            <div className="flex flex-col gap-[5px] col-span-2">
              <span className="text-[11px] font-medium text-primary/50 uppercase tracking-wide">Варианты (по одному на строку)</span>
              <textarea
                rows={3}
                value={(block.config.options as string) ?? ""}
                onChange={(e) => onConfigChange({ options: e.target.value })}
                className="bg-cardbg rounded-[8px] px-3 py-2 text-[13px] text-primary outline-none border border-transparent focus:border-cta/40 resize-none"
                placeholder={"Вариант 1\nВариант 2"}
              />
            </div>
          )}
          {block.config.source === "entity" && (
            <>
              <ConfigSelect label="Сущность" value={(block.config.entity_id as string) ?? ""} options={entityOptions} onChange={(entity_id) => onConfigChange({ entity_id })} />
              <ConfigSelect
                label="Поле-подпись"
                value={(block.config.display_field as string) ?? ""}
                options={fieldOptions(entityFields(block.config.entity_id as string), "— авто —")}
                onChange={(display_field) => onConfigChange({ display_field })}
              />
            </>
          )}
          <ConfigSegmented
            label="Множественный"
            value={(block.config.multiple as boolean) ? "yes" : "no"}
            options={[{ value: "no", label: "Нет" }, { value: "yes", label: "Да" }]}
            onChange={(v) => onConfigChange({ multiple: v === "yes" })}
          />
        </>
      )}

      {block.type === "toggle" && (
        <ConfigSegmented
          label="По умолчанию"
          value={(block.config.default_value as boolean) ? "on" : "off"}
          options={[{ value: "off", label: "Выкл" }, { value: "on", label: "Вкл" }]}
          onChange={(v) => onConfigChange({ default_value: v === "on" })}
        />
      )}

      {block.type === "file_upload" && (
        <>
          <ConfigSelect
            label="Поле"
            value={(block.config.field_name as string) ?? ""}
            options={fieldOptions(fields, "— выберите —")}
            onChange={(field_name) => onConfigChange({ field_name })}
          />
          <ConfigInput
            label="Допустимые форматы"
            value={(block.config.accept as string) ?? "*"}
            onChange={(accept) => onConfigChange({ accept })}
            placeholder=".pdf,.docx,.xlsx"
          />
          <ConfigInput
            label="Макс. размер (МБ)"
            value={String(block.config.max_size_mb ?? 10)}
            onChange={(v) => onConfigChange({ max_size_mb: Number(v) || 10 })}
          />
          <ConfigSegmented
            label="Множественный"
            value={(block.config.multiple as boolean) ? "yes" : "no"}
            options={[{ value: "no", label: "Нет" }, { value: "yes", label: "Да" }]}
            onChange={(v) => onConfigChange({ multiple: v === "yes" })}
          />
          {Boolean(block.config.multiple) && (
            <ConfigInput
              label="Макс. кол-во файлов"
              value={String(block.config.max_files ?? 50)}
              onChange={(v) => onConfigChange({ max_files: Number(v) || 50 })}
            />
          )}
        </>
      )}

      {block.type === "lookup" && (
        <>
          <ConfigSelect
            label="Поле"
            value={(block.config.field_name as string) ?? ""}
            options={fieldOptions(fields, "— выберите —")}
            onChange={(field_name) => onConfigChange({ field_name })}
          />
          <ConfigSelect label="Сущность" value={(block.config.entity_id as string) ?? ""} options={entityOptions} onChange={(entity_id) => onConfigChange({ entity_id })} />
          <ConfigSelect
            label="Поле-подпись"
            value={(block.config.display_field as string) ?? ""}
            options={fieldOptions(entityFields(block.config.entity_id as string), "— авто —")}
            onChange={(display_field) => onConfigChange({ display_field })}
          />
          <ConfigSegmented
            label="Множественный"
            value={(block.config.multiple as boolean) ? "yes" : "no"}
            options={[{ value: "no", label: "Нет" }, { value: "yes", label: "Да" }]}
            onChange={(v) => onConfigChange({ multiple: v === "yes" })}
          />
        </>
      )}

      {block.type === "responsible" && (
        <>
          <ConfigSelect
            label="Поле"
            value={(block.config.field_name as string) ?? ""}
            options={fieldOptions(fields, "— выберите —")}
            onChange={(field_name) => onConfigChange({ field_name })}
          />
          <ConfigSelect label="Сущность" value={(block.config.entity_id as string) ?? ""} options={entityOptions} onChange={(entity_id) => onConfigChange({ entity_id })} />
          <ConfigSelect
            label="Поле-подпись"
            value={(block.config.display_field as string) ?? ""}
            options={fieldOptions(entityFields(block.config.entity_id as string), "— авто —")}
            onChange={(display_field) => onConfigChange({ display_field })}
          />
          <ConfigSelect
            label="Поле для сопоставления с ФИО аккаунта"
            value={(block.config.match_field as string) ?? ""}
            options={fieldOptions(entityFields(block.config.entity_id as string), "— как поле-подпись —")}
            onChange={(match_field) => onConfigChange({ match_field })}
          />
        </>
      )}

      {/* ── Display: record card ── */}
      {block.type === "record_card" && (
        <ConfigSelect label="Сущность" value={(block.config.entity_id as string) ?? ""} options={entityOptions} onChange={(entity_id) => onConfigChange({ entity_id })} />
      )}

      {/* ── Display: pivot ── */}
      {block.type === "pivot" && (
        <>
          <ConfigSelect label="Сущность" value={(block.config.entity_id as string) ?? ""} options={entityOptions} onChange={(entity_id) => onConfigChange({ entity_id })} />
          <ConfigSelect label="Строки" value={(block.config.row_field as string) ?? ""} options={fieldOptions(entityFields(block.config.entity_id as string), "— выберите —")} onChange={(row_field) => onConfigChange({ row_field })} />
          <ConfigSelect label="Столбцы" value={(block.config.col_field as string) ?? ""} options={fieldOptions(entityFields(block.config.entity_id as string), "— выберите —")} onChange={(col_field) => onConfigChange({ col_field })} />
          <ConfigSelect label="Значение" value={(block.config.value_field as string) ?? ""} options={fieldOptions(entityFields(block.config.entity_id as string), "— выберите —")} onChange={(value_field) => onConfigChange({ value_field })} />
          <ConfigSelect
            label="Агрегация"
            value={(block.config.agg as string) ?? "count"}
            options={[
              { value: "count", label: "Кол-во" },
              { value: "sum",   label: "Сумма" },
              { value: "avg",   label: "Среднее" },
              { value: "min",   label: "Минимум" },
              { value: "max",   label: "Максимум" },
            ]}
            onChange={(agg) => onConfigChange({ agg })}
          />
        </>
      )}

      {/* ── Display: gantt ── */}
      {block.type === "gantt" && (
        <>
          <ConfigSelect label="Сущность" value={(block.config.entity_id as string) ?? ""} options={entityOptions} onChange={(entity_id) => onConfigChange({ entity_id })} />
          <ConfigSelect label="Заголовок" value={(block.config.title_field as string) ?? ""} options={fieldOptions(entityFields(block.config.entity_id as string), "— авто —")} onChange={(title_field) => onConfigChange({ title_field })} />
          <ConfigSelect label="Дата начала" value={(block.config.start_field as string) ?? ""} options={fieldOptions(entityFields(block.config.entity_id as string), "— выберите —")} onChange={(start_field) => onConfigChange({ start_field })} />
          <ConfigSelect label="Дата конца" value={(block.config.end_field as string) ?? ""} options={fieldOptions(entityFields(block.config.entity_id as string), "— выберите —")} onChange={(end_field) => onConfigChange({ end_field })} />
        </>
      )}

      {/* ── Display: tree ── */}
      {block.type === "tree" && (
        <>
          <ConfigSelect label="Сущность" value={(block.config.entity_id as string) ?? ""} options={entityOptions} onChange={(entity_id) => onConfigChange({ entity_id })} />
          <ConfigSelect label="Подпись" value={(block.config.label_field as string) ?? ""} options={fieldOptions(entityFields(block.config.entity_id as string), "— авто —")} onChange={(label_field) => onConfigChange({ label_field })} />
          <ConfigSelect label="Родитель" value={(block.config.parent_field as string) ?? ""} options={fieldOptions(entityFields(block.config.entity_id as string), "— выберите —")} onChange={(parent_field) => onConfigChange({ parent_field })} />
        </>
      )}

      {/* ── Action: import ── */}
      {block.type === "import" && (
        <>
          <ConfigSelect label="Сущность" value={(block.config.entity_id as string) ?? ""} options={entityOptions} onChange={(entity_id) => onConfigChange({ entity_id })} />
          <ConfigInput label="Форматы" value={(block.config.accept as string) ?? ".xlsx,.csv"} onChange={(accept) => onConfigChange({ accept })} placeholder=".xlsx,.csv" />
          <ConfigSegmented
            label="Заголовки"
            value={(block.config.has_header as boolean) !== false ? "yes" : "no"}
            options={[{ value: "yes", label: "Да" }, { value: "no", label: "Нет" }]}
            onChange={(v) => onConfigChange({ has_header: v === "yes" })}
          />
        </>
      )}

      {/* ── Action: export ── */}
      {block.type === "export" && (
        <>
          <ConfigSelect label="Сущность" value={(block.config.entity_id as string) ?? ""} options={entityOptions} onChange={(entity_id) => onConfigChange({ entity_id })} />
          <ConfigSegmented
            label="Формат"
            value="csv"
            options={[
              { value: "csv", label: "CSV" },
            ]}
            onChange={() => onConfigChange({ format: "csv" })}
          />
          <p className="col-span-2 text-[11px] text-primary/40">Excel и PDF пока не реализованы — блок всегда выгружает CSV.</p>
          <ConfigInput label="Имя файла" value={(block.config.filename as string) ?? ""} onChange={(filename) => onConfigChange({ filename })} placeholder="report" />
        </>
      )}

      {/* ── Container: modal ── */}
      {block.type === "modal" && (
        <>
          <ConfigInput label="Заголовок" value={(block.config.title as string) ?? ""} onChange={(title) => onConfigChange({ title })} />
          <ConfigInput label="Текст кнопки" value={(block.config.trigger_label as string) ?? ""} onChange={(trigger_label) => onConfigChange({ trigger_label })} />
          <ConfigSegmented
            label="Вид кнопки"
            value={(block.config.trigger_variant as string) ?? "primary"}
            options={[
              { value: "primary",   label: "Осн." },
              { value: "secondary", label: "Доп." },
              { value: "link",      label: "Ссылка" },
            ]}
            onChange={(trigger_variant) => onConfigChange({ trigger_variant })}
          />
          <div className="flex flex-col gap-[5px] col-span-2">
            <span className="text-[11px] font-medium text-primary/50 uppercase tracking-wide">Текст в окне</span>
            <textarea
              rows={4}
              value={(block.config.content as string) ?? ""}
              onChange={(e) => onConfigChange({ content: e.target.value })}
              className="bg-cardbg rounded-[8px] px-3 py-2 text-[13px] text-primary outline-none border border-transparent focus:border-cta/40 resize-none"
              placeholder="Содержимое диалога…"
            />
          </div>
        </>
      )}

      {/* ── Container: tabs ── */}
      {block.type === "tabs" && (
        <div className="flex flex-col gap-[10px] col-span-2">
          {((block.config.tabs as { id: string; label: string; content?: string }[]) ?? []).map((tab, i, arr) => (
            <div key={tab.id} className="flex flex-col gap-[5px] border-b border-mainbg pb-2">
              <div className="flex items-center gap-[6px]">
                <input
                  value={tab.label}
                  onChange={(e) => {
                    const tabs = arr.map((t, j) => (j === i ? { ...t, label: e.target.value } : t));
                    onConfigChange({ tabs });
                  }}
                  className="flex-1 h-[30px] bg-cardbg rounded-[6px] px-2 text-[13px] text-primary outline-none"
                  placeholder={`Вкладка ${i + 1}`}
                />
                <button
                  onClick={() => onConfigChange({ tabs: arr.filter((_, j) => j !== i) })}
                  className="w-6 h-6 flex items-center justify-center rounded-full text-primary/40 hover:bg-red-50 hover:text-red-500 transition-colors text-[16px] leading-none"
                >×</button>
              </div>
              <textarea
                rows={2}
                value={tab.content ?? ""}
                onChange={(e) => {
                  const tabs = arr.map((t, j) => (j === i ? { ...t, content: e.target.value } : t));
                  onConfigChange({ tabs });
                }}
                className="bg-cardbg rounded-[8px] px-3 py-2 text-[13px] text-primary outline-none border border-transparent focus:border-cta/40 resize-none"
                placeholder="Содержимое вкладки…"
              />
            </div>
          ))}
          <button
            onClick={() => {
              const current = (block.config.tabs as { id: string; label: string; content?: string }[]) ?? [];
              onConfigChange({ tabs: [...current, { id: `tab${Date.now()}`, label: `Вкладка ${current.length + 1}`, content: "" }] });
            }}
            className="h-[30px] rounded-[6px] border border-dashed border-primary/20 text-[13px] text-primary/60 hover:text-primary hover:border-primary/40 transition-colors"
          >+ Добавить вкладку</button>
        </div>
      )}

      {/* ── Container: filter_panel ── */}
      {block.type === "filter_panel" && (
        <>
          <ConfigSelect label="Сущность" value={(block.config.entity_id as string) ?? ""} options={entityOptions} onChange={(entity_id) => onConfigChange({ entity_id })} />
          <ConfigSegmented
            label="Положение"
            value={(block.config.position as string) ?? "top"}
            options={[{ value: "top", label: "Сверху" }, { value: "side", label: "Сбоку" }]}
            onChange={(position) => onConfigChange({ position })}
          />
        </>
      )}
      {block.type === "positions_picker" && (
        <>
          <ConfigInput
            label="Заголовок"
            value={(block.config.label as string) ?? "Позиции заказа"}
            onChange={(label) => onConfigChange({ label })}
          />
          <ConfigSelect
            label="Каталог (сущность)"
            value={(block.config.catalog_entity_id as string) ?? ""}
            options={entityOptions}
            onChange={(catalog_entity_id) => onConfigChange({ catalog_entity_id })}
          />
          <ConfigInput
            label="Поле названия"
            value={(block.config.catalog_display_field as string) ?? "nazvanie"}
            onChange={(catalog_display_field) => onConfigChange({ catalog_display_field })}
            placeholder="nazvanie"
          />
          <ConfigInput
            label="Поле цены"
            value={(block.config.catalog_price_field as string) ?? "cena"}
            onChange={(catalog_price_field) => onConfigChange({ catalog_price_field })}
            placeholder="cena"
          />
          <ConfigInput
            label="Поле единицы"
            value={(block.config.catalog_unit_field as string) ?? "edinica"}
            onChange={(catalog_unit_field) => onConfigChange({ catalog_unit_field })}
            placeholder="edinica"
          />

          {(() => {
            const extras: PositionsPickerExtra[] = Array.isArray(block.config.extras)
              ? (block.config.extras as PositionsPickerExtra[])
              : (block.config.extra_lookup_entity_id
                  ? [{
                      entity_id: block.config.extra_lookup_entity_id as string,
                      display_field: (block.config.extra_lookup_display_field as string) ?? "",
                      label: (block.config.extra_lookup_label as string) ?? "Раздел",
                      field: (block.config.extra_field as string) ?? "",
                    }]
                  : []);
            function updateExtras(next: PositionsPickerExtra[]) {
              onConfigChange({
                extras: next,
                extra_lookup_entity_id: undefined,
                extra_lookup_display_field: undefined,
                extra_lookup_label: undefined,
                extra_field: undefined,
              });
            }
            return (
              <>
                <div className="col-span-2 text-[11px] font-medium text-primary/50 uppercase tracking-wide pt-2">Доп. связи на строку (опционально)</div>
                {extras.map((ex, i) => (
                  <div key={i} className="col-span-2 grid grid-cols-2 gap-x-[12px] gap-y-[10px] p-3 bg-mainbg rounded-btn">
                    <ConfigSelect
                      label="Сущность"
                      value={ex.entity_id}
                      options={entityOptions}
                      onChange={(entity_id) => updateExtras(extras.map((e, j) => j === i ? { ...e, entity_id, display_field: "" } : e))}
                    />
                    <ConfigSelect
                      label="Поле-подпись"
                      value={ex.display_field}
                      options={fieldOptions(entityFields(ex.entity_id), "— авто —")}
                      onChange={(display_field) => updateExtras(extras.map((e, j) => j === i ? { ...e, display_field } : e))}
                    />
                    <ConfigInput
                      label="Подпись поля"
                      value={ex.label}
                      onChange={(label) => updateExtras(extras.map((e, j) => j === i ? { ...e, label } : e))}
                    />
                    <ConfigSelect
                      label="Поле для сохранения"
                      value={ex.field}
                      options={fieldOptions(entityFields(block.config.positions_entity_id as string), "— выберите —")}
                      onChange={(field) => updateExtras(extras.map((e, j) => j === i ? { ...e, field } : e))}
                    />
                    <button
                      onClick={() => updateExtras(extras.filter((_, j) => j !== i))}
                      className="col-span-2 text-[12px] text-mistake hover:underline text-left"
                    >
                      ✕ Удалить связь
                    </button>
                  </div>
                ))}
                <button
                  onClick={() => updateExtras([...extras, { entity_id: "", display_field: "", label: "Раздел", field: "" }])}
                  className="col-span-2 text-[13px] font-medium text-cta hover:text-active transition-colors text-left"
                >
                  + Добавить связь
                </button>
              </>
            );
          })()}

          <div className="col-span-2 text-[11px] font-medium text-primary/50 uppercase tracking-wide pt-2">Сохранение строк</div>
          <ConfigSelect
            label="Дочерняя сущность"
            value={(block.config.positions_entity_id as string) ?? ""}
            options={entityOptions}
            onChange={(positions_entity_id) => onConfigChange({ positions_entity_id })}
          />
          <ConfigSelect
            label="Поле родителя"
            value={(block.config.parent_field as string) ?? ""}
            options={fieldOptions(entityFields(block.config.positions_entity_id as string), "— выберите —")}
            onChange={(parent_field) => onConfigChange({ parent_field })}
          />
          <ConfigSelect
            label="Поле позиции"
            value={(block.config.item_field as string) ?? ""}
            options={fieldOptions(entityFields(block.config.positions_entity_id as string), "— выберите —")}
            onChange={(item_field) => onConfigChange({ item_field })}
          />
          <ConfigSelect
            label="Поле количества"
            value={(block.config.qty_field as string) ?? "kolichestvo"}
            options={fieldOptions(entityFields(block.config.positions_entity_id as string), "— выберите —")}
            onChange={(qty_field) => onConfigChange({ qty_field })}
          />
          <ConfigSelect
            label="Поле суммы строки"
            value={(block.config.row_total_field as string) ?? ""}
            options={fieldOptions(entityFields(block.config.positions_entity_id as string), "— выберите —")}
            onChange={(row_total_field) => onConfigChange({ row_total_field })}
          />
          <ConfigSelect
            label="Поле итога (в этой записи)"
            value={(block.config.total_field as string) ?? ""}
            options={fieldOptions(fields, "— не сохранять —")}
            onChange={(total_field) => onConfigChange({ total_field })}
          />
        </>
      )}
      {block.type === "button" && (
        <>
          <ConfigSegmented
            label="Действие"
            value={(block.config.actionType as string) ?? "url"}
            options={[
              { value: "url",   label: "Ссылка" },
              { value: "page",  label: "Страница" },
              { value: "block", label: "Блок" },
              { value: "save",  label: "Сохранить" },
            ]}
            onChange={(actionType) => onConfigChange({ actionType })}
          />
          {(block.config.actionType === "url" || !block.config.actionType) && (
            <ConfigInput
              label="URL"
              value={(block.config.href as string) ?? ""}
              onChange={(href) => onConfigChange({ href })}
              placeholder="https://..."
            />
          )}
          {block.config.actionType === "page" && (
            <ConfigSelect
              label="Страница"
              value={(block.config.targetPageId as string) ?? ""}
              options={[
                { value: "", label: "— выберите —" },
                ...pages.map((p) => ({ value: p.id, label: p.title })),
              ]}
              onChange={(targetPageId) => onConfigChange({ targetPageId })}
            />
          )}
          {block.config.actionType === "block" && (
            <ConfigInput
              label="ID блока"
              value={(block.config.targetBlockId as string) ?? ""}
              onChange={(targetBlockId) => onConfigChange({ targetBlockId })}
              placeholder="block-id или #anchor"
            />
          )}
          <ConfigSelect
            label="Размер текста"
            value={(block.config.fontSize as string) ?? "15"}
            options={["12","13","14","15","16","18","20"].map((s) => ({ value: s, label: s + "px" }))}
            onChange={(fontSize) => onConfigChange({ fontSize })}
          />
          <ConfigSegmented
            label="Скругление"
            value={(block.config.radius as string) ?? "rounded"}
            options={[
              { value: "sharp",   label: "Острые" },
              { value: "rounded", label: "Обычное" },
              { value: "pill",    label: "Капсула" },
            ]}
            onChange={(radius) => onConfigChange({ radius })}
          />
          <ConfigSegmented
            label="Ширина"
            value={(block.config.width as string) ?? "full"}
            options={[
              { value: "full",  label: "Полная" },
              { value: "half",  label: "½" },
              { value: "third", label: "⅓" },
              { value: "auto",  label: "Авто" },
            ]}
            onChange={(width) => onConfigChange({ width })}
          />
          {block.config.actionType === "save" && (
            <>
              <ConfigSelect
                label="pre_create: сущность"
                value={((block.config.pre_create as Record<string, unknown>)?.entity_id as string) ?? ""}
                options={entityOptions}
                onChange={(entity_id) => onConfigChange({ pre_create: entity_id ? { ...((block.config.pre_create as Record<string, unknown>) ?? {}), entity_id } : undefined })}
              />
              {((block.config.pre_create as Record<string, unknown>)?.entity_id as string) && (
                <ConfigInput
                  label="pre_create: поле результата"
                  value={((block.config.pre_create as Record<string, unknown>)?.result_field as string) ?? ""}
                  onChange={(result_field) => onConfigChange({ pre_create: { ...((block.config.pre_create as Record<string, unknown>) ?? {}), result_field } })}
                  placeholder="поле в основной форме"
                />
              )}
            </>
          )}
        </>
      )}
      {(block.type === "metric" || block.type === "kpi") && (
        <ConfigSegmented
          label="Ширина"
          value={(block.config.width as string) ?? "full"}
          options={[
            { value: "full",  label: "Полная" },
            { value: "half",  label: "½" },
            { value: "third", label: "⅓" },
          ]}
          onChange={(width) => onConfigChange({ width })}
        />
      )}
      </div>
      )}
      {block.type === "table" && (
        <TableBlockSettings
          entityId={(block.config.entity_id as string) ?? ""}
          visibleSystemColumns={(block.config.visible_system_columns as string[]) ?? []}
          entities={entities}
          onConfigChange={onConfigChange}
        />
      )}
      {block.type === "form" && (
        <FormBlockSettings
          entityId={(block.config.entity_id as string) ?? ""}
          entities={entities}
          fieldConditions={(block.config.field_conditions as Record<string, VisibilityCond | null>) ?? {}}
          onConfigChange={onConfigChange}
        />
      )}
      <VisibilitySection
        fields={fields}
        condition={visibilityCond}
        onChange={(cond) => onConfigChange({ visibility_condition: cond ?? undefined })}
      />
    </div>
  );
}

/* ── Visibility condition type ── */
type VisibilityCond = { field: string; op: string; value: string };

/* ── Visibility section (shared by all non-divider blocks) ── */
function VisibilitySection({
  fields,
  condition,
  onChange,
}: {
  fields: FieldRead[];
  condition: VisibilityCond | null;
  onChange: (c: VisibilityCond | null) => void;
}) {
  const [open, setOpen] = useState(false);

  const OPS = [
    { value: "eq",        label: "равно" },
    { value: "neq",       label: "не равно" },
    { value: "contains",  label: "содержит" },
    { value: "empty",     label: "пусто" },
    { value: "not_empty", label: "не пусто" },
    { value: "gt",        label: ">" },
    { value: "lt",        label: "<" },
  ];
  const needsValue = condition && !["empty", "not_empty"].includes(condition.op);

  function enable() {
    if (!condition && fields.length > 0) {
      onChange({ field: fields[0].name, op: "eq", value: "" });
    }
    setOpen(true);
  }

  return (
    <div className="border-t border-mainbg">
      <button
        onClick={() => (open ? setOpen(false) : enable())}
        className="flex items-center justify-between w-full px-5 py-[10px] text-[13px] text-primary/60 hover:text-primary transition-colors"
      >
        <span className="flex items-center gap-2">
          <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5 shrink-0" stroke="currentColor" strokeWidth="1.6">
            <path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z" />
            <circle cx="8" cy="8" r="2" />
          </svg>
          Условие видимости
          {condition && (
            <span className="px-1.5 py-0.5 bg-cta/10 text-cta text-[11px] rounded-[4px] font-medium">Активно</span>
          )}
        </span>
        <svg viewBox="0 0 16 16" fill="none" className={cn("w-3.5 h-3.5 transition-transform", open && "rotate-180")} stroke="currentColor" strokeWidth="1.6">
          <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div className="px-5 pb-4 flex flex-col gap-2">
          {fields.length === 0 ? (
            <p className="text-[13px] text-primary/40 italic">Сначала привяжите таблицу данных к странице.</p>
          ) : (
            <>
              <p className="text-[12px] text-primary/50">Блок показывается если:</p>
              <div className="flex items-center gap-2 flex-wrap">
                <select
                  value={condition?.field ?? fields[0].name}
                  onChange={(e) => onChange({ field: e.target.value, op: condition?.op ?? "eq", value: condition?.value ?? "" })}
                  className="h-[30px] bg-cardbg rounded-[6px] px-2 text-[13px] text-primary outline-none"
                >
                  {fields.map((f) => <option key={f.id} value={f.name}>{f.display_name}</option>)}
                </select>
                <select
                  value={condition?.op ?? "eq"}
                  onChange={(e) => onChange({ field: condition?.field ?? fields[0].name, op: e.target.value, value: condition?.value ?? "" })}
                  className="h-[30px] bg-cardbg rounded-[6px] px-2 text-[13px] text-primary outline-none"
                >
                  {OPS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
                {needsValue && (
                  <input
                    value={condition?.value ?? ""}
                    onChange={(e) => onChange({ field: condition!.field, op: condition!.op, value: e.target.value })}
                    className="h-[30px] flex-1 min-w-[80px] bg-cardbg rounded-[6px] px-2 text-[13px] text-primary outline-none"
                    placeholder="значение"
                  />
                )}
                <button
                  onClick={() => { onChange(null); setOpen(false); }}
                  title="Убрать условие"
                  className="w-6 h-6 flex items-center justify-center rounded-full text-primary/40 hover:bg-red-50 hover:text-red-500 transition-colors text-[16px] leading-none"
                >×</button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Table block settings ── */
function TableBlockSettings({
  entityId,
  visibleSystemColumns,
  entities,
  onConfigChange,
}: {
  entityId: string;
  visibleSystemColumns: string[];
  entities: { id: string; display_name: string; fields: FieldRead[] }[];
  onConfigChange: (patch: Record<string, unknown>) => void;
}) {
  const entityOptions = [
    { value: "", label: "— выберите сущность —" },
    ...entities.map((e) => ({ value: e.id, label: e.display_name })),
  ];
  const systemFields = (entities.find((e) => e.id === entityId)?.fields ?? []).filter((f) => f.is_system);
  return (
    <div className="px-5 pb-4 pt-3 border-t border-mainbg flex flex-col gap-[10px]">
      <div className="grid grid-cols-2 gap-x-[12px] gap-y-[10px]">
        <ConfigSelect
          label="Источник данных"
          value={entityId}
          options={entityOptions}
          onChange={(entity_id) => onConfigChange({ entity_id })}
        />
      </div>
      {systemFields.length > 0 && (
        <div className="flex flex-col gap-[6px]">
          <span className="text-[12px] font-medium text-primary/40 uppercase tracking-wide pt-2">Системные поля</span>
          {systemFields.map((f) => {
            const visible = visibleSystemColumns.includes(f.name);
            return (
              <div key={f.id} className="flex items-center justify-between h-[41px] px-5 bg-mainbg rounded-btn">
                <button
                  onClick={() => onConfigChange({
                    visible_system_columns: visible
                      ? visibleSystemColumns.filter((c) => c !== f.name)
                      : [...visibleSystemColumns, f.name],
                  })}
                  className="flex items-center gap-[15px]"
                >
                  <span className={cn(
                    "w-[23px] h-[23px] rounded-[5px] border-2 border-primary flex items-center justify-center",
                    visible && "bg-primary",
                  )}>
                    {visible && (
                      <svg viewBox="0 0 16 16" className="w-3 h-3"><path d="M3 8 L7 12 L13 4" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
                    )}
                  </span>
                  <span className="text-[18px] text-primary/60">{f.display_name}</span>
                </button>
                <span className="text-[13px] text-primary/40">{f.field_type}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ── Form block settings ── */
function FormBlockSettings({
  entityId,
  entities,
  fieldConditions,
  onConfigChange,
}: {
  entityId: string;
  entities: { id: string; display_name: string; fields: FieldRead[] }[];
  fieldConditions: Record<string, VisibilityCond | null>;
  onConfigChange: (patch: Record<string, unknown>) => void;
}) {
  const entityOptions = [
    { value: "", label: "— выберите сущность —" },
    ...entities.map((e) => ({ value: e.id, label: e.display_name })),
  ];
  const entity = entities.find((e) => e.id === entityId);
  const userFields = (entity?.fields ?? []).filter((f) => !f.is_system);

  const OPS = [
    { value: "eq",        label: "=" },
    { value: "neq",       label: "≠" },
    { value: "empty",     label: "пусто" },
    { value: "not_empty", label: "≠ пусто" },
  ];

  function setFieldCond(fieldName: string, cond: VisibilityCond | null) {
    const updated: Record<string, VisibilityCond | null> = { ...fieldConditions, [fieldName]: cond };
    if (cond === null) delete updated[fieldName];
    onConfigChange({ field_conditions: updated });
  }

  return (
    <div className="flex flex-col border-t border-mainbg">
      <div className="grid grid-cols-2 gap-x-[12px] gap-y-[10px] px-5 py-3">
        <ConfigSelect
          label="Источник данных"
          value={entityId}
          options={entityOptions}
          onChange={(entity_id) => onConfigChange({ entity_id })}
        />
      </div>
      {userFields.length > 0 && (
        <div className="px-5 pb-4 flex flex-col gap-1">
          <p className="text-[11px] font-medium text-primary/50 uppercase tracking-wide mb-1">Видимость полей формы</p>
          {userFields.map((f) => {
            const cond = fieldConditions[f.name] ?? null;
            const otherFields = userFields.filter((ff) => ff.name !== f.name);
            return (
              <div key={f.id} className="flex items-center gap-2 py-1.5 border-b border-mainbg last:border-0">
                <span className="text-[13px] text-primary w-[110px] shrink-0 truncate" title={f.display_name}>{f.display_name}</span>
                {cond ? (
                  <div className="flex items-center gap-1 flex-1 flex-wrap">
                    <span className="text-[11px] text-primary/40">если</span>
                    <select
                      value={cond.field}
                      onChange={(e) => setFieldCond(f.name, { ...cond, field: e.target.value })}
                      className="h-[24px] bg-cardbg rounded-[4px] px-1.5 text-[12px] text-primary outline-none"
                    >
                      {otherFields.map((ff) => <option key={ff.id} value={ff.name}>{ff.display_name}</option>)}
                    </select>
                    <select
                      value={cond.op}
                      onChange={(e) => setFieldCond(f.name, { ...cond, op: e.target.value })}
                      className="h-[24px] bg-cardbg rounded-[4px] px-1.5 text-[12px] text-primary outline-none"
                    >
                      {OPS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                    {!["empty", "not_empty"].includes(cond.op) && (
                      <input
                        value={cond.value}
                        onChange={(e) => setFieldCond(f.name, { ...cond, value: e.target.value })}
                        className="h-[24px] w-[70px] bg-cardbg rounded-[4px] px-1.5 text-[12px] text-primary outline-none"
                        placeholder="значение"
                      />
                    )}
                    <button onClick={() => setFieldCond(f.name, null)} className="text-primary/30 hover:text-red-400 text-[14px] ml-0.5">×</button>
                  </div>
                ) : (
                  <button
                    onClick={() => setFieldCond(f.name, { field: otherFields[0]?.name ?? "", op: "eq", value: "" })}
                    className="text-[11px] text-cta/70 hover:text-cta transition-colors"
                  >
                    + условие
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function fieldOptions(fields: FieldRead[], emptyLabel: string): { value: string; label: string }[] {
  return [
    { value: "", label: emptyLabel },
    ...fields.map((field) => ({ value: field.name, label: field.display_name })),
  ];
}

function ConfigInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="flex flex-col gap-[5px]">
      <span className="text-[11px] font-medium text-primary/50 uppercase tracking-wide">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder ?? "—"}
        className="h-[36px] bg-cardbg rounded-[8px] px-3 text-[14px] text-primary outline-none
                   border border-transparent focus:border-cta/40 transition-colors
                   placeholder:text-primary/25"
      />
    </label>
  );
}

function ConfigSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-col gap-[5px]">
      <span className="text-[11px] font-medium text-primary/50 uppercase tracking-wide">{label}</span>
      <div className="relative">
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="w-full h-[36px] appearance-none bg-cardbg rounded-[8px] pl-3 pr-8 text-[14px] text-primary outline-none
                     border border-transparent focus:border-cta/40 transition-colors cursor-pointer"
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <svg viewBox="0 0 16 16" fill="none" className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-primary/40 pointer-events-none">
          <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    </label>
  );
}

function ConfigSegmented({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-col gap-[5px] col-span-2">
      <span className="text-[11px] font-medium text-primary/50 uppercase tracking-wide">{label}</span>
      <div className="flex h-[36px] bg-cardbg rounded-[8px] p-[3px] gap-[2px]">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={cn(
              "flex-1 rounded-[6px] text-[13px] font-medium transition-all",
              value === opt.value
                ? "bg-cta text-white shadow-sm"
                : "text-primary/60 hover:text-primary hover:bg-white/60"
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── Block canvas ── */
function BlockCanvas({
  blocks,
  fields,
  pages,
  entities,
  onBlocksChange,
  onBlockChange,
  onBlockConfigChange,
  onAddClick,
}: {
  blocks: PageBlock[];
  fields: FieldRead[];
  pages: import("@/shared/api/views").PageRead[];
  entities: { id: string; display_name: string; fields: FieldRead[] }[];
  onBlocksChange: (b: PageBlock[]) => void;
  onBlockChange: (id: string, patch: Partial<PageBlock>) => void;
  onBlockConfigChange: (id: string, patch: Record<string, unknown>) => void;
  onAddClick: () => void;
}) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIdx = blocks.findIndex((b) => b.id === active.id);
    const newIdx = blocks.findIndex((b) => b.id === over.id);
    onBlocksChange(arrayMove(blocks, oldIdx, newIdx));
  }

  return (
    <div className="flex flex-col gap-[10px] px-[40px]">
      {blocks.length === 0 && (
        <p className="text-[14px] text-primary/40 py-[5px]">Добавьте блоки на страницу</p>
      )}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={blocks.map((b) => b.id)} strategy={verticalListSortingStrategy}>
          {blocks.map((block) => (
            <SortableBlockRow
              key={block.id}
              block={block}
              fields={fields}
              pages={pages}
              entities={entities}
              onChange={(patch) => onBlockChange(block.id, patch)}
              onConfigChange={(patch) => onBlockConfigChange(block.id, patch)}
              onDelete={() => onBlocksChange(blocks.filter((b) => b.id !== block.id))}
            />
          ))}
        </SortableContext>
      </DndContext>
      <button
        onClick={onAddClick}
        className="flex items-center gap-[8px] w-fit h-[38px] px-5 bg-cta text-white text-[14px] font-medium rounded-btn hover:bg-active transition-colors mt-[5px]"
      >
        <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4">
          <line x1="8" y1="2" x2="8" y2="14" stroke="white" strokeWidth="2" strokeLinecap="round" />
          <line x1="2" y1="8" x2="14" y2="8" stroke="white" strokeWidth="2" strokeLinecap="round" />
        </svg>
        Добавить блок
      </button>
    </div>
  );
}

function BlockPickerModal({
  onAdd,
  onClose,
}: {
  onAdd: (type: PageBlock["type"]) => void;
  onClose: () => void;
}) {
  const [activeGroup, setActiveGroup] = useState("input");

  const group = BLOCK_GROUPS.find((g) => g.id === activeGroup) ?? BLOCK_GROUPS[0];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div
        className="bg-white rounded-[20px] shadow-[0_8px_40px_rgba(0,32,95,0.18)] flex overflow-hidden"
        style={{ width: 720, maxHeight: "85vh" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Left: category tabs */}
        <div className="w-[180px] shrink-0 bg-mainbg flex flex-col py-4 gap-1">
          <p className="text-[11px] font-semibold text-primary/40 uppercase tracking-wider px-5 pb-2">Категория</p>
          {BLOCK_GROUPS.map((g) => (
            <button
              key={g.id}
              onClick={() => setActiveGroup(g.id)}
              className={cn(
                "flex items-center gap-2 text-left px-5 py-2.5 text-[14px] font-medium transition-colors",
                activeGroup === g.id ? "bg-white text-cta rounded-r-[10px]" : "text-primary/60 hover:text-primary",
              )}
            >
              <span className="w-[18px] h-[18px] shrink-0">{GROUP_ICONS[g.id]}</span>
              {g.label}
            </button>
          ))}
        </div>

        {/* Right: block grid */}
        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex items-center justify-between px-6 py-4 border-b border-cardbg shrink-0">
            <p className="text-[18px] font-semibold text-primary">{group.label}</p>
            <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-mainbg text-primary/40 hover:text-primary text-[20px] leading-none transition-colors">×</button>
          </div>
          <div className="flex-1 overflow-y-auto p-5">
            <div className="grid grid-cols-3 gap-3">
              {group.types.map((type) => {
                const meta = BLOCK_TYPE_META[type];
                return (
                  <button
                    key={type}
                    onClick={() => { onAdd(type); onClose(); }}
                    className="flex flex-col items-start gap-2 p-4 bg-mainbg rounded-[12px] text-left hover:bg-[#EBF4FF] hover:border-cta border-2 border-transparent transition-all"
                  >
                    <span className="w-7 h-7 text-primary/70">{BLOCK_ICONS[type] ?? <TableIcon />}</span>
                    <span className="text-[13px] font-semibold text-primary leading-tight">{meta.label}</span>
                    <span className="text-[11px] text-primary/50 leading-[1.3]">{meta.desc}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const GROUP_ICONS: Record<string, React.ReactNode> = {
  input:     <InputBlockIcon />,
  display:   <TableIcon />,
  action:    <ButtonBlockIcon />,
  container: <ModalBlockIcon />,
};

/* ── Small icons ── */
function Chevron({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 12 12" fill="none" className={cn("w-full h-full transition-transform", open && "rotate-180")}>
      <path d="M2 4 L6 8 L10 4" stroke="#00205F" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function DragVert() {
  return (
    <svg viewBox="0 0 20 20" fill="none" className="w-full h-full">
      {[6, 10, 14].map((y) => (
        <g key={y}>
          <circle cx="7" cy={y} r="1.5" fill="#00205F" />
          <circle cx="13" cy={y} r="1.5" fill="#00205F" />
        </g>
      ))}
    </svg>
  );
}

function EditIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-[24px] h-[24px]">
      <rect x="5" y="6" width="13" height="13" rx="1" stroke="#00205F" strokeWidth="2" />
      <path d="M12.5 5.5 L18.5 11.5" stroke="#00205F" strokeWidth="2" />
      <path d="M16 3 L21 8 L18.5 10.5 L13.5 5.5 Z" fill="#00205F" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-[22px] h-[22px]">
      <path d="M5 7 L19 7" stroke="#00205F" strokeWidth="2" strokeLinecap="round" />
      <path d="M9 7 L9 5 L15 5 L15 7" stroke="#00205F" strokeWidth="2" />
      <path d="M7 7 L7.5 20 L16.5 20 L17 7" stroke="#00205F" strokeWidth="2" strokeLinejoin="round" />
    </svg>
  );
}

/* ── View-type tile icons (35×35 viewBox) ── */
function CalendarIcon() {
  return (
    <svg viewBox="0 0 35 35" fill="none" className="w-full h-full">
      <rect x="4" y="6" width="27" height="25" rx="2" stroke="currentColor" strokeWidth="3" />
      <path d="M4 13 L31 13" stroke="currentColor" strokeWidth="3" />
      <line x1="11" y1="3" x2="11" y2="9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <line x1="24" y1="3" x2="24" y2="9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
function DeckIcon() {
  return (
    <svg viewBox="0 0 35 35" fill="none" className="w-full h-full">
      <rect x="10" y="4" width="18" height="27" rx="2" stroke="currentColor" strokeWidth="3" />
      <rect x="4" y="8" width="18" height="23" rx="2" stroke="currentColor" strokeWidth="3" fill="#CBE3FF" />
    </svg>
  );
}
function TableIcon() {
  return (
    <svg viewBox="0 0 35 35" fill="none" className="w-full h-full">
      <rect x="4" y="6" width="27" height="23" rx="1.5" stroke="currentColor" strokeWidth="3" />
      <path d="M4 13 L31 13 M13 6 L13 29 M22 13 L22 29" stroke="currentColor" strokeWidth="3" />
    </svg>
  );
}
function GridIcon() {
  return (
    <svg viewBox="0 0 35 35" fill="none" className="w-full h-full">
      <rect x="4" y="4" width="11" height="11" rx="1.5" stroke="currentColor" strokeWidth="3" />
      <rect x="20" y="4" width="11" height="11" rx="1.5" stroke="currentColor" strokeWidth="3" />
      <rect x="4" y="20" width="11" height="11" rx="1.5" stroke="currentColor" strokeWidth="3" />
      <rect x="20" y="20" width="11" height="11" rx="1.5" stroke="currentColor" strokeWidth="3" />
    </svg>
  );
}
function DetailsIcon() {
  return (
    <svg viewBox="0 0 35 35" fill="none" className="w-full h-full">
      <rect x="7" y="4" width="21" height="27" rx="2" stroke="currentColor" strokeWidth="3" />
      <line x1="13" y1="11" x2="22" y2="11" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <line x1="13" y1="17" x2="22" y2="17" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <line x1="13" y1="23" x2="18" y2="23" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
function MapIcon() {
  return (
    <svg viewBox="0 0 35 35" fill="none" className="w-full h-full">
      <path d="M17.5 3 C12 3 8 7 8 12.5 C8 19 17.5 31 17.5 31 C17.5 31 27 19 27 12.5 C27 7 23 3 17.5 3 Z" stroke="currentColor" strokeWidth="3" />
      <circle cx="17.5" cy="12.5" r="3.5" stroke="currentColor" strokeWidth="3" />
    </svg>
  );
}
function ChartIcon() {
  return (
    <svg viewBox="0 0 35 35" fill="none" className="w-full h-full">
      <rect x="4" y="4" width="27" height="27" rx="2.5" stroke="currentColor" strokeWidth="3.5" />
      <path d="M9 22 L15 16 L20 20 L26 12" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function DashboardIcon() {
  return (
    <svg viewBox="0 0 35 35" fill="none" className="w-full h-full">
      <rect x="5" y="5" width="11" height="11" rx="1.8" stroke="currentColor" strokeWidth="3.5" />
      <rect x="19" y="5" width="11" height="7" rx="1.8" stroke="currentColor" strokeWidth="3.5" />
      <rect x="5" y="20" width="11" height="7" rx="1.8" stroke="currentColor" strokeWidth="3.5" />
      <rect x="19" y="16" width="11" height="11" rx="1.8" stroke="currentColor" strokeWidth="3.5" />
    </svg>
  );
}
function FormIcon() {
  return (
    <svg viewBox="0 0 30 27" fill="none" className="w-full h-full">
      <rect x="1" y="2" width="28" height="8" rx="1" stroke="currentColor" strokeWidth="3" />
      <rect x="1" y="17" width="28" height="8" rx="1" stroke="currentColor" strokeWidth="3" />
    </svg>
  );
}
function ButtonBlockIcon() {
  return (
    <svg viewBox="0 0 35 35" fill="none" className="w-full h-full">
      <rect x="4" y="10" width="27" height="15" rx="4" stroke="currentColor" strokeWidth="3" />
      <line x1="12" y1="17.5" x2="23" y2="17.5" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}
function CardIcon() {
  return (
    <svg viewBox="0 0 39 39" fill="none" className="w-full h-full">
      <rect x="3" y="3" width="33" height="33" rx="4" stroke="currentColor" strokeWidth="3.25" />
      <circle cx="13" cy="13" r="3" fill="currentColor" />
      <path d="M5 30 L15 21 L23 28 L28 24 L34 30" stroke="currentColor" strokeWidth="3.25" strokeLinejoin="round" />
    </svg>
  );
}
function InputBlockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
      <rect x="2" y="7" width="20" height="10" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <line x1="6" y1="12" x2="10" y2="12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
function NumberBlockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
      <rect x="2" y="7" width="20" height="10" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <text x="6" y="16" fontSize="8" fontWeight="600" fill="currentColor">123</text>
    </svg>
  );
}
function SelectBlockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
      <rect x="2" y="7" width="20" height="10" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M16 11 L19 12 L16 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function ToggleBlockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
      <rect x="2" y="8" width="20" height="8" rx="4" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="16" cy="12" r="3" fill="currentColor" />
    </svg>
  );
}
function FileBlockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
      <path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M13 2v7h7" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}
function LookupBlockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
      <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.8" />
      <line x1="16.5" y1="16.5" x2="21" y2="21" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <line x1="8" y1="11" x2="14" y2="11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <line x1="11" y1="8" x2="11" y2="14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
function PivotBlockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
      <rect x="2" y="2" width="20" height="20" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <line x1="2" y1="8" x2="22" y2="8" stroke="currentColor" strokeWidth="1.5" />
      <line x1="8" y1="2" x2="8" y2="22" stroke="currentColor" strokeWidth="1.5" />
      <rect x="10" y="10" width="4" height="4" fill="currentColor" opacity="0.4" />
      <rect x="15" y="10" width="5" height="4" fill="currentColor" opacity="0.6" />
    </svg>
  );
}
function GanttBlockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
      <line x1="3" y1="6" x2="3" y2="20" stroke="currentColor" strokeWidth="1.5" />
      <rect x="4" y="5" width="10" height="3" rx="1.5" fill="currentColor" opacity="0.7" />
      <rect x="7" y="10" width="13" height="3" rx="1.5" fill="currentColor" opacity="0.5" />
      <rect x="4" y="15" width="7" height="3" rx="1.5" fill="currentColor" opacity="0.8" />
    </svg>
  );
}
function TreeBlockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
      <circle cx="12" cy="4" r="2" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="5" cy="14" r="2" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="19" cy="14" r="2" stroke="currentColor" strokeWidth="1.6" />
      <line x1="12" y1="6" x2="12" y2="10" stroke="currentColor" strokeWidth="1.4" />
      <line x1="12" y1="10" x2="5" y2="12" stroke="currentColor" strokeWidth="1.4" />
      <line x1="12" y1="10" x2="19" y2="12" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}
function ImportBlockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
      <path d="M12 3v12M8 11l4 4 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M20 17v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
function ExportBlockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
      <path d="M12 15V3M8 7l4-4 4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M20 17v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
function ModalBlockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
      <rect x="3" y="6" width="18" height="13" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <line x1="3" y1="10" x2="21" y2="10" stroke="currentColor" strokeWidth="1.5" />
      <line x1="16" y1="8" x2="18" y2="8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
function TabsBlockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
      <rect x="2" y="8" width="20" height="14" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <rect x="2" y="4" width="7" height="5" rx="1.5" fill="currentColor" opacity="0.8" />
      <rect x="10" y="4" width="7" height="5" rx="1.5" stroke="currentColor" strokeWidth="1.4" opacity="0.5" />
    </svg>
  );
}
function FilterBlockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
      <line x1="4" y1="6" x2="20" y2="6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <line x1="7" y1="12" x2="17" y2="12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <line x1="10" y1="18" x2="14" y2="18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
function DividerBlockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
      <line x1="2" y1="12" x2="22" y2="12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeDasharray="3 2" />
    </svg>
  );
}

// ── ViewFieldsTab ─────────────────────────────────────────────────────

function ViewFieldsTab({
  appId,
  entityId,
  savedViews,
  userFields,
}: {
  appId: string;
  entityId: string;
  savedViews: ViewRead[];
  userFields: { name: string; display_name: string }[];
}) {
  const [selectedViewId, setSelectedViewId] = useState<string>(savedViews[0]?.id ?? "");
  const viewId = selectedViewId || savedViews[0]?.id;

  const configsQuery = useViewFieldConfigs(appId, entityId, viewId);
  const replaceConfigs = useReplaceFieldConfigs(appId, entityId, viewId ?? "");


  const [draft, setDraft] = useState<Record<string, ViewFieldConfigItem>>({});
  const [dirty, setDirty] = useState(false);

  // Sync draft from server when view changes
  useEffect(() => {
    if (!configsQuery.data) return;
    const m: Record<string, ViewFieldConfigItem> = {};
    for (const c of configsQuery.data) {
      m[c.field_name] = {
        field_name: c.field_name,
        is_visible: c.is_visible,
        is_readonly: c.is_readonly,
        display_order: c.display_order,
        width: c.width,
        widget_type: c.widget_type,
        widget_config: c.widget_config,
      };
    }
    setDraft(m);
    setDirty(false);
  }, [configsQuery.data]);

  useEffect(() => {
    if (savedViews.length > 0 && !selectedViewId) {
      setSelectedViewId(savedViews[0].id);
    }
  }, [savedViews, selectedViewId]);

  function patchField(fieldName: string, patch: Partial<ViewFieldConfigItem>) {
    const idx = userFields.findIndex((f) => f.name === fieldName);
    setDraft((prev) => {
      const existing: ViewFieldConfigItem = prev[fieldName] ?? {
        field_name: fieldName,
        is_visible: true,
        is_readonly: false,
        display_order: idx,
        width: null,
        widget_type: null,
        widget_config: {},
      };
      return { ...prev, [fieldName]: { ...existing, ...patch } };
    });
    setDirty(true);
  }

  function handleSave() {
    const configs: ViewFieldConfigItem[] = userFields.map((f, idx) => ({
      field_name: f.name,
      is_visible: draft[f.name]?.is_visible ?? true,
      is_readonly: draft[f.name]?.is_readonly ?? false,
      display_order: draft[f.name]?.display_order ?? idx,
      width: draft[f.name]?.width ?? null,
      widget_type: draft[f.name]?.widget_type ?? null,
      widget_config: draft[f.name]?.widget_config ?? {},
    }));
    replaceConfigs.mutate(configs, { onSuccess: () => setDirty(false) });
  }

  if (!appId || !entityId) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-[16px] text-primary/40">Выберите страницу с таблицей</p>
      </div>
    );
  }

  return (
    <div className="px-[40px] py-[30px] flex flex-col gap-[20px]">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-[12px]">
          <h2 className="text-[20px] font-bold text-primary">Настройка полей представления</h2>
          {savedViews.length > 0 && (
            <select
              value={selectedViewId}
              onChange={(e) => setSelectedViewId(e.target.value)}
              className="h-[34px] px-3 bg-white border border-cardbg rounded-[8px] text-[13px] text-primary outline-none focus:border-cta"
            >
              {savedViews.map((v) => (
                <option key={v.id} value={v.id}>{v.name}</option>
              ))}
            </select>
          )}
        </div>
        {dirty && (
          <button
            onClick={handleSave}
            disabled={replaceConfigs.isPending}
            className="h-[36px] px-[16px] bg-cta text-white text-[14px] font-medium rounded-btn hover:bg-active disabled:opacity-60 transition-colors"
          >
            {replaceConfigs.isPending ? "Сохраняю…" : "Сохранить"}
          </button>
        )}
      </div>

      {savedViews.length === 0 && (
        <p className="text-[14px] text-primary/40">Нет сохранённых представлений. Создайте представление на вкладке «Представления».</p>
      )}

      {savedViews.length > 0 && userFields.length === 0 && (
        <p className="text-[14px] text-primary/40">Нет полей для настройки.</p>
      )}

      {savedViews.length > 0 && userFields.length > 0 && (
        <div className="bg-white border border-cardbg rounded-[8px] overflow-hidden">
          {/* Header */}
          <div className="grid bg-[#F5F6F8] border-b border-cardbg text-[12px] font-semibold text-primary/60"
            style={{ gridTemplateColumns: "1fr 80px 80px 80px" }}
          >
            <div className="px-4 py-2.5">Поле</div>
            <div className="px-3 py-2.5 text-center">Видимость</div>
            <div className="px-3 py-2.5 text-center">Только чтение</div>
            <div className="px-3 py-2.5 text-center">Ширина</div>
          </div>

          {configsQuery.isLoading && (
            <div className="px-4 py-4 text-[13px] text-primary/40">Загрузка…</div>
          )}

          {!configsQuery.isLoading && userFields.map((f, idx) => {
            const cfg = draft[f.name];
            const isVisible = cfg?.is_visible ?? true;
            const isReadonly = cfg?.is_readonly ?? false;
            const width = cfg?.width ?? null;
            return (
              <div
                key={f.name}
                className="grid border-b border-cardbg last:border-b-0 items-center hover:bg-mainbg/40 transition-colors"
                style={{ gridTemplateColumns: "1fr 80px 80px 80px" }}
              >
                <div className="px-4 py-2.5 flex items-center gap-[8px]">
                  <span className="text-[12px] text-primary/30 w-5 tabular-nums text-right">{idx + 1}</span>
                  <span className="text-[13px] text-primary">{f.display_name}</span>
                  <span className="text-[11px] text-primary/30 font-mono">{f.name}</span>
                </div>
                <div className="px-3 py-2.5 flex justify-center">
                  <button
                    onClick={() => patchField(f.name, { is_visible: !isVisible })}
                    className={cn(
                      "w-5 h-5 rounded border-2 flex items-center justify-center transition-colors",
                      isVisible ? "bg-cta border-cta" : "bg-white border-cardbg",
                    )}
                  >
                    {isVisible && <svg viewBox="0 0 10 8" fill="none" className="w-3 h-3"><path d="M1 4l3 3 5-6" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                  </button>
                </div>
                <div className="px-3 py-2.5 flex justify-center">
                  <button
                    onClick={() => patchField(f.name, { is_readonly: !isReadonly })}
                    className={cn(
                      "w-5 h-5 rounded border-2 flex items-center justify-center transition-colors",
                      isReadonly ? "bg-amber-400 border-amber-400" : "bg-white border-cardbg",
                    )}
                  >
                    {isReadonly && <svg viewBox="0 0 10 8" fill="none" className="w-3 h-3"><path d="M1 4l3 3 5-6" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                  </button>
                </div>
                <div className="px-3 py-2.5">
                  <input
                    type="number"
                    min={40}
                    max={600}
                    value={width ?? ""}
                    onChange={(e) => patchField(f.name, { width: e.target.value ? Number(e.target.value) : null })}
                    placeholder="авто"
                    className="w-full h-[26px] px-2 text-[12px] rounded border border-cardbg bg-mainbg text-primary focus:outline-none focus:border-cta"
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
