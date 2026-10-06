import { useEffect, type ReactNode } from "react";
import { cn } from "@/lib/cn";

/* ─────────────────────────────────────────────────
   SHARED MODAL PRIMITIVES
   Single source of truth for overlay/close/button chrome.
   Previously this block was copy-pasted into every file in
   this folder; keep behavior consistent by editing only here.
───────────────────────────────────────────────── */

/** Dark overlay backdrop. Closes on Escape and backdrop click,
 *  unless `busy` (a submit is in flight) — then both are disabled
 *  so an accidental dismiss can't orphan a pending request. */
export function Overlay({
  onClose,
  children,
  alignTop = false,
  topOffset = 85,
  busy = false,
}: {
  onClose: () => void;
  children: ReactNode;
  alignTop?: boolean;
  topOffset?: number;
  busy?: boolean;
}) {
  useEffect(() => {
    if (busy) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose, busy]);

  return (
    <div
      className="absolute inset-0 z-50 flex justify-center"
      style={{ background: "rgba(0, 32, 95, 0.5)", alignItems: alignTop ? "flex-start" : "center" }}
      onClick={busy ? undefined : onClose}
    >
      <div
        className="bg-mainbg rounded-[10px] shadow-[0_4px_4px_rgba(0,0,0,0.25)] overflow-visible"
        style={alignTop ? { marginTop: topOffset } : {}}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

export function CloseBtn({ onClick, disabled }: { onClick: () => void; disabled?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label="Закрыть"
      className="w-7 h-7 shrink-0 hover:opacity-70 transition-opacity disabled:opacity-40 disabled:cursor-default"
    >
      <svg viewBox="0 0 28 28" fill="none" className="w-full h-full">
        <line x1="7" y1="7" x2="21" y2="21" stroke="#00205F" strokeWidth="2" strokeLinecap="round" />
        <line x1="21" y1="7" x2="7" y2="21" stroke="#00205F" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </button>
  );
}

/** Blue pill input/field container */
export function BlueField({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("w-full h-[41px] bg-cardbg rounded-btn flex items-center px-5 relative", className)}>
      {children}
    </div>
  );
}

/** Bottom action buttons. `disabled` blocks both buttons (used while a
 *  submit is in flight, so a double click can't fire the mutation twice). */
export function ModalButtons({
  onCancel,
  onConfirm,
  confirmLabel,
  disabled,
  loading,
}: {
  onCancel: () => void;
  onConfirm: () => void;
  confirmLabel: string;
  disabled?: boolean;
  loading?: boolean;
}) {
  return (
    <div className="flex justify-end gap-[10px]">
      <button
        onClick={onCancel}
        disabled={loading}
        className="px-5 py-[3px] h-[34px] border-2 border-cta rounded-btn text-cta text-meta
                   hover:bg-cta/10 transition-colors disabled:opacity-60 disabled:cursor-default"
      >
        Отмена
      </button>
      <button
        onClick={onConfirm}
        disabled={disabled}
        className="px-5 py-[3px] h-[34px] bg-cta border-2 border-cta rounded-btn text-white text-meta
                   hover:bg-active transition-colors disabled:opacity-60 disabled:cursor-default"
      >
        {loading ? "Подождите…" : confirmLabel}
      </button>
    </div>
  );
}

/** Inline banner for API errors inside a modal. Never pass raw backend
 *  exception text here — run it through getFriendlyErrorMessage first. */
export function ModalError({ message }: { message: string | null | undefined }) {
  if (!message) return null;
  return (
    <p className="text-[13px] text-mistake leading-snug" role="alert">
      {message}
    </p>
  );
}
