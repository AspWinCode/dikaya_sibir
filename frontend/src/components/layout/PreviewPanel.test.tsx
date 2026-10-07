import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PreviewPanel } from "./PreviewPanel";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("PreviewPanel — device switcher", () => {
  it("Mobile stays inline and never opens a window", async () => {
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null);
    const user = userEvent.setup();
    render(<PreviewPanel appId="app-1" />);

    await user.click(screen.getByText("Смартфон"));
    expect(openSpy).not.toHaveBeenCalled();
  });

  it("Tablet stays inline and never opens a window", async () => {
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null);
    const user = userEvent.setup();
    render(<PreviewPanel appId="app-1" />);

    await user.click(screen.getByText("Планшет"));
    expect(openSpy).not.toHaveBeenCalled();
  });

  it("Desktop opens exactly one new tab with the current app's runtime URL", async () => {
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null);
    const user = userEvent.setup();
    render(<PreviewPanel appId="app-42" />);

    await user.click(screen.getByText("Десктоп ↗"));

    expect(openSpy).toHaveBeenCalledTimes(1);
    const [url, target] = openSpy.mock.calls[0];
    expect(String(url)).toContain("app=app-42");
    expect(target).toBe("_blank");
  });

  it("disables the Desktop control when there is no app yet", async () => {
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null);
    const user = userEvent.setup();
    render(<PreviewPanel appId={null} />);

    const desktopBtn = screen.getByText("Десктоп ↗").closest("button")!;
    expect(desktopBtn).toBeDisabled();

    await user.click(desktopBtn);
    expect(openSpy).not.toHaveBeenCalled();
  });

  it("the runtime iframe's own mask has square (90°) corners, not a rounded/skewed frame", () => {
    render(<PreviewPanel appId="app-1" />);
    const iframe = screen.getByTitle("Fitness App");
    const mask = iframe.parentElement!;
    expect(mask.style.borderRadius).toBe("0");
  });
});
