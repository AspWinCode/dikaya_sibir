import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { isAxiosError } from "axios";
import { changePassword } from "@/shared/api/auth";
import { useAuthStore } from "@/shared/auth/store";
import { PasswordInput } from "@/shared/components/PasswordInput";

const inputCls =
  "w-full h-[46px] bg-cardbg rounded-[10px] border-none outline-none px-4 text-base text-primary focus:ring-2 focus:ring-primary/20";

function errorText(err: unknown): string {
  if (isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (detail === "Current password is incorrect") return "Временный пароль указан неверно";
    if (typeof detail === "string") return detail;
    if (err.response?.status === 422) return "Новый пароль не соответствует требованиям (минимум 10 символов)";
    if (!err.response) return "Сервер недоступен";
  }
  return "Не удалось сменить пароль. Попробуйте ещё раз";
}

/**
 * Shown after the first login with an invite temp password: the backend blocks
 * every other endpoint until the user sets their own password.
 */
export function ChangePasswordRequiredPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const initializing = useAuthStore((s) => s.initializing);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const login = useAuthStore((s) => s.login);
  const logout = useAuthStore((s) => s.logout);

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (initializing) {
    return <div className="min-h-screen flex items-center justify-center text-primary text-xl">Загрузка…</div>;
  }
  if (!isAuthenticated || !user) return <Navigate to="/signin" replace />;
  if (!user.must_change_password) return <Navigate to="/" replace />;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (next.length < 10) return setError("Новый пароль должен быть не короче 10 символов");
    if (next !== confirm) return setError("Пароли не совпадают");
    if (next === current) return setError("Новый пароль должен отличаться от временного");
    setBusy(true);
    setError(null);
    try {
      await changePassword(current, next);
      // change-password revokes every session — sign in again with the new password.
      await login({ email: user!.email, password: next });
      navigate("/", { replace: true });
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-white flex flex-col items-center justify-center gap-6 px-4 py-8">
      <span className="text-[48px] font-medium text-primary leading-[150%] select-none">Лесовик</span>
      <form
        onSubmit={(e) => void handleSubmit(e)}
        className="bg-mainbg rounded-card w-full max-w-[460px] px-8 py-8 flex flex-col gap-4"
      >
        <div className="flex flex-col gap-1 text-center">
          <h1 className="text-[26px] font-bold text-primary">Смена пароля</h1>
          <p className="text-[14px] text-primary/70">
            Вы вошли с временным паролем из приглашения. Придумайте свой пароль, чтобы продолжить.
          </p>
        </div>
        <label className="flex flex-col gap-1">
          <span className="text-[16px] font-medium text-primary">Временный пароль</span>
          <PasswordInput required autoComplete="current-password" value={current}
            onChange={(e) => setCurrent(e.target.value)} className={inputCls} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[16px] font-medium text-primary">Новый пароль</span>
          <PasswordInput required autoComplete="new-password" value={next}
            onChange={(e) => setNext(e.target.value)} className={inputCls} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[16px] font-medium text-primary">Повторите новый пароль</span>
          <PasswordInput required autoComplete="new-password" value={confirm}
            onChange={(e) => setConfirm(e.target.value)} className={inputCls} />
        </label>
        {error && <p className="text-[14px] text-mistake">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="h-[50px] bg-cta rounded-btn text-[20px] font-medium text-white hover:bg-active transition-colors disabled:opacity-50"
        >
          {busy ? "Сохраняем…" : "Сохранить и продолжить"}
        </button>
        <button
          type="button"
          onClick={() => void logout().then(() => navigate("/signin", { replace: true }))}
          className="text-[14px] text-primary/70 hover:text-primary underline"
        >
          Выйти
        </button>
      </form>
    </div>
  );
}
