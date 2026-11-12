import { isAxiosError } from "axios";
import { getFriendlyErrorMessage } from "./errorMessage";

const TRANSLIT: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z", и: "i", й: "y", к: "k",
  л: "l", м: "m", н: "n", о: "o", п: "p", р: "r", с: "s", т: "t", у: "u", ф: "f", х: "kh", ц: "ts",
  ч: "ch", ш: "sh", щ: "sch", ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya",
};

/** "ООО Ромашка №1" -> "ooo-romashka-1": the ID format the API accepts
 * (lowercase latin letters, digits, "-" and "_"). */
export function slugify(input: string): string {
  const latin = input
    .toLowerCase()
    .split("")
    .map((ch) => (ch in TRANSLIT ? TRANSLIT[ch] : ch))
    .join("");
  return latin
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^[-_]+|[-_]+$/g, "")
    .slice(0, 128);
}

export const SLUG_RE = /^[a-z0-9_-]{2,128}$/;
export const MIN_PASSWORD = 10;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export interface OrgFormValues {
  display_name: string;
  slug: string;
  admin_email: string;
  admin_display_name: string;
  admin_password: string;
}

export type OrgFormErrors = Partial<Record<keyof OrgFormValues, string>>;

/** Client-side mirror of the API rules, so the user is told which field is wrong. */
export function validateOrgForm(v: OrgFormValues): OrgFormErrors {
  const e: OrgFormErrors = {};
  if (v.display_name.trim().length < 2) e.display_name = "Введите название (не короче 2 символов)";
  if (!SLUG_RE.test(v.slug)) {
    e.slug = "ID: 2–128 символов, только строчная латиница, цифры, «-» и «_» (например, romashka)";
  }
  if (!EMAIL_RE.test(v.admin_email.trim())) e.admin_email = "Введите корректный email администратора";
  if (v.admin_display_name.trim().length < 2) e.admin_display_name = "Введите имя администратора";
  if (v.admin_password.length < MIN_PASSWORD) e.admin_password = `Пароль — не менее ${MIN_PASSWORD} символов`;
  return e;
}

const FIELD_LABEL: Record<string, string> = {
  display_name: "Название организации",
  slug: "ID (slug)",
  plan: "Тариф",
  admin_email: "Email администратора",
  admin_display_name: "Имя администратора",
  admin_password: "Пароль администратора",
};

/** Human-readable reason for a failed "create organisation" request. */
export function orgCreateErrorMessage(err: unknown): string {
  if (isAxiosError(err) && err.response) {
    const { status, data } = err.response as { status: number; data?: { detail?: unknown } };
    const detail = data?.detail;

    if (status === 409 && typeof detail === "string") {
      if (/slug/i.test(detail)) return "Организация с таким ID (slug) уже существует. Выберите другой.";
      if (/email/i.test(detail)) return "Пользователь с такой почтой уже зарегистрирован.";
    }
    if (status === 403) return "Недостаточно прав: создавать организации может только администратор платформы.";
    if (status === 422 && Array.isArray(detail)) {
      const fields = detail
        .map((d) => (d as { loc?: unknown[] }).loc?.[1])
        .filter((f): f is string => typeof f === "string")
        .map((f) => FIELD_LABEL[f] ?? f);
      if (fields.length) return `Проверьте поля: ${[...new Set(fields)].join(", ")}.`;
      return "Проверьте введённые данные.";
    }
  }
  return getFriendlyErrorMessage(err, { fallback: "Не удалось создать организацию. Попробуйте ещё раз." });
}
