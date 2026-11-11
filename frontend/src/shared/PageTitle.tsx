import { useEffect } from "react";
import { Navigate, useLocation } from "react-router-dom";

const BRAND = "Лесовик";

/** Human-readable tab titles per route (the SPA used to show the same
 * technical "No-Code Platform — App Builder" on every page). */
export const PAGE_TITLES: Record<string, string> = {
  "/landing": "",
  "/signin": "Вход",
  "/signup": "Регистрация",
  "/forgot-password": "Восстановление пароля",
  "/reset-password": "Новый пароль",
  "/change-password": "Смена пароля",
  "/invite": "Приглашение",
  "/": "Проекты",
  "/admin": "Администрирование",
  "/views": "Конструктор",
  "/data": "Источники данных",
  "/actions": "Действия",
  "/bot": "Автоматизация",
  "/settings": "Настройки",
  "/security": "Безопасность",
  "/database": "База данных",
  "/deploy": "Публикация",
  "/profile": "Профиль",
  "/intel": "Аналитика",
  "/schema": "Схема данных",
  "/templates": "Шаблоны",
  "/learning": "Обучение",
  "/rules": "Правила",
  "/modules": "Модули",
  "/themes": "Темы",
  "/account": "Аккаунт",
  "/builder": "Редактор",
  "/preview": "Предпросмотр",
  "/db-history": "История базы данных",
  "/data-page": "Данные",
  "/knowledge-base": "База знаний",
  "/documents": "Документы",
  "/notifications": "Уведомления",
};

export function titleForPath(pathname: string): string {
  const clean = pathname.replace(/\/+$/, "") || "/";
  // "/invite/:token" → "/invite"
  const key = PAGE_TITLES[clean] !== undefined ? clean : "/" + clean.split("/")[1];
  const name = PAGE_TITLES[key];
  return name ? `${name} — ${BRAND}` : BRAND;
}

/** Keeps document.title in sync with the current route. */
export function PageTitle() {
  const { pathname } = useLocation();
  useEffect(() => {
    document.title = titleForPath(pathname);
  }, [pathname]);
  return null;
}

/** Redirect that keeps the query string (e.g. ?next=…). */
export function RedirectKeepSearch({ to }: { to: string }) {
  const { search } = useLocation();
  return <Navigate to={`${to}${search}`} replace />;
}
