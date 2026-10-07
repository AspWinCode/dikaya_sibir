import { useState } from "react";
import { TabSwitcher } from "@/components/ui/TabSwitcher";
import { buildRuntimeUrl } from "@/shared/lib/appLinks";

interface PreviewPanelProps {
  projectName?: string;
  appId?: string | null;
  onOpen?: () => void;
}

export function PreviewPanel({ projectName = "Fitness App", appId, onOpen }: PreviewPanelProps) {
  const [device, setDevice] = useState<"mobile" | "tablet">("mobile");
  const runtimeUrl = appId ? buildRuntimeUrl(appId, window.location.origin) : null;

  function handleDeviceChange(id: string) {
    if (id === "desktop") {
      if (runtimeUrl) window.open(runtimeUrl, "_blank", "noopener,noreferrer");
      return;
    }
    setDevice(id as "mobile" | "tablet");
  }

  const tabs = [
    {
      id: "mobile",
      label: "Смартфон",
      icon: (
        <svg viewBox="0 0 23 23" fill="none" className="w-full h-full">
          <rect x="4" y="1" width="15" height="21" rx="3" stroke="#00205F" strokeWidth="2"/>
          <circle cx="11.5" cy="18.5" r="1" fill="#00205F"/>
        </svg>
      ),
    },
    {
      id: "tablet",
      label: "Планшет",
      icon: (
        <svg viewBox="0 0 23 23" fill="none" className="w-full h-full">
          <rect x="3" y="1" width="17" height="21" rx="2" stroke="#00205F" strokeWidth="2"/>
          <circle cx="11.5" cy="18" r="0.8" fill="#00205F"/>
        </svg>
      ),
    },
    {
      id: "desktop",
      label: "Десктоп ↗",
      disabled: !runtimeUrl,
      title: runtimeUrl ? "Открыть в новой вкладке" : "Выберите приложение",
      icon: (
        <svg viewBox="0 0 23 23" fill="none" className="w-full h-full">
          <rect x="1" y="2" width="21" height="14" rx="2" stroke="#00205F" strokeWidth="2"/>
          <path d="M7 20 L16 20" stroke="#00205F" strokeWidth="2" strokeLinecap="round"/>
          <path d="M11.5 16 L11.5 20" stroke="#00205F" strokeWidth="2" strokeLinecap="round"/>
        </svg>
      ),
    },
  ];

  const FRAME_W: Record<typeof device, number> = { mobile: 380, tablet: 480 };
  // 0 — the app's own header must keep square (90°) corners, not be
  // clipped into a rounded/skewed shape by the device mockup frame.
  const OUTER_R: Record<typeof device, number> = { mobile: 0, tablet: 0 };
  const frameW = FRAME_W[device];
  const outerR = OUTER_R[device];

  return (
    <div
      className="absolute top-[70px] right-0 bottom-0 bg-mainbg flex flex-col items-center overflow-hidden"
      style={{
        width: 580,
        borderRadius: "5px 20px 20px 5px",
        paddingTop: 7,
      }}
    >
      {/* Device toggle */}
      <TabSwitcher
        tabs={tabs}
        activeId={device}
        onChange={handleDeviceChange}
        className="shrink-0"
      />

      {/* Preview frame — grows to fill available space */}
      <div className="flex-1 flex items-center justify-center w-full overflow-hidden py-[20px]">
        <div
          className="bg-cardbg overflow-hidden relative w-full h-full"
          style={{
            maxWidth: frameW,
            borderRadius: outerR,
            transition: "max-width 0.25s, border-radius 0.25s",
          }}
        >
          {runtimeUrl ? (
            // A mask div around the iframe, not border-radius on the iframe
            // itself — an iframe's content is its own compositing layer and
            // doesn't reliably clip to border-radius in every browser.
            <div style={{ width: "100%", height: "100%", borderRadius: outerR, overflow: "hidden" }}>
              <iframe
                key={`${appId}-${device}`}
                src={runtimeUrl}
                title={projectName}
                style={{ width: "100%", height: "100%", border: "none", display: "block" }}
                sandbox="allow-scripts allow-same-origin allow-forms"
              />
            </div>
          ) : (
            <div className="w-full h-full flex items-center justify-center text-primary/40 text-sm">
              Выберите приложение
            </div>
          )}
        </div>
      </div>

      {/* Open app button — always at bottom */}
      <div className="shrink-0 pb-5">
        <button
          onClick={onOpen}
          disabled={!onOpen}
          title={onOpen ? undefined : "Откройте предпросмотр из конструктора"}
          className="flex items-center justify-center gap-5 bg-cta text-white text-cta-lg
                     rounded-btn px-10 py-[10px] hover:bg-active transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ width: 331 }}
        >
          Открыть {projectName}
        </button>
      </div>
    </div>
  );
}
