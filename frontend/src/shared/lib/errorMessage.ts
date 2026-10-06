import { isAxiosError } from "axios";

/**
 * Turn an API/network error into a short Russian message safe to show a
 * user. Never forwards raw backend exception text (FastAPI `detail` is
 * English/technical and sometimes echoes internal exception strings) —
 * only status codes drive the mapping. `allowedDetail` is an opt-in
 * whitelist for endpoints that are known to return curated, user-facing
 * Russian strings (e.g. auth/password-reset flows).
 */
export function getFriendlyErrorMessage(
  err: unknown,
  opts?: { fallback?: string; allowedDetail?: boolean }
): string {
  const fallback = opts?.fallback ?? "Произошла ошибка. Попробуйте ещё раз.";

  if (!isAxiosError(err)) {
    return fallback;
  }

  if (!err.response) {
    return "Сервер недоступен. Проверьте подключение и попробуйте ещё раз.";
  }

  const status = err.response.status;
  const detail = (err.response.data as { detail?: unknown } | undefined)?.detail;

  // Even when the caller opts in to showing backend `detail`, only do so
  // when it looks like a curated, Russian, user-facing string — generic
  // validation/exception handlers return English technical text that must
  // never reach the user as-is.
  if (
    opts?.allowedDetail &&
    typeof detail === "string" &&
    detail.length > 0 &&
    /[а-яё]/i.test(detail)
  ) {
    return detail;
  }

  switch (status) {
    case 400:
    case 422:
      return "Проверьте правильность заполнения полей.";
    case 401:
      return "Сессия истекла. Войдите снова.";
    case 403:
      return "Недостаточно прав для этого действия.";
    case 404:
      return "Запись не найдена. Возможно, её уже удалили.";
    case 409:
      return "Данные были изменены другим пользователем. Обновите страницу и попробуйте снова.";
    case 429:
      return "Слишком много попыток. Подождите немного и повторите.";
    case 500:
    case 502:
    case 503:
    case 504:
      return "Сервер недоступен. Попробуйте повторить позже.";
    default:
      return fallback;
  }
}
