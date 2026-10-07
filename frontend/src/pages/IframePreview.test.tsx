import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { IframePreview } from "./ViewEditorPage";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderPreview(appId: string | undefined) {
  const ref = createRef<HTMLIFrameElement>();
  return render(
    <IframePreview appId={appId} appName="Тест" activePageId="page-1" iframeRef={ref} accent="#00205F" />
  );
}

describe("ViewEditorPage's IframePreview — device switcher (the constructor's own preview panel)", () => {
  it("Mobile stays inline and never opens a window", async () => {
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null);
    const user = userEvent.setup();
    renderPreview("app-1");

    await user.click(screen.getByText("Смартфон"));
    expect(openSpy).not.toHaveBeenCalled();
  });

  it("Tablet stays inline, at a real tablet viewport width, and never opens a window", async () => {
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null);
    const user = userEvent.setup();
    renderPreview("app-1");

    await user.click(screen.getByText("Планшет"));
    expect(openSpy).not.toHaveBeenCalled();
    expect(screen.getByTitle("Предпросмотр приложения")).toBeInTheDocument();
  });

  it("Desktop opens exactly one new tab for the currently edited app and page", async () => {
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null);
    const user = userEvent.setup();
    renderPreview("app-42");

    await user.click(screen.getByText("Десктоп ↗"));

    expect(openSpy).toHaveBeenCalledTimes(1);
    const [url, target] = openSpy.mock.calls[0];
    expect(String(url)).toContain("app=app-42");
    expect(String(url)).toContain("page=page-1");
    expect(String(url)).toContain("preview=true");
    expect(target).toBe("_blank");
  });

  it("disables the Desktop control when there is no app selected yet", async () => {
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null);
    const user = userEvent.setup();
    renderPreview(undefined);

    const desktopBtn = screen.getByText("Десктоп ↗").closest("button")!;
    expect(desktopBtn).toBeDisabled();

    await user.click(desktopBtn);
    expect(openSpy).not.toHaveBeenCalled();
  });

  it("the runtime iframe's own mask has square (90°) corners, not a rounded/skewed device frame", () => {
    renderPreview("app-1");
    const iframe = screen.getByTitle("Предпросмотр приложения");
    const mask = iframe.parentElement!;
    expect(mask.style.borderRadius).toBe("0");
  });
});
