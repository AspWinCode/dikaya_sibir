import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { apiClient } from "@/shared/api/client";
import { PasswordInput } from "@/shared/components/PasswordInput";
import { getFriendlyErrorMessage } from "@/shared/lib/errorMessage";

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const navigate = useNavigate();

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (password !== confirm) {
      setError("Пароли не совпадают");
      return;
    }

    setLoading(true);
    try {
      await apiClient.post("/auth/reset-password", { token, new_password: password });
      setDone(true);
      setTimeout(() => navigate("/signin", { replace: true }), 3000);
    } catch (err) {
      // /auth/reset-password only ever raises curated Russian messages
      // (expired/used token, password policy) with 400/422 — safe to show.
      setError(
        getFriendlyErrorMessage(err, {
          fallback: "Не удалось сбросить пароль",
          allowedDetail: true,
        })
      );
    } finally {
      setLoading(false);
    }
  }

  if (!token) {
    return (
      <div className="min-h-screen bg-white flex flex-col items-center justify-center gap-6 px-4">
        <span className="text-[56px] font-medium text-primary leading-[150%] select-none">Лесовик</span>
        <div
          className="relative bg-mainbg rounded-card border-2 border-primary flex flex-col items-center text-center"
          style={{ width: 500, padding: "40px 75px" }}
        >
          <p className="text-[20px] text-mistake">Недействительная ссылка сброса пароля.</p>
          <Link to="/forgot-password" className="mt-4 text-[16px] font-medium text-primary hover:underline">
            Запросить новую ссылку
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white flex flex-col items-center justify-center gap-6 px-4">
      <span className="text-[56px] font-medium text-primary leading-[150%] select-none">Лесовик</span>

      <div
        className="relative bg-mainbg rounded-card border-2 border-primary flex flex-col items-center"
        style={{ width: 500, padding: "40px 75px" }}
      >
        <h1 className="text-[32px] font-bold text-primary leading-[150%] mb-4">
          Новый пароль
        </h1>

        {done ? (
          <div className="flex flex-col items-center gap-4 mt-4 text-center">
            <p className="text-[18px] text-primary">Пароль успешно изменён!</p>
            <p className="text-[14px] text-primary/60">Перенаправляем на страницу входа…</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="w-full flex flex-col gap-5 mt-2">
            <div className="flex flex-col gap-[5px]">
              <label htmlFor="reset-password-new" className="text-[22px] font-medium text-primary leading-[150%]">
                Новый пароль
              </label>
              <PasswordInput
                id="reset-password-new"
                required
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full h-[50px] bg-cardbg rounded-[10px] border-none outline-none px-4
                           text-base text-primary focus:ring-2 focus:ring-primary/20"
              />
            </div>

            <div className="flex flex-col gap-[5px]">
              <label htmlFor="reset-password-confirm" className="text-[22px] font-medium text-primary leading-[150%]">
                Повторите пароль
              </label>
              <PasswordInput
                id="reset-password-confirm"
                required
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="w-full h-[50px] bg-cardbg rounded-[10px] border-none outline-none px-4
                           text-base text-primary focus:ring-2 focus:ring-primary/20"
              />
            </div>

            <p className="text-[12px] text-primary/50">
              Минимум 10 символов, заглавная буква, цифра и спецсимвол.
            </p>

            {error && (
              <p className="text-[14px] text-mistake text-center">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full h-[50px] bg-cta rounded-btn text-[20px] font-medium text-white
                         hover:bg-active transition-colors cursor-pointer disabled:opacity-60 disabled:cursor-default"
            >
              {loading ? "Сохранение…" : "Сохранить пароль"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
