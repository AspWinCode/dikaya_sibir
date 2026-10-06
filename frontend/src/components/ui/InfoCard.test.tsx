import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { InfoCard } from "./InfoCard";

describe("InfoCard", () => {
  it("keeps the label badge inset within the card instead of a fixed width that could overflow it", () => {
    render(
      <InfoCard
        card={{ id: "1", content: "Содержимое карточки", label: "Очень длинное название метки для проверки" }}
      />
    );
    const badge = screen.getByText("Очень длинное название метки для проверки").parentElement;
    expect(badge?.className).toContain("left-[25px]");
    expect(badge?.className).toContain("right-[25px]");
    // No fixed width class that could push the badge past the card edge.
    expect(badge?.className).not.toMatch(/\bw-\[\d+px\]/);
  });
});
