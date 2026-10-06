import { useHealth } from "../hooks/useHealth";

export function StatusBanner() {
  const { data, isError } = useHealth();

  if (isError || data?.ready === false) {
    return (
      <div
        style={{
          background: "#fee2e2",
          color: "#991b1b",
          padding: "8px 16px",
          fontSize: 13,
          textAlign: "center",
        }}
      >
        {isError ? "Сервер недоступен." : "Сервис временно недоступен. Попробуйте обновить страницу."}
      </div>
    );
  }

  return null;
}
