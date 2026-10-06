import { useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Navbar } from "@/components/layout/Navbar";
import { cn } from "@/lib/cn";
import { useAuthStore } from "@/shared/auth/store";
import {
  useArticles, useCategories, useArticle,
  useCreateArticle, useUpdateArticle, useDeleteArticle, useUploadArticleImage,
} from "@/shared/hooks/useKnowledge";
import type { ArticleListItem, ArticleRead } from "@/shared/api/knowledge";

export function KnowledgeBasePage() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.roles.some((r) => r.id === "platform_admin") ?? false;

  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(searchParams.get("article"));
  const [mode, setMode] = useState<"view" | "create" | "edit">("view");

  const articlesQ = useArticles({ category: category ?? undefined, q: search || undefined });
  const categoriesQ = useCategories();
  const articles = articlesQ.data ?? [];

  function openArticle(item: ArticleListItem) {
    setSelectedSlug(item.slug);
    setMode("view");
  }

  function backToList() {
    setSelectedSlug(null);
    setMode("view");
  }

  return (
    <div className="relative w-[1920px] h-[1080px] bg-white overflow-hidden">
      <Navbar />

      {/* ── Sidebar ── */}
      <aside
        className="absolute bg-white border-r border-cardbg overflow-y-auto"
        style={{ left: 0, top: 70, width: 320, height: 1010 }}
      >
        <div className="px-6 py-5">
          <h1 className="text-[22px] font-bold text-primary mb-4">База знаний</h1>
          <div className="relative mb-5">
            <input
              value={search}
              onChange={(e) => { setSearch(e.target.value); setSelectedSlug(null); }}
              placeholder="Поиск по статьям…"
              className="w-full h-[38px] pl-9 pr-3 rounded-[8px] border border-cardbg text-[14px] outline-none focus:border-cta"
            />
            <svg viewBox="0 0 16 16" className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-primary/30" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="7" cy="7" r="5" /><path d="M11 11l3 3" strokeLinecap="round" />
            </svg>
          </div>

          {isAdmin && (
            <button
              onClick={() => { setSelectedSlug(null); setMode("create"); }}
              className="w-full h-[38px] mb-5 rounded-[8px] bg-cta text-white text-[14px] font-medium hover:bg-cta/90"
            >
              + Новая статья
            </button>
          )}

          <p className="text-[12px] font-semibold text-primary/40 uppercase tracking-wide mb-2">Категории</p>
          <nav className="flex flex-col gap-1">
            <button
              onClick={() => { setCategory(null); setSelectedSlug(null); }}
              className={cn(
                "text-left px-3 py-2 rounded-[6px] text-[14px]",
                category === null ? "bg-[#EBF4FF] text-cta font-medium" : "text-primary hover:bg-mainbg",
              )}
            >
              Все статьи
            </button>
            {(categoriesQ.data ?? []).map((c) => (
              <button
                key={c}
                onClick={() => { setCategory(c); setSelectedSlug(null); }}
                className={cn(
                  "text-left px-3 py-2 rounded-[6px] text-[14px]",
                  category === c ? "bg-[#EBF4FF] text-cta font-medium" : "text-primary hover:bg-mainbg",
                )}
              >
                {c}
              </button>
            ))}
          </nav>
        </div>
      </aside>

      {/* ── Main ── */}
      <main className="absolute bg-mainbg overflow-y-auto" style={{ left: 320, top: 70, width: 1600, height: 1010 }}>
        {mode === "create" && (
          <ArticleEditor
            isAdmin={isAdmin}
            onDone={(slug) => { setSelectedSlug(slug); setMode("view"); }}
            onCancel={() => setMode("view")}
          />
        )}

        {mode !== "create" && !selectedSlug && (
          <div className="px-10 py-8">
            {articlesQ.isLoading && <p className="text-[14px] text-primary/40">Загрузка…</p>}
            {!articlesQ.isLoading && articles.length === 0 && (
              <div className="flex flex-col items-center justify-center py-24 text-center">
                <div className="text-[48px] mb-4">📚</div>
                <p className="text-[18px] font-semibold text-primary mb-2">
                  {search || category ? "Ничего не найдено" : "База знаний пока пуста"}
                </p>
                <p className="text-[14px] text-primary/50">
                  {isAdmin ? "Создайте первую статью." : "Загляните позже — контент добавляют администраторы."}
                </p>
              </div>
            )}
            <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
              {articles.map((item) => (
                <button
                  key={item.id}
                  onClick={() => openArticle(item)}
                  className="text-left bg-white border border-cardbg rounded-[12px] p-5 hover:border-cta/40 hover:shadow-sm transition-all"
                >
                  <div className="flex items-center gap-2 mb-2">
                    {item.category && (
                      <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-[#EBF4FF] text-cta">{item.category}</span>
                    )}
                    {!item.is_published && (
                      <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-mainbg text-primary/50">Черновик</span>
                    )}
                    {isAdmin && (
                      <span className="text-[11px] text-primary/35 ml-auto">#{item.display_order}</span>
                    )}
                  </div>
                  <p className="text-[15px] font-semibold text-primary mb-1.5">{item.title}</p>
                  <p className="text-[13px] text-primary/60 line-clamp-3">{item.excerpt}</p>
                </button>
              ))}
            </div>
          </div>
        )}

        {mode === "view" && selectedSlug && (
          <ArticleDetail
            slug={selectedSlug}
            isAdmin={isAdmin}
            onBack={backToList}
            onEdit={() => setMode("edit")}
            onDeleted={backToList}
          />
        )}

        {mode === "edit" && selectedSlug && (
          <ArticleEditor
            isAdmin={isAdmin}
            existingSlug={selectedSlug}
            onDone={(slug) => { setSelectedSlug(slug); setMode("view"); }}
            onCancel={() => setMode("view")}
          />
        )}
      </main>
    </div>
  );
}

/* ── Article detail (read) ── */
function ArticleDetail({
  slug, isAdmin, onBack, onEdit, onDeleted,
}: {
  slug: string; isAdmin: boolean; onBack: () => void; onEdit: () => void; onDeleted: () => void;
}) {
  const articleQ = useArticle(slug);
  const deleteMut = useDeleteArticle();
  const article: ArticleRead | undefined = articleQ.data;

  function handleDelete() {
    if (!article) return;
    if (!confirm(`Удалить статью «${article.title}»?`)) return;
    deleteMut.mutate(article.id, { onSuccess: onDeleted });
  }

  if (articleQ.isLoading) {
    return <div className="px-10 py-8 text-[14px] text-primary/40">Загрузка…</div>;
  }
  if (!article) {
    return (
      <div className="px-10 py-8">
        <p className="text-[14px] text-mistake">Статья не найдена.</p>
        <button onClick={onBack} className="text-[13px] text-cta hover:underline mt-2">← Назад к списку</button>
      </div>
    );
  }

  return (
    <div className="px-10 py-8 max-w-[900px]">
      <button onClick={onBack} className="text-[13px] text-cta hover:underline mb-4 flex items-center gap-1">
        ← Назад к списку
      </button>

      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          {article.category && (
            <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-[#EBF4FF] text-cta mb-2 inline-block">
              {article.category}
            </span>
          )}
          <h1 className="text-[26px] font-bold text-primary">{article.title}</h1>
          {!article.is_published && <p className="text-[12px] text-primary/40 mt-1">Черновик — не виден обычным пользователям</p>}
        </div>
        {isAdmin && (
          <div className="flex items-center gap-2 shrink-0">
            <button onClick={onEdit} className="h-[34px] px-3 rounded-[8px] border border-cardbg text-[13px] text-primary hover:bg-mainbg">
              Изменить
            </button>
            <button
              onClick={handleDelete}
              disabled={deleteMut.isPending}
              className="h-[34px] px-3 rounded-[8px] border border-[#FDECEC] text-[13px] text-mistake hover:bg-[#FDECEC]"
            >
              Удалить
            </button>
          </div>
        )}
      </div>

      <div
        className="bg-white border border-cardbg rounded-[12px] p-6 text-[14px] text-primary leading-relaxed kb-article-content"
        // Admin-authored HTML (ТЗ 3.12: текст/изображения/видео). Content is
        // only ever written by platform_admin — see api/v1/endpoints/knowledge.py.
        dangerouslySetInnerHTML={{ __html: article.content || "<p class='text-primary/40'>Пусто</p>" }}
      />
    </div>
  );
}

/* ── Article editor (create / edit) ── */
function ArticleEditor({
  isAdmin, existingSlug, onDone, onCancel,
}: {
  isAdmin: boolean; existingSlug?: string; onDone: (slug: string) => void; onCancel: () => void;
}) {
  const existingQ = useArticle(existingSlug);
  const createMut = useCreateArticle();
  const updateMut = useUpdateArticle(existingSlug ?? "");
  const uploadMut = useUploadArticleImage();
  const contentRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [title, setTitle] = useState(existingQ.data?.title ?? "");
  const [category, setCategoryField] = useState(existingQ.data?.category ?? "");
  const [displayOrder, setDisplayOrder] = useState(existingQ.data?.display_order ?? 0);
  const [content, setContent] = useState(existingQ.data?.content ?? "");
  const [isPublished, setIsPublished] = useState(existingQ.data?.is_published ?? true);
  const [initialized, setInitialized] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Populate the form once the existing article loads (edit mode).
  if (existingSlug && existingQ.data && !initialized) {
    setTitle(existingQ.data.title);
    setCategoryField(existingQ.data.category ?? "");
    setDisplayOrder(existingQ.data.display_order);
    setContent(existingQ.data.content);
    setIsPublished(existingQ.data.is_published);
    setInitialized(true);
  }

  if (!isAdmin) {
    return <div className="px-10 py-8 text-[14px] text-mistake">Недостаточно прав.</div>;
  }

  async function handleImagePick(file: File) {
    setError(null);
    try {
      const { url } = await uploadMut.mutateAsync({ file, articleId: existingQ.data?.id });
      const tag = `<img src="${url}" alt="" />`;
      const el = contentRef.current;
      if (el) {
        const pos = el.selectionStart ?? content.length;
        setContent(content.slice(0, pos) + tag + content.slice(pos));
      } else {
        setContent((c) => c + tag);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Не удалось загрузить изображение");
    }
  }

  async function handleSave() {
    setError(null);
    if (!title.trim()) { setError("Укажите заголовок"); return; }
    try {
      if (existingSlug) {
        const updated = await updateMut.mutateAsync({
          title, category: category || null, display_order: displayOrder, content, is_published: isPublished,
        });
        onDone(updated.slug);
      } else {
        const created = await createMut.mutateAsync({
          title, category: category || undefined, display_order: displayOrder, content, is_published: isPublished,
        });
        onDone(created.slug);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Не удалось сохранить статью");
    }
  }

  const saving = createMut.isPending || updateMut.isPending;

  return (
    <div className="px-10 py-8 max-w-[900px]">
      <h2 className="text-[22px] font-bold text-primary mb-6">{existingSlug ? "Изменить статью" : "Новая статья"}</h2>

      <div className="flex flex-col gap-4 bg-white border border-cardbg rounded-[12px] p-6">
        <div>
          <label className="text-[13px] font-medium text-primary block mb-1.5">Заголовок</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full h-[38px] px-3 rounded-[8px] border border-cardbg text-[14px] outline-none focus:border-cta"
          />
        </div>

        <div className="flex gap-4">
          <div className="flex-1">
            <label className="text-[13px] font-medium text-primary block mb-1.5">Категория</label>
            <input
              value={category}
              onChange={(e) => setCategoryField(e.target.value)}
              placeholder="Например: Правила, Импорт, Безопасность"
              className="w-full h-[38px] px-3 rounded-[8px] border border-cardbg text-[14px] outline-none focus:border-cta"
            />
          </div>
          <div className="w-[140px]">
            <label className="text-[13px] font-medium text-primary block mb-1.5">Порядок</label>
            <input
              type="number"
              value={displayOrder}
              onChange={(e) => setDisplayOrder(Number(e.target.value) || 0)}
              className="w-full h-[38px] px-3 rounded-[8px] border border-cardbg text-[14px] outline-none focus:border-cta"
            />
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-[13px] font-medium text-primary">Содержание (HTML)</label>
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadMut.isPending}
              className="text-[12px] text-cta hover:underline disabled:opacity-50"
            >
              {uploadMut.isPending ? "Загрузка…" : "+ Вставить изображение"}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleImagePick(f); e.target.value = ""; }}
            />
          </div>
          <textarea
            ref={contentRef}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={12}
            placeholder="<p>Текст статьи…</p>"
            className="w-full px-3 py-2 rounded-[8px] border border-cardbg text-[13px] font-mono outline-none focus:border-cta resize-y"
          />
        </div>

        {content && (
          <div>
            <p className="text-[12px] font-semibold text-primary/40 uppercase tracking-wide mb-2">Предпросмотр</p>
            <div
              className="border border-cardbg rounded-[8px] p-4 text-[14px] text-primary leading-relaxed kb-article-content"
              dangerouslySetInnerHTML={{ __html: content }}
            />
          </div>
        )}

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={isPublished}
            onChange={(e) => setIsPublished(e.target.checked)}
            className="w-[16px] h-[16px] accent-cta"
          />
          <span className="text-[13px] text-primary">Опубликовано (видно всем пользователям)</span>
        </label>

        {error && <div className="px-3 py-2 bg-[#FDECEC] text-mistake text-[13px] rounded-[8px]">{error}</div>}

        <div className="flex items-center gap-3 pt-2">
          <button
            onClick={handleSave}
            disabled={saving}
            className="h-[38px] px-6 rounded-[8px] bg-cta text-white text-[14px] font-medium hover:bg-cta/90 disabled:opacity-50"
          >
            {saving ? "Сохранение…" : "Сохранить"}
          </button>
          <button onClick={onCancel} className="h-[38px] px-5 rounded-[8px] border border-cardbg text-[14px] text-primary hover:bg-mainbg">
            Отмена
          </button>
        </div>
      </div>
    </div>
  );
}
