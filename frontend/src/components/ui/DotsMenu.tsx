import { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";

/** Three-dot context menu trigger with dropdown.
 *
 * The dropdown is rendered through a portal and positioned with `fixed`
 * coordinates computed from the trigger's bounding box, so it is never
 * clipped by a scrollable/overflow-hidden ancestor (e.g. the horizontal
 * card rows on MainPage). */
export function DotsMenu({
  className,
  onShare,
  onRename,
  onClone,
  onVersions,
  onDelete,
}: {
  className?: string;
  onShare?: () => void;
  onRename?: () => void;
  onClone?: () => void;
  onVersions?: () => void;
  onDelete?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<{ top: number; right: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const handlePointer = (e: MouseEvent) => {
      const target = e.target as Node;
      if (menuRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      setOpen(false);
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  function toggle(e: React.MouseEvent) {
    e.stopPropagation();
    if (!open && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      setCoords({ top: rect.bottom + 4, right: window.innerWidth - rect.right });
    }
    setOpen((v) => !v);
  }

  return (
    <div className={`relative shrink-0 ${className ?? ""}`}>
      <button
        ref={triggerRef}
        className="flex flex-col justify-center items-center gap-[2.67px] w-5 h-5"
        onClick={toggle}
        aria-label="Меню"
      >
        {[0, 1, 2].map((i) => (
          <span key={i} className="w-1 h-1 rounded-full bg-primary" />
        ))}
      </button>

      {open && coords &&
        createPortal(
          <div
            ref={menuRef}
            className="fixed z-[100] bg-mainbg rounded-[10px]
                       shadow-[0_4px_12px_rgba(0,32,95,0.15)] overflow-hidden min-w-[180px]"
            style={{ top: coords.top, right: coords.right }}
            onClick={(e) => e.stopPropagation()}
          >
            {onShare && (
              <button
                onClick={() => { setOpen(false); onShare(); }}
                className="w-full text-left px-4 py-2 text-meta text-primary hover:bg-cardbg transition-colors"
              >
                Поделиться
              </button>
            )}
            {onRename && (
              <button
                onClick={() => { setOpen(false); onRename(); }}
                className="w-full text-left px-4 py-2 text-meta text-primary hover:bg-cardbg transition-colors"
              >
                Переименовать
              </button>
            )}
            {onClone && (
              <button
                onClick={() => { setOpen(false); onClone(); }}
                className="w-full text-left px-4 py-2 text-meta text-primary hover:bg-cardbg transition-colors"
              >
                Клонировать
              </button>
            )}
            {onVersions && (
              <button
                onClick={() => { setOpen(false); onVersions(); }}
                className="w-full text-left px-4 py-2 text-meta text-primary hover:bg-cardbg transition-colors"
              >
                История версий
              </button>
            )}
            {onDelete && (
              <button
                onClick={() => { setOpen(false); onDelete(); }}
                className="w-full text-left px-4 py-2 text-meta text-[#C22A2A] hover:bg-cardbg transition-colors"
              >
                Удалить
              </button>
            )}
          </div>,
          document.body
        )}
    </div>
  );
}
