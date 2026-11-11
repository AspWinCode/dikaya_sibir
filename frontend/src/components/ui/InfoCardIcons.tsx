/** Small line icons for the «Информация о проекте» cards (replace the ⋮ menu). */

const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "#00205F",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  className: "w-full h-full",
  "aria-hidden": true,
};

/** Данные — database cylinder. */
export function DataCardIcon() {
  return (
    <svg {...base}>
      <ellipse cx="12" cy="5.5" rx="7" ry="2.8" />
      <path d="M5 5.5v13c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8v-13" />
      <path d="M5 12c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8" />
    </svg>
  );
}

/** Интерфейс — a screen with a layout grid. */
export function InterfaceCardIcon() {
  return (
    <svg {...base}>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <path d="M3 9h18" />
      <path d="M9 9v11" />
    </svg>
  );
}

/** Безопасность — shield with a check. */
export function SecurityCardIcon() {
  return (
    <svg {...base}>
      <path d="M12 3l7.5 3v5.5c0 4.5-3.1 8.2-7.5 9.5-4.4-1.3-7.5-5-7.5-9.5V6L12 3z" />
      <path d="M8.7 12.2l2.3 2.3 4.3-4.6" />
    </svg>
  );
}

/** Автоматизация — lightning bolt. */
export function AutomationCardIcon() {
  return (
    <svg {...base}>
      <path d="M13 2.5L4.5 13.5H11l-1 8 8.5-11H12l1-8z" />
    </svg>
  );
}
