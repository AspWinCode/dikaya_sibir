"""Role → function catalog.

A *function* is one thing a role may do ("Создавать пользователей", "Смотреть
журнал аудита", ...). Access gates in the API ask ``current_user.can(code)``
instead of hard-coding role names.

How a role's grant is decided:
  1. ``platform_admin`` always has every function (locked — it can't be edited,
     so nobody can lock themselves out of the platform).
  2. An explicit override stored in ``identity.resource_permission`` with
     ``resource_type = "function"`` and ``resource_id = <code>`` wins.
  3. Otherwise the built-in default applies: the role is listed in the
     function's ``default_roles`` (system roles) — custom roles start with
     nothing.

The defaults below reproduce exactly what the old ``has_role(...)`` checks
allowed, so nothing changes until an admin toggles a checkbox.
"""

from __future__ import annotations

from dataclasses import dataclass

FUNCTION_RESOURCE_TYPE = "function"
FUNCTION_ACTION = "use"

LOCKED_ROLES = frozenset({"platform_admin"})


@dataclass(frozen=True)
class FunctionDef:
    code: str
    label: str
    description: str
    group: str
    default_roles: frozenset[str]


def _f(code: str, label: str, description: str, group: str, *roles: str) -> FunctionDef:
    return FunctionDef(code, label, description, group, frozenset(roles))


_PA = "platform_admin"
_OA = "org_admin"
_AU = "auditor"
_AB = "app_builder"
_AA = "app_admin"

GROUP_USERS = "Пользователи"
GROUP_ROLES = "Роли и группы"
GROUP_SECURITY = "Безопасность и аудит"
GROUP_APPS = "Приложения и данные"
GROUP_CONTENT = "Контент платформы"

FUNCTIONS: tuple[FunctionDef, ...] = (
    # Пользователи
    _f("users.view", "Просматривать пользователей", "Список и карточки пользователей", GROUP_USERS, _PA, _OA, _AU),
    _f("users.manage", "Создавать и редактировать пользователей",
       "Создание, приглашение, изменение, отключение, смена пароля", GROUP_USERS, _PA, _OA),
    _f("users.delete", "Удалять пользователей навсегда", "Полное удаление учётной записи", GROUP_USERS, _PA),
    _f("sessions.manage", "Управлять сессиями", "Просмотр и завершение чужих сессий", GROUP_USERS, _PA, _OA),
    # Роли и группы
    _f("roles.view", "Просматривать роли", "Список ролей, их права и правила доступа", GROUP_ROLES, _PA, _OA, _AU),
    _f("roles.manage", "Управлять ролями", "Создание, удаление ролей и изменение их функций", GROUP_ROLES, _PA, _OA),
    _f("groups.view", "Просматривать группы", "Список групп и их состав", GROUP_ROLES, _PA, _OA, _AU),
    _f("groups.manage", "Управлять группами", "Создание групп, состав, назначение ролей", GROUP_ROLES, _PA, _OA),
    # Безопасность и аудит
    _f("audit.view", "Смотреть журнал аудита", "Журнал действий пользователей", GROUP_SECURITY, _PA),
    _f("security.manage", "Менять политики безопасности",
       "Политики паролей, сессий и загрузки файлов", GROUP_SECURITY, _PA),
    _f("ldap.manage", "Настройки и проверка LDAP", "Просмотр настроек и проверка подключения", GROUP_SECURITY, _PA, _OA),
    # Приложения и данные
    _f("apps.create", "Создавать приложения", "Создание новых приложений", GROUP_APPS, _PA, _AB, _OA),
    _f("apps.trash", "Корзина удалённых записей", "Просмотр удалённых записей приложения", GROUP_APPS, _PA, _AA),
    _f("workflow.cancel", "Отменять процессы", "Отмена запущенных экземпляров процессов", GROUP_APPS, _PA, _AA),
    _f("records.purge", "Удалять записи навсегда", "Окончательное удаление записей без восстановления",
       GROUP_APPS, _PA),
    # Контент платформы
    _f("knowledge.manage", "Управлять базой знаний и обучением",
       "Статьи базы знаний, раздел «Обучение»", GROUP_CONTENT, _PA),
    _f("documents.configure", "Настраивать типы документов", "Настройка типов документов и реестра",
       GROUP_CONTENT, _PA),
)

FUNCTIONS_BY_CODE: dict[str, FunctionDef] = {f.code: f for f in FUNCTIONS}

Overrides = dict[tuple[str, str], bool]  # (role_id, function_code) -> allowed


def default_allowed(role_id: str, code: str) -> bool:
    """Built-in grant of a role for a function (no overrides)."""
    if role_id in LOCKED_ROLES:
        return True
    fn = FUNCTIONS_BY_CODE.get(code)
    return bool(fn and role_id in fn.default_roles)


def role_allows(role_id: str, code: str, overrides: Overrides) -> bool:
    if code not in FUNCTIONS_BY_CODE:
        return False
    if role_id in LOCKED_ROLES:
        return True
    return overrides.get((role_id, code), default_allowed(role_id, code))


def user_can(role_ids: list[str] | tuple[str, ...], code: str, overrides: Overrides) -> bool:
    """A user may do something if ANY of their roles allows it."""
    return any(role_allows(r, code, overrides) for r in role_ids)


def role_function_states(role_id: str, overrides: Overrides) -> dict[str, bool]:
    """Effective {code: allowed} for one role across the whole catalog."""
    return {f.code: role_allows(role_id, f.code, overrides) for f in FUNCTIONS}


def overrides_for_desired(role_id: str, desired: set[str]) -> Overrides:
    """Minimal override rows that turn the role's defaults into ``desired``.

    Only functions whose desired state differs from the built-in default are
    stored, so resetting a role to its defaults leaves no rows behind.
    """
    out: Overrides = {}
    for f in FUNCTIONS:
        want = f.code in desired
        if want != default_allowed(role_id, f.code):
            out[(role_id, f.code)] = want
    return out
