import { useNavigate } from "react-router-dom";
import { useArticles } from "@/shared/hooks/useKnowledge";
import type { ArticleListItem } from "@/shared/api/knowledge";

/** Categories the «Обучение» screen is built from (see LearningPage). */
export const LEARNING_CATEGORY = "Обучение";
export const NEXT_STEPS_CATEGORY = "Следующие шаги";

function Group({ title, hint, category }: { title: string; hint: string; category: string }) {
  const navigate = useNavigate();
  const q = useArticles({ category });
  const items: ArticleListItem[] = q.data ?? [];

  return (
    <section className="bg-white rounded-[12px] border border-cardbg p-6 mb-6">
      <div className="flex items-start justify-between gap-4 mb-1">
        <div>
          <h2 className="text-[18px] font-semibold text-primary">{title}</h2>
          <p className="text-[13px] text-primary/50 mt-1">{hint}</p>
        </div>
        <button
          onClick={() => navigate(`/knowledge-base?new=1&category=${encodeURIComponent(category)}`)}
          className="shrink-0 h-[36px] px-4 rounded-[8px] bg-cta text-white text-[14px] font-medium hover:bg-cta/90"
        >
          + Добавить
        </button>
      </div>

      {q.isLoading && <p className="text-[13px] text-primary/40 mt-4">Загрузка…</p>}

      {!q.isLoading && items.length === 0 && (
        <p className="text-[13px] text-primary/40 mt-4 border border-dashed border-cardbg rounded-[10px] p-4 text-center">
          Пока ничего нет. Нажмите «+ Добавить».
        </p>
      )}

      {items.length > 0 && (
        <ul className="mt-4 divide-y divide-cardbg">
          {items.map((a) => (
            <li key={a.id} className="flex items-center gap-3 py-2.5">
              <span className="w-8 text-[12px] text-primary/40 tabular-nums">#{a.display_order}</span>
              <div className="min-w-0 flex-1">
                <p className="text-[14px] font-medium text-primary truncate">{a.title}</p>
                {a.excerpt && <p className="text-[12px] text-primary/50 truncate">{a.excerpt}</p>}
              </div>
              <span
                className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${
                  a.is_published ? "bg-green-50 text-green-600" : "bg-mainbg text-primary/50"
                }`}
              >
                {a.is_published ? "Опубликовано" : "Черновик"}
              </span>
              <button
                onClick={() => navigate(`/knowledge-base?article=${encodeURIComponent(a.slug)}&edit=1`)}
                className="text-[13px] font-medium text-cta hover:underline"
              >
                Изменить
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Admin-panel section where a platform admin fills in the «Обучение» screen. */
export function AdminLearning() {
  const navigate = useNavigate();
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h1 className="text-[24px] font-bold text-primary">Обучение</h1>
        <button onClick={() => navigate("/learning")} className="text-[14px] font-medium text-cta hover:underline">
          Открыть страницу «Обучение» →
        </button>
      </div>
      <p className="text-[14px] text-primary/60 mb-6 max-w-[900px]">
        Здесь заполняется экран «Обучение», который видят пользователи платформы. Карточки «Следующие шаги» и
        «Обучающие материалы» — это статьи; порядок задаёт число «Порядок», а черновики пользователям не видны.
      </p>

      <Group
        title="Предлагаемые следующие шаги"
        hint="Короткие карточки с заголовком и описанием вверху экрана."
        category={NEXT_STEPS_CATEGORY}
      />
      <Group
        title="Обучающие материалы"
        hint="Статьи и инструкции в нижней части экрана."
        category={LEARNING_CATEGORY}
      />
    </div>
  );
}
