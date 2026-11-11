import { DotsMenu } from "./DotsMenu";

export interface InfoCardItem {
  text: string;
  /** Renders the bullet in a "good" colour (published / active / on). */
  on?: boolean;
}

export interface InfoCardData {
  id: string;
  content: string;
  label: string;
  icon?: React.ReactNode;
  /** Headline figure shown large at the top of the card (e.g. "18"). When set,
   * the card renders big/caption/items instead of the plain `content` text. */
  big?: string;
  /** Small line under the headline figure (e.g. "таблиц · 48 полей"). */
  caption?: string;
  /** Up to a few short lines previewing what's inside. */
  items?: InfoCardItem[];
  /** Makes the whole card clickable (opens the matching section). */
  onOpen?: () => void;
}

interface InfoCardProps {
  card: InfoCardData;
}

const MAX_ITEMS = 5;

export function InfoCard({ card }: InfoCardProps) {
  const rich = card.big !== undefined;
  const items = (card.items ?? []).slice(0, MAX_ITEMS);
  const extra = (card.items?.length ?? 0) - items.length;

  return (
    <div
      className={`relative w-[250px] h-[400px] shrink-0${card.onOpen ? " cursor-pointer group" : ""}`}
      role={card.onOpen ? "link" : undefined}
      tabIndex={card.onOpen ? 0 : undefined}
      onClick={(e) => {
        // Clicks on the card's own controls (the ⋮ menu) must not navigate.
        if (card.onOpen && !(e.target as HTMLElement).closest("button")) card.onOpen();
      }}
      onKeyDown={(e) => {
        if (card.onOpen && e.key === "Enter") card.onOpen();
      }}
    >
      {/* Background */}
      <div className="absolute inset-0 bg-cardbg rounded-card transition-colors group-hover:bg-[#BFDCFF]" />

      {rich ? (
        <div className="absolute left-[25px] right-[25px] top-[28px] bottom-[120px] flex flex-col overflow-hidden">
          <span className="text-[52px] font-bold leading-[110%] text-primary">{card.big}</span>
          {card.caption && (
            <span className="mt-1 text-[15px] leading-[130%] text-primary/70">{card.caption}</span>
          )}
          {items.length > 0 && (
            <ul className="mt-4 flex flex-col gap-[7px]">
              {items.map((it, i) => (
                <li key={i} className="flex items-center gap-2 min-w-0 text-[14px] leading-[130%] text-primary">
                  <span
                    className={`w-[7px] h-[7px] rounded-full shrink-0 ${it.on ? "bg-green-500" : "bg-primary/30"}`}
                  />
                  <span className="truncate">{it.text}</span>
                </li>
              ))}
              {extra > 0 && <li className="text-[13px] text-primary/60 pl-[15px]">и ещё {extra}</li>}
            </ul>
          )}
        </div>
      ) : (
        /* Content text */
        <p className="absolute left-[25px] top-[80px] w-[200px] text-info text-primary leading-[120%] whitespace-pre-line">
          {card.content}
        </p>
      )}

      {/* Label badge — left/right inset instead of a fixed width so it can
          never extend past the card regardless of card width changes. */}
      <div className="absolute left-[25px] right-[25px] bottom-[53px] flex items-center justify-between
                      bg-mainbg rounded-badge px-[15px] py-[10px] gap-2 h-[50px]">
        <span className="text-card-h font-semibold text-primary truncate min-w-0">{card.label}</span>
        {card.icon ? (
          <span className="w-5 h-5 shrink-0">{card.icon}</span>
        ) : (
          <DotsMenu />
        )}
      </div>
    </div>
  );
}
