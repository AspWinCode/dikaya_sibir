import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AdminLearning } from "./AdminLearning";

vi.mock("@/shared/hooks/useKnowledge", () => ({
  useArticles: ({ category }: { category: string }) => ({
    isLoading: false,
    data:
      category === "Обучение"
        ? [{ id: "1", slug: "kak-nachat", title: "Как начать", excerpt: "Первые шаги", category, display_order: 2, is_published: true, updated_at: "" }]
        : [],
  }),
}));

function Where() {
  const l = useLocation();
  return <div data-testid="where">{l.pathname + l.search}</div>;
}

function renderIt() {
  return render(
    <MemoryRouter initialEntries={["/admin"]}>
      <Routes>
        <Route path="/admin" element={<AdminLearning />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AdminLearning", () => {
  it("lists existing materials and shows an empty state for a category without articles", () => {
    renderIt();
    expect(screen.getByText("Как начать")).toBeTruthy();
    expect(screen.getByText("Опубликовано")).toBeTruthy();
    expect(screen.getByText("Пока ничего нет. Нажмите «+ Добавить».")).toBeTruthy();
  });

  it("opens the article editor with the right category preset", () => {
    renderIt();
    fireEvent.click(screen.getAllByText("+ Добавить")[0]);
    expect(decodeURIComponent(screen.getByTestId("where").textContent ?? "")).toBe(
      "/knowledge-base?new=1&category=Следующие шаги",
    );
  });

  it("opens an existing article straight in edit mode", () => {
    renderIt();
    fireEvent.click(screen.getByText("Изменить"));
    expect(screen.getByTestId("where").textContent).toBe("/knowledge-base?article=kak-nachat&edit=1");
  });
});
