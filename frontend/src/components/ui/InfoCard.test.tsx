import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InfoCard } from "./InfoCard";

describe("InfoCard", () => {
  it("renders the headline figure, caption and a preview list, with an overflow note", () => {
    render(
      <InfoCard
        card={{
          id: "data",
          label: "Данные",
          content: "x",
          big: "7",
          caption: "таблиц · 48 полей",
          items: Array.from({ length: 7 }, (_, i) => ({ text: `Таблица ${i + 1}`, on: true })),
        }}
      />,
    );
    expect(screen.getByText("7")).toBeTruthy();
    expect(screen.getByText("таблиц · 48 полей")).toBeTruthy();
    expect(screen.getByText("Таблица 1")).toBeTruthy();
    expect(screen.getByText("Таблица 5")).toBeTruthy();
    expect(screen.queryByText("Таблица 6")).toBeNull();
    expect(screen.getByText("и ещё 2")).toBeTruthy();
  });

  it("falls back to the plain content text when no headline figure is given", () => {
    render(<InfoCard card={{ id: "t", label: "Данные", content: "Нет таблиц" }} />);
    expect(screen.getByText("Нет таблиц")).toBeTruthy();
  });

  it("opens the section on click, but not when the ⋮ button inside is clicked", () => {
    const onOpen = vi.fn();
    render(<InfoCard card={{ id: "d", label: "Данные", content: "x", big: "1", onOpen }} />);
    fireEvent.click(screen.getByText("1"));
    expect(onOpen).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button"));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});
