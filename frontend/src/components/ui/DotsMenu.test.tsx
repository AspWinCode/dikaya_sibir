import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DotsMenu } from "./DotsMenu";

describe("DotsMenu", () => {
  it("renders the dropdown via a portal onto document.body, so an overflow-hidden ancestor can't clip it", async () => {
    const onDelete = vi.fn();
    const user = userEvent.setup();

    const { container } = render(
      <div style={{ overflow: "hidden", height: 10, width: 10 }}>
        <DotsMenu onDelete={onDelete} onRename={() => {}} />
      </div>
    );

    await user.click(screen.getByLabelText("Меню"));

    const item = await screen.findByText("Удалить");
    // The dropdown must NOT be inside the clipping container.
    expect(container.contains(item)).toBe(false);
    expect(item.closest("body")).toBe(document.body);

    await user.click(item);
    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    render(<DotsMenu onRename={() => {}} />);
    await user.click(screen.getByLabelText("Меню"));
    expect(await screen.findByText("Переименовать")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByText("Переименовать")).not.toBeInTheDocument();
  });
});
