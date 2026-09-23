import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { isAxiosError } from "axios";
import { useQuery } from "@tanstack/react-query";
import { acceptInvite, getInvitePreview, signupViaInvite } from "@/shared/api/apps";
import { useAuthStore } from "@/shared/auth/store";
import { setTokens } from "@/shared/auth/tokens";
import { buildRuntimeUrl } from "@/shared/lib/appLinks";
import { PasswordInput } from "@/shared/components/PasswordInput";

const ROLE_LABELS: Record<string, string> = {
  admin: "администратор",
  editor: "редактор",
  viewer: "наблюдатель",
};

function errorText(err: unknown): string {
  if (isAxiosError(err)) {
    const status = err.response?.status;
    const detail = err.response?.data?.detail;
    if (status === 410) return "Ссылка недействительна: срок истёк, лимит исчерпан или её отозвали";
    if (status === 409) return "Этот e-mail уже зарегистрирован — войдите в свой аккаунт";
    if (status === 429) return "Слишком много попыток. Подождите минуту";
    if (typeof detail === "string") return detail;
    if (!err.response) return "Сервер недоступен";
  }
  return "Что-то пошло не так. Попробуйте ещё раз";
}

function goToApp(appId: string) {
  window.location.href = buildRuntimeUrl(appId, window.location.origin);
}

const inputCls =
  "w-full h-[46px] bg-cardbg rounded-[10px] border-none outline-none px-4 text-base text-primary focus:ring-2 focus:ring-primary/20";

/** Public landing for a shareable invite link: sign up or join with the current account. */
export function InvitePage() {
  const { token = "" } = useParams();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const initializing = useAuthStore((s) => s.initializing);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const preview = useQuery({
    queryKey: ["invite-preview", token],
    queryFn: () => getInvitePreview(token),
    retry: false,
  });

  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setError(null); }, [isAuthenticated]);

  async function handleJoin() {
    setBusy(true);
    setError(null);
    try {
      const res = await acceptInvite(token);
      goToApp(res.app_id);
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  async function handleSignup(e: FormEvent) {
    e.preventDefault();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return setError("Введите корректный e-mail");
    if (name.trim().length < 2) return setError("Укажите имя и фамилию");
    if (password.length < 8) return setError("Пароль должен быть не короче 8 символов");
    if (password !== confirm) return setError("Пароли не совпадают");
    setBusy(true);
    setError(null);
    try {
      const tokens = await signupViaInvite(token, { email, display_name: name.trim(), password });
      setTokens(tokens.access_token, tokens.refresh_token);
      goToApp(preview.data!.app_id);
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  const signinHref = `/signin?next=${encodeURIComponent(`/invite/${token}`)}`;

  let body: React.ReactNode;
  if (preview.isLoading || initializing) {
    body = <p className="text-primary/60 text-center">Проверяем приглашение…</p>;
  } else if (preview.isError || !preview.data) {
    body = (
      <div className="flex flex-col gap-4 text-center">
        <p className="text-[18px] text-primary">{errorText(preview.error)}</p>
        <p className="text-[14px] text-primary/60">Попросите у администратора новую ссылку.</p>
        <Link to="/signin" className="text-cta underline text-[15px]">Перейти ко входу</Link>
      </div>
    );
  } else {
    const inv = preview.data;
    const header = (
      <div className="flex flex-col gap-1 text-center">
        <p className="text-[15px] text-primary/60">Вас пригласили в приложение</p>
        <p className="text-[26px] font-bold text-primary leading-tight break-words">{inv.app_name}</p>
        <p className="text-[14px] text-primary/60">
          Роль: {ROLE_LABELS[inv.role] ?? inv.role}
          {inv.expires_at && ` · ссылка действует до ${new Date(inv.expires_at).toLocaleDateString("ru-RU")}`}
        </p>
      </div>
    );

    if (isAuthenticated) {
      body = (
        <div className="flex flex-col gap-5">
          {header}
          <p className="text-[15px] text-primary text-center">
            Вы вошли как <b>{user?.email ?? "…"}</b>
          </p>
          {error && <p className="text-[14px] text-mistake text-center">{error}</p>}
          <button
            onClick={() => void handleJoin()}
            disabled={busy}
            className="h-[50px] bg-cta rounded-btn text-[20px] font-medium text-white hover:bg-active transition-colors disabled:opacity-50"
          >
            {busy ? "Подключаем…" : "Присоединиться"}
          </button>
          <button
            onClick={() => void logout()}
            className="text-[14px] text-primary/70 hover:text-primary underline"
          >
            Это не я — выйти и зарегистрироваться
          </button>
        </div>
      );
    } else if (!inv.allow_signup) {
      body = (
        <div className="flex flex-col gap-5">
          {header}
          <p className="text-[15px] text-primary text-center">
            По этой ссылке могут присоединиться только пользователи с существующим аккаунтом.
          </p>
          <Link
            to={signinHref}
            className="h-[50px] flex items-center justify-center bg-cta rounded-btn text-[20px] font-medium text-white hover:bg-active transition-colors"
          >
            Войти
          </Link>
        </div>
      );
    } else {
      body = (
        <form onSubmit={(e) => void handleSignup(e)} className="flex flex-col gap-4">
          {header}
          <label className="flex flex-col gap-1">
            <span className="text-[16px] font-medium text-primary">Почта</span>
            <input type="email" required autoComplete="email" value={email}
              onChange={(e) => setEmail(e.target.value)} className={inputCls} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[16px] font-medium text-primary">Имя и фамилия</span>
            <input required autoComplete="name" value={name}
              onChange={(e) => setName(e.target.value)} className={inputCls} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[16px] font-medium text-primary">Пароль</span>
            <PasswordInput required autoComplete="new-password" value={password}
              onChange={(e) => setPassword(e.target.value)} className={inputCls} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[16px] font-medium text-primary">Повторите пароль</span>
            <PasswordInput required autoComplete="new-password" value={confirm}
              onChange={(e) => setConfirm(e.target.value)} className={inputCls} />
          </label>
          {error && <p className="text-[14px] text-mistake">{error}</p>}
          <button
            type="submit"
            disabled={busy}
            className="h-[50px] bg-cta rounded-btn text-[20px] font-medium text-white hover:bg-active transition-colors disabled:opacity-50"
          >
            {busy ? "Регистрируем…" : "Зарегистрироваться и войти"}
          </button>
          <Link to={signinHref} className="text-[14px] text-primary/75 hover:text-primary text-center">
            Уже есть аккаунт? Войти
          </Link>
        </form>
      );
    }
  }

  return (
    <div className="min-h-screen bg-white flex flex-col items-center justify-center gap-6 px-4 py-8">
      <span className="text-[48px] font-medium text-primary leading-[150%] select-none">Лесовик</span>
      <div className="bg-mainbg rounded-card w-full max-w-[460px] px-8 py-8">{body}</div>
    </div>
  );
}
