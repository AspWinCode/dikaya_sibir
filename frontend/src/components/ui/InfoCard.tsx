import { DotsMenu } from "./DotsMenu";

export interface InfoCardData {
  id: string;
  content: string;
  label: string;
  icon?: React.ReactNode;
}

interface InfoCardProps {
  card: InfoCardData;
}

export function InfoCard({ card }: InfoCardProps) {
  return (
    <div className="relative w-[250px] h-[400px] shrink-0">
      {/* Background */}
      <div className="absolute inset-0 bg-cardbg rounded-card" />

      {/* Content text */}
      <p className="absolute left-[25px] top-[80px] w-[200px] text-info text-primary leading-[120%] whitespace-pre-line">
        {card.content}
      </p>

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
