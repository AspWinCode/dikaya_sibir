import { useState } from "react";
import { Link } from "react-router-dom";
import { Navbar } from "@/components/layout/Navbar";
import { IconRail, type RailModule } from "@/components/layout/IconRail";
import { PreviewPanel } from "@/components/layout/PreviewPanel";
import { useAuthStore } from "@/shared/auth/store";
import { useArticles } from "@/shared/hooks/useKnowledge";

const LEARNING_CATEGORY = "Обучение";
const NEXT_STEPS_CATEGORY = "Следующие шаги";

export function LearningPage() {
  const isPlatformAdmin = useAuthStore((s) => s.user?.roles.some((r) => r.id === "platform_admin") ?? false);
  const articlesQ = useArticles({ category: LEARNING_CATEGORY });
  const articles = articlesQ.data ?? [];
  const stepsQ = useArticles({ category: NEXT_STEPS_CATEGORY });
  const steps = stepsQ.data ?? [];

  const [railModule, setRailModule] = useState<RailModule>("docs");

  return (
    <div className="relative w-[1920px] h-[1080px] bg-white overflow-hidden">
      <Navbar />
      <IconRail active={railModule} onChange={setRailModule} />

      {/* Main content */}
      <main
        className="absolute bg-mainbg overflow-y-auto"
        style={{ left: 85, top: 70, width: 1250, height: 1010 }}
      >
        <div className="px-10 py-8">
          <h1 className="text-[28px] font-bold text-primary mb-8">Обучение</h1>

          {/* Suggested next steps — admin-editable Knowledge Base articles
              (category "Следующие шаги"), same mechanism as the materials
              section below. Order and visibility come from the article's
              own display_order / is_published fields. */}
          <section className="mb-10">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[18px] font-semibold text-primary">Предлагаемые следующие шаги</h2>
              {isPlatformAdmin && (
                <Link to="/knowledge-base" className="text-[13px] font-medium text-cta hover:underline">
                  + Добавить шаг
                </Link>
              )}
            </div>

            {stepsQ.isLoading && <p className="text-[13px] text-primary/40">Загрузка…</p>}

            {!stepsQ.isLoading && steps.length === 0 && (
              <div className="border border-dashed border-cardbg rounded-[10px] p-6 text-center">
                <p className="text-[13px] text-primary/40">
                  {isPlatformAdmin
                    ? "Шагов пока нет. Добавьте статьи в базе знаний с категорией «Следующие шаги»."
                    : "Шаги появятся здесь, когда администратор их добавит."}
                </p>
              </div>
            )}

            {steps.length > 0 && (
              <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
                {steps.map((step, i) => (
                  <Link
                    key={step.id}
                    to={`/knowledge-base?article=${step.slug}`}
                    className="text-left border border-cardbg bg-white rounded-[10px] p-5 hover:border-cta/40 hover:shadow-sm transition-all"
                  >
                    <div className="flex items-start gap-3">
                      <span className="w-6 h-6 shrink-0 mt-0.5 rounded-full bg-[#EBF4FF] text-cta text-[13px] font-bold flex items-center justify-center">
                        {i + 1}
                      </span>
                      <div>
                        <p className="text-[15px] font-semibold mb-1 text-cta">{step.title}</p>
                        <p className="text-[13px] text-primary/60 line-clamp-2">{step.excerpt}</p>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </section>

          {/* How AppSheet works */}
          <section className="mb-10">
            <h2 className="text-[18px] font-semibold text-primary mb-5">Как работает Лесовик</h2>
            <div className="flex items-center gap-0">
              {[
                { num: 1, label: "Данные",       icon: "🗄️" },
                { num: 2, label: "Интерфейс",    icon: "📱" },
                { num: 3, label: "Автоматизация",icon: "⚡" },
                { num: 4, label: "Публикация",   icon: "🚀" },
              ].map((step, i) => (
                <div key={step.num} className="flex items-center">
                  <div className="flex flex-col items-center gap-2 w-[180px]">
                    <div className="w-14 h-14 bg-white border-2 border-cta/20 rounded-full flex items-center justify-center text-2xl">
                      {step.icon}
                    </div>
                    <div className="text-center">
                      <div className="w-7 h-7 rounded-full bg-cta text-white text-[13px] font-bold flex items-center justify-center mx-auto mb-1">
                        {step.num}
                      </div>
                      <p className="text-[14px] font-medium text-primary">{step.label}</p>
                    </div>
                  </div>
                  {i < 3 && (
                    <svg viewBox="0 0 40 20" className="w-10 h-5 text-cta/30 mx-1" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M0 10h36M30 4l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* Learning articles — pulled from the knowledge base (category "Обучение"),
              editable by a platform admin from the Knowledge Base page. */}
          <section>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[18px] font-semibold text-primary">Обучающие материалы</h2>
              {isPlatformAdmin && (
                <Link
                  to="/knowledge-base"
                  className="text-[13px] font-medium text-cta hover:underline"
                >
                  + Добавить материал
                </Link>
              )}
            </div>

            {articlesQ.isLoading && <p className="text-[13px] text-primary/40">Загрузка…</p>}

            {!articlesQ.isLoading && articles.length === 0 && (
              <div className="border border-dashed border-cardbg rounded-[10px] p-8 text-center">
                <p className="text-[14px] text-primary/60 mb-1">Обучающих материалов пока нет</p>
                <p className="text-[13px] text-primary/40">
                  {isPlatformAdmin
                    ? "Добавьте статьи в базе знаний с категорией «Обучение» — они появятся здесь."
                    : "Обратитесь к администратору платформы, чтобы их добавили."}
                </p>
              </div>
            )}

            {articles.length > 0 && (
              <div className="grid gap-5" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
                {articles.map((article) => (
                  <Link
                    key={article.id}
                    to={`/knowledge-base?article=${article.slug}`}
                    className="bg-white border border-cardbg rounded-[10px] overflow-hidden hover:shadow-md transition-shadow"
                  >
                    <div className="h-[100px] bg-mainbg flex items-center justify-center">
                      <svg viewBox="0 0 24 24" className="w-8 h-8 text-cta/30" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <path d="M4 4h16v16H4z" strokeLinejoin="round" />
                        <path d="M8 9h8M8 13h8M8 17h4" strokeLinecap="round" />
                      </svg>
                    </div>
                    <div className="p-4">
                      <p className="text-[14px] font-semibold text-cta mb-1">{article.title}</p>
                      <p className="text-[12px] text-primary/60 line-clamp-2">{article.excerpt}</p>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </section>
        </div>
      </main>

      <PreviewPanel projectName="Дикая Сибирь" />
    </div>
  );
}
