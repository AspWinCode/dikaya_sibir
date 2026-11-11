import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { formatDistanceToNow } from "date-fns";
import { ru } from "date-fns/locale";
import { Navbar } from "@/components/layout/Navbar";
import { Sidebar, type SidebarTab } from "@/components/layout/Sidebar";
import { PreviewPanel } from "@/components/layout/PreviewPanel";
import { TabSwitcher } from "@/components/ui/TabSwitcher";
import { ProjectCard, CreateProjectCard, type Project } from "@/components/ui/ProjectCard";
import { InfoCard, type InfoCardData } from "@/components/ui/InfoCard";
import {
  CreateProjectModal,
  NewAppModal,
  ShareModal,
  RolesModal,
  CloneAppModal,
  AppVersionsModal,
  CreateFromTemplateModal,
} from "@/components/modals/Modals";
import {
  useApps,
  useCreateApp,
  useUpdateApp,
  useDeleteApp,
  useCloneApp,
} from "@/shared/hooks/useApps";
import { useEntities } from "@/shared/hooks/useEntities";
import { usePages } from "@/shared/hooks/useViews";
import { useRules } from "@/shared/hooks/useRules";
import { useAuthStore } from "@/shared/auth/store";
import { installTemplate } from "@/shared/api/templates";
import type { App } from "@/shared/api/apps";

type ModalType =
  | "create"
  | "new-app"
  | "from-template"
  | "share"
  | "roles"
  | "clone"
  | "versions"
  | null;

/** Map a backend App into the shape the ProjectCard expects. */
function toProject(app: App, currentUserId?: string): Project {
  const statusLabel = app.is_archived
    ? "Архив"
    : app.is_published
    ? "Опубликовано"
    : "Черновик";

  return {
    id: app.id,
    name: app.name,
    description: app.description ?? undefined,
    imageUrl: undefined,
    status: statusLabel,
    owner: currentUserId && app.owner_id === currentUserId ? "Я" : "—",
    lastModified: formatDistanceToNow(new Date(app.updated_at), {
      addSuffix: true,
      locale: ru,
    }),
  };
}

/** Slugify an app name into the [a-z0-9-_] form the backend requires. */
function slugify(name: string): string {
  const base = name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  const safe = base.length >= 2 ? base : `app-${base}`;
  return `${safe}-${Date.now().toString(36)}`;
}


const TOP_TABS = [
  {
    id: "apps",
    label: "Приложения",
    icon: (
      <svg viewBox="0 0 23 23" fill="none" className="w-full h-full">
        <rect x="4" y="1" width="15" height="21" rx="3" stroke="#00205F" strokeWidth="2"/>
        <circle cx="11.5" cy="18.5" r="1" fill="#00205F"/>
      </svg>
    ),
  },
  {
    id: "databases",
    label: "Базы данных",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
        <ellipse cx="12" cy="6" rx="8" ry="3" stroke="#00205F" strokeWidth="2"/>
        <path d="M4 6 L4 18 C4 19.66 7.58 21 12 21 C16.42 21 20 19.66 20 18 L20 6" stroke="#00205F" strokeWidth="2"/>
        <path d="M4 12 C4 13.66 7.58 15 12 15 C16.42 15 20 13.66 20 12" stroke="#00205F" strokeWidth="2"/>
      </svg>
    ),
  },
];

function pluralTable(n: number) {
  const r = n % 10;
  if (n % 100 >= 11 && n % 100 <= 14) return "таблиц";
  if (r === 1) return "таблица";
  if (r >= 2 && r <= 4) return "таблицы";
  return "таблиц";
}

function pluralField(n: number) {
  const r = n % 10;
  if (n % 100 >= 11 && n % 100 <= 14) return "полей";
  if (r === 1) return "поле";
  if (r >= 2 && r <= 4) return "поля";
  return "полей";
}

export function MainPage() {
  const [sidebarTab, setSidebarTab]    = useState<SidebarTab>("all");
  const [topTab, setTopTab]            = useState<"apps" | "databases">("apps");
  const [selectedProject, setSelected] = useState<string | null>(null);
  const [modal, setModal]              = useState<ModalType>(null);
  const [cloneTargetId, setCloneTargetId]     = useState<string | null>(null);
  const [versionsTargetId, setVersionsTargetId] = useState<string | null>(null);
  const [templateSubmitting, setTemplateSubmitting] = useState(false);

  const navigate = useNavigate();
  const currentUser = useAuthStore((s) => s.user);

  const projectScrollRef = useRef<HTMLDivElement>(null);
  const infoScrollRef    = useRef<HTMLDivElement>(null);
  const [projectAtStart, setProjectAtStart] = useState(true);
  const [infoAtStart,    setInfoAtStart]    = useState(true);

  function scrollProjects(dir: 1 | -1) {
    projectScrollRef.current?.scrollBy({ left: dir * 380, behavior: "smooth" });
  }
  function scrollInfo(dir: 1 | -1) {
    infoScrollRef.current?.scrollBy({ left: dir * 280, behavior: "smooth" });
  }
  function onProjectScroll() {
    setProjectAtStart((projectScrollRef.current?.scrollLeft ?? 0) < 10);
  }
  function onInfoScroll() {
    setInfoAtStart((infoScrollRef.current?.scrollLeft ?? 0) < 10);
  }

  function handleSidebarChange(tab: SidebarTab) {
    if (tab === "templates") { navigate("/templates"); return; }
    setSidebarTab(tab);
  }

  const { data, isLoading, isError, refetch } = useApps();
  const createApp          = useCreateApp();
  const updateApp          = useUpdateApp();
  const deleteAppMutation  = useDeleteApp();
  const cloneAppMutation   = useCloneApp();

  const apps = data?.items ?? [];

  const filteredApps =
    sidebarTab === "my"
      ? apps.filter((a) => a.owner_id === currentUser?.id)
      : sidebarTab === "shared"
      ? apps.filter((a) => a.owner_id !== currentUser?.id)
      : apps;

  const projects = filteredApps.map((a) => toProject(a, currentUser?.id));

  function handleRenameApp(appId: string, currentName: string) {
    const name = window.prompt("Новое название:", currentName);
    if (!name?.trim() || name.trim() === currentName) return;
    updateApp.mutate({ appId, body: { name: name.trim() } });
  }

  function handleDeleteApp(appId: string) {
    if (!window.confirm("Удалить приложение?")) return;
    deleteAppMutation.mutate(appId);
    if (selectedProject === appId) setSelected(null);
  }

  function handleOpenClone(appId: string) {
    setCloneTargetId(appId);
    setModal("clone");
  }

  function handleOpenVersions(appId: string) {
    setVersionsTargetId(appId);
    setModal("versions");
  }

  async function handleCreateApp(name: string, category: string) {
    const app = await createApp.mutateAsync({ name, slug: slugify(name), category: category || null });
    setModal(null);
    navigate(`/schema?app=${app.id}`);
  }

  async function handleCreateFromTemplate(name: string, templateId: string, category: string) {
    setTemplateSubmitting(true);
    try {
      const app = await createApp.mutateAsync({ name, slug: slugify(name), category: category || null });
      await installTemplate(app.id, templateId);
      setModal(null);
    } finally {
      setTemplateSubmitting(false);
    }
  }

  async function handleCloneApp(newName: string) {
    if (!cloneTargetId) return;
    await cloneAppMutation.mutateAsync({ appId: cloneTargetId, body: { name: newName } });
    setModal(null);
    setCloneTargetId(null);
  }

  const isApps = topTab === "apps";
  const infoTitle = isApps ? "Информация о проекте" : "Информация о базе данных";

  const effectiveSelected = selectedProject ?? projects[0]?.id ?? null;
  const selected = projects.find((p) => p.id === effectiveSelected);
  const { data: entitiesData } = useEntities(effectiveSelected ?? undefined);
  const { data: pagesData }    = usePages(effectiveSelected ?? undefined);
  const { data: rulesData }    = useRules(effectiveSelected ?? undefined);

  const entities       = entitiesData ?? [];
  const pages          = pagesData    ?? [];
  const rules          = rulesData    ?? [];
  const publishedPages = pages.filter((p) => p.is_published).length;
  const activeRules    = rules.filter((r) => r.is_active).length;
  const totalFields    = entities.reduce((sum, e) => sum + (e.fields?.length ?? 0), 0);

  const open = (route: string) => () => navigate(effectiveSelected ? `${route}?app=${effectiveSelected}` : route);
  const infoCards: InfoCardData[] = isApps
    ? [
        {
          id: "data",
          label: "Данные",
          content: entities.length ? `${entities.length} ${pluralTable(entities.length)}` : "Нет таблиц",
          big: String(entities.length),
          caption: `${pluralTable(entities.length)}${totalFields ? ` · ${totalFields} ${pluralField(totalFields)}` : ""}`,
          items: entities.filter((e) => !e.is_system).map((e) => ({ text: e.display_name, on: true })),
          onOpen: open("/schema"),
        },
        {
          id: "interface",
          label: "Интерфейс",
          content: pages.length ? `Опубликовано ${publishedPages}/${pages.length} стр` : "Нет страниц",
          big: `${publishedPages}/${pages.length}`,
          caption: "страниц опубликовано",
          items: pages.map((p) => ({ text: p.title, on: p.is_published })),
          onOpen: open("/views"),
        },
        {
          id: "security",
          label: "Безопасность",
          content: "Защита подключена",
          big: "✓",
          caption: "Защита подключена",
          onOpen: open("/security"),
        },
        {
          id: "automation",
          label: "Автоматизация",
          content: rules.length ? `${activeRules} активных из ${rules.length} правил` : "Нет правил",
          big: `${activeRules}/${rules.length}`,
          caption: "правил активно",
          items: rules.map((r) => ({ text: r.name, on: r.is_active })),
          onOpen: open("/bot"),
        },
      ]
    : [
        { id: "t1", label: "Данные",        content: entities.length ? `${entities.length} ${pluralTable(entities.length)}` : "Нет таблиц" },
        { id: "t2", label: "Интерфейс",     content: pages.length    ? `${pages.length} страниц` : "Нет страниц" },
        { id: "t3", label: "Безопасность",  content: "Защита подключена" },
        { id: "t4", label: "Автоматизация", content: rules.length    ? `${rules.length} правил` : "Нет правил" },
      ];

  return (
    <div className="relative w-[1920px] h-[1080px] bg-white overflow-hidden">
      <Navbar onGroupAddClick={() => setModal("roles")} />
      <Sidebar active={sidebarTab} onChange={handleSidebarChange} isPlatformAdmin={currentUser?.roles.some((r) => r.id === "platform_admin")} />

      {/* Main content area */}
      <main
        className="absolute top-[70px] bg-mainbg overflow-hidden"
        style={{
          left: 280,
          width: 1045,
          height: 1000,
          borderRadius: "20px 5px 5px 20px",
        }}
      >
        {/* Header: title + tabs */}
        <div className="absolute left-[40px] top-[7px] flex items-center gap-[53px]">
          <h1 className="text-title font-semibold text-primary whitespace-nowrap">
            Выберите проект
          </h1>
          <TabSwitcher
            tabs={TOP_TABS}
            activeId={topTab}
            onChange={(id) => setTopTab(id as "apps" | "databases")}
          />
        </div>

        {/* Project cards row — scrollable */}
        <div
          className="absolute overflow-hidden"
          style={{ left: 40, top: 86, width: 950, height: 292 }}
        >
          <div
            ref={projectScrollRef}
            onScroll={onProjectScroll}
            className="flex items-start gap-[30px]"
            style={{ overflowX: "scroll", overflowY: "hidden", height: 312 }}
          >
            <CreateProjectCard onClick={() => setModal("create")} />

            {isApps && isLoading && (
              <div className="flex items-center text-primary/60 text-lg h-[284px] px-6">
                Загрузка приложений…
              </div>
            )}

            {isApps && isError && (
              <div className="flex flex-col items-start justify-center gap-2 h-[284px] px-6">
                <span className="text-mistake text-lg">Не удалось загрузить приложения</span>
                <button
                  onClick={() => refetch()}
                  className="text-cta hover:text-active underline text-base"
                >
                  Повторить
                </button>
              </div>
            )}

            {isApps && !isLoading && !isError && projects.length === 0 && (
              <div className="flex items-center text-primary/60 text-lg h-[284px] px-6">
                Пока нет приложений — создайте первое.
              </div>
            )}

            {isApps &&
              projects.map((p) => (
                <ProjectCard
                  key={p.id}
                  project={p}
                  variant="apps"
                  isSelected={p.id === effectiveSelected}
                  onClick={() => setSelected(p.id)}
                  onDoubleClick={() => navigate(`/views?app=${p.id}`)}
                  onShareClick={() => { setSelected(p.id); setModal("share"); }}
                  onRename={() => handleRenameApp(p.id, p.name)}
                  onClone={() => handleOpenClone(p.id)}
                  onVersions={() => handleOpenVersions(p.id)}
                  onDelete={() => handleDeleteApp(p.id)}
                />
              ))}

            {!isApps && (
              <div className="flex items-center text-primary/60 text-lg h-[284px] px-6">
                Базы данных появятся здесь.
              </div>
            )}
          </div>
        </div>

        {/* Project row — left arrow */}
        {!projectAtStart && (
          <button
            onClick={() => scrollProjects(-1)}
            className="absolute flex items-center justify-center
                       bg-[rgba(152,155,159,0.4)] rounded-full cursor-pointer
                       hover:bg-[rgba(152,155,159,0.6)] transition-colors"
            style={{ left: 5, top: 210, width: 45, height: 45 }}
          >
            <svg viewBox="0 0 22 31" fill="none" className="w-[14px] h-[20px]">
              <path d="M18 2 L4 15.5 L18 29" stroke="rgba(64,64,64,0.6)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        )}

        {/* Project row — right arrow */}
        <button
          onClick={() => scrollProjects(1)}
          className="absolute flex items-center justify-center
                     bg-[rgba(152,155,159,0.4)] rounded-full cursor-pointer
                     hover:bg-[rgba(152,155,159,0.6)] transition-colors"
          style={{ left: 995, top: 210, width: 45, height: 45 }}
        >
          <svg viewBox="0 0 22 31" fill="none" className="w-[14px] h-[20px]">
            <path d="M4 2 L18 15.5 L4 29" stroke="rgba(64,64,64,0.6)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>

        {/* Section title */}
        <h2 className="absolute left-[40px] top-[396px] text-title font-semibold text-primary">
          {infoTitle}
        </h2>

        {/* Info cards row — scrollable */}
        <div
          className="absolute overflow-hidden"
          style={{ left: 40, top: 452, width: 940, height: 420 }}
        >
          <div
            ref={infoScrollRef}
            onScroll={onInfoScroll}
            className="flex gap-[65px]"
            style={{ overflowX: "scroll", overflowY: "hidden", height: 440 }}
          >
            {infoCards.map((card) => (
              <InfoCard key={card.id} card={card} />
            ))}
          </div>
        </div>

        {/* Info row — left arrow */}
        {!infoAtStart && (
          <button
            onClick={() => scrollInfo(-1)}
            className="absolute flex items-center justify-center
                       bg-[rgba(152,155,159,0.4)] rounded-full cursor-pointer
                       hover:bg-[rgba(152,155,159,0.6)] transition-colors"
            style={{ left: 5, top: 640, width: 45, height: 45 }}
          >
            <svg viewBox="0 0 22 31" fill="none" className="w-[14px] h-[20px]">
              <path d="M18 2 L4 15.5 L18 29" stroke="rgba(64,64,64,0.6)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        )}

        {/* Info row — right arrow */}
        <button
          onClick={() => scrollInfo(1)}
          className="absolute flex items-center justify-center
                     bg-[rgba(152,155,159,0.4)] rounded-full cursor-pointer
                     hover:bg-[rgba(152,155,159,0.6)] transition-colors"
          style={{ left: 985, top: 640, width: 45, height: 45 }}
        >
          <svg viewBox="0 0 22 31" fill="none" className="w-[14px] h-[20px]">
            <path d="M4 2 L18 15.5 L4 29" stroke="rgba(64,64,64,0.6)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>

        {/* Bottom CTA */}
        <button
          onClick={() => navigate(effectiveSelected ? `/schema?app=${effectiveSelected}` : "/schema")}
          className="absolute flex items-center justify-center gap-5
                     bg-cta rounded-btn text-[24px] font-medium text-white
                     hover:bg-active transition-colors cursor-pointer"
          style={{ left: "calc(50% - 165.5px)", top: 870, width: 331, height: 50 }}
        >
          Приступить к работе
        </button>
      </main>

      <PreviewPanel
        projectName={selected?.name ?? "Fitness App"}
        appId={effectiveSelected}
        onOpen={effectiveSelected ? () => navigate(`/views?app=${effectiveSelected}`) : undefined}
      />

      {/* Modals */}
      {modal === "create" && (
        <CreateProjectModal
          onClose={() => setModal(null)}
          onBlank={() => setModal("new-app")}
          onTemplate={() => setModal("from-template")}
          onModules={() => { setModal(null); navigate("/templates"); }}
        />
      )}
      {modal === "new-app" && (
        <NewAppModal
          onClose={() => setModal(null)}
          onConfirm={handleCreateApp}
          isSubmitting={createApp.isPending}
        />
      )}
      {modal === "from-template" && (
        <CreateFromTemplateModal
          onClose={() => setModal(null)}
          onConfirm={handleCreateFromTemplate}
          isSubmitting={templateSubmitting}
        />
      )}
      {modal === "share" && (
        <ShareModal onClose={() => setModal(null)} appId={effectiveSelected} />
      )}
      {modal === "roles" && (
        <RolesModal
          onClose={() => setModal(null)}
          projectName={selected?.name ?? "Дикая Сибирь"}
          appId={effectiveSelected}
        />
      )}
      {modal === "clone" && cloneTargetId && (
        <CloneAppModal
          onClose={() => { setModal(null); setCloneTargetId(null); }}
          onConfirm={handleCloneApp}
          sourceName={apps.find((a) => a.id === cloneTargetId)?.name ?? ""}
          isSubmitting={cloneAppMutation.isPending}
        />
      )}
      {modal === "versions" && versionsTargetId && (
        <AppVersionsModal
          onClose={() => { setModal(null); setVersionsTargetId(null); }}
          appId={versionsTargetId}
          appName={apps.find((a) => a.id === versionsTargetId)?.name ?? ""}
        />
      )}
    </div>
  );
}
