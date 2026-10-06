import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { isAxiosError } from "axios";
import { apiClient } from "@/shared/api/client";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await apiClient.post("/auth/forgot-password", { email });
      setSent(true);
    } catch (err) {
      if (isAxiosError(err) && !err.response) {
        setError("Сервер недоступен");
      } else {
        // Always show success to not reveal email existence
        setSent(true);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-white flex flex-col items-center justify-center gap-6 px-4">
      <span className="text-[56px] font-medium text-primary leading-[150%] select-none">
        Лесовик
      </span>

      <div
        className="relative bg-mainbg rounded-card border-2 border-primary flex flex-col items-center"
        style={{ width: 500, minHeight: 360, padding: "40px 75px" }}
      >
        <h1 className="text-[32px] font-bold text-primary leading-[150%] mb-2">
          Забыли пароль?
        </h1>

        {sent ? (
          <div className="flex flex-col items-center gap-4 mt-6 text-center">
            <p className="text-[18px] text-primary leading-[150%]">
              Если аккаунт с этим адресом существует, мы отправили письмо со ссылкой для сброса пароля.
            </p>
            <p className="text-[14px] text-primary/60">
              Проверьте папку «Спам», если письмо не пришло в течение нескольких минут.
            </p>
            <Link
              to="/signin"
              className="mt-4 text-[16px] font-medium text-primary hover:underline"
            >
              ← Вернуться ко входу
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="w-full flex flex-col gap-5 mt-4">
            <div className="flex flex-col gap-[5px]">
              <label htmlFor="forgot-password-email" className="text-[22px] font-medium text-primary leading-[150%]">
                Почта
              </label>
              <input
                id="forgot-password-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full h-[50px] bg-cardbg rounded-[10px] border-none outline-none px-4
                           text-base text-primary focus:ring-2 focus:ring-primary/20"
              />
            </div>

            {error && (
              <p className="text-[14px] text-mistake text-center">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full h-[50px] bg-cta rounded-btn text-[20px] font-medium text-white
                         hover:bg-active transition-colors cursor-pointer disabled:opacity-60 disabled:cursor-default"
            >
              {loading ? "Отправка…" : "Отправить ссылку"}
            </button>

            <Link
              to="/signin"
              className="text-center text-[14px] font-medium text-primary/75 hover:text-primary transition-colors"
            >
              ← Вернуться ко входу
            </Link>
          </form>
        )}
      </div>
    </div>
  );
}
