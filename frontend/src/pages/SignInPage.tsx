import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { isAxiosError } from "axios";
import { useAuthStore } from "@/shared/auth/store";
import { ldapLogin as apiLdapLogin, getYandexAuthUrl, getVkAuthUrl, type TokenPair } from "@/shared/api/auth";
import { setTokens } from "@/shared/auth/tokens";
import { PasswordInput } from "@/shared/components/PasswordInput";

// Backend error strings we translate rather than showing raw to the user.
const KNOWN_ERROR_TRANSLATIONS: Record<string, string> = {
  "Invalid credentials": "Неверная почта или пароль",
  "Account is blocked": "Аккаунт заблокирован",
  "Account is deactivated": "Аккаунт отключён",
  "User not found or inactive": "Пользователь не найден или отключён",
  "TOTP code required": "Введите код двухфакторной аутентификации",
  "Invalid TOTP code": "Неверный код двухфакторной аутентификации",
  "LDAP authentication failed": "Не удалось выполнить корпоративную авторизацию",
  "LDAP authentication is not enabled": "Корпоративная авторизация не подключена",
};

function extractError(err: unknown, isLdap = false): string {
  if (isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return KNOWN_ERROR_TRANSLATIONS[detail] ?? detail;
    if (err.response?.status === 401) return isLdap ? "Неверные корпоративные данные" : "Неверная почта или пароль";
    if (err.response?.status === 403) return "Доступ заблокирован";
    if (!err.response) return "Сервер недоступен";
  }
  return "Не удалось войти. Попробуйте ещё раз";
}

type LoginMode = "standard" | "ldap";

const OAUTH_ERRORS: Record<string, string> = {
  oauth_denied: "Вход отменён",
  oauth_failed: "Не удалось войти через внешний сервис. Попробуйте ещё раз.",
};

export function SignInPage() {
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);
  const bootstrap = useAuthStore((s) => s.bootstrap);
  const [searchParams] = useSearchParams();

  const [mode, setMode] = useState<LoginMode>("standard");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [totpRequired, setTotpRequired] = useState(false);
  // Only same-app relative paths — never "//host" or absolute URLs (open redirect).
  const nextParam = searchParams.get("next");
  const next = nextParam && /^\/(?![/\\])/.test(nextParam) ? nextParam : "/";
  const oauthError = OAUTH_ERRORS[searchParams.get("error") ?? ""] ?? null;
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function switchMode(m: LoginMode) {
    setMode(m);
    setError(null);
    setTotpRequired(false);
    setTotpCode("");
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === "ldap") {
        const tokens: TokenPair = await apiLdapLogin({ email, password });
        setTokens(tokens.access_token, tokens.refresh_token);
        await bootstrap();
      } else {
        await login({
          email,
          password,
          totp_code: totpRequired && totpCode ? totpCode : undefined,
        });
      }
      navigate(next, { replace: true });
    } catch (err) {
      const msg = extractError(err, mode === "ldap");
      if (mode === "standard" && msg.toLowerCase().includes("totp")) {
        setTotpRequired(true);
      }
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  const showTotp = mode === "standard" && totpRequired;
  const cardHeight = showTotp ? 580 : 500;

  return (
    <div className="min-h-screen bg-white flex flex-col items-center justify-center gap-6 px-4">
      {/* Logo */}
      <span className="text-[56px] font-medium text-primary leading-[150%] select-none">
        Лесовик
      </span>

      {/* Card — with border per design */}
      <form
        onSubmit={handleSubmit}
        className="relative bg-mainbg rounded-card border-2 border-primary"
        style={{ width: 500, height: cardHeight }}
      >
        {/* Title */}
        <h1
          className="absolute text-[32px] font-bold text-primary leading-[150%] flex items-center"
          style={{ left: "calc(50% - 40px)", top: 25 }}
        >
          Вход
        </h1>

        {/* Mode tabs */}
        <div
          className="absolute flex rounded-[10px] overflow-hidden border border-primary/20"
          style={{ left: "calc(50% - 175px)", top: 80, width: 350, height: 36 }}
        >
          <button
            type="button"
            onClick={() => switchMode("standard")}
            className={`flex-1 text-[13px] font-medium transition-colors ${
              mode === "standard"
                ? "bg-primary text-white"
                : "bg-cardbg text-primary hover:bg-primary/10"
            }`}
          >
            Пароль
          </button>
          <button
            type="button"
            onClick={() => switchMode("ldap")}
            className={`flex-1 text-[13px] font-medium transition-colors ${
              mode === "ldap"
                ? "bg-primary text-white"
                : "bg-cardbg text-primary hover:bg-primary/10"
            }`}
          >
            Корпоративный (LDAP)
          </button>
        </div>

        {/* Email */}
        <div
          className="absolute flex flex-col gap-[5px]"
          style={{ left: "calc(50% - 175px)", top: 133, width: 350 }}
        >
          <label className="text-[22px] font-medium text-primary leading-[150%]">
            {mode === "ldap" ? "Логин / Почта" : "Почта"}
          </label>
          <input
            type={mode === "ldap" ? "text" : "email"}
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full h-[50px] bg-cardbg rounded-[10px] border-none outline-none px-4
                       text-base text-primary focus:ring-2 focus:ring-primary/20"
          />
        </div>

        {/* Password */}
        <div
          className="absolute flex flex-col gap-[5px]"
          style={{ left: "calc(50% - 175px)", top: 246, width: 350 }}
        >
          <label className="text-[22px] font-medium text-primary leading-[150%]">
            Пароль
          </label>
          <PasswordInput
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full h-[50px] bg-cardbg rounded-[10px] border-none outline-none px-4
                       text-base text-primary focus:ring-2 focus:ring-primary/20"
          />
        </div>

        {/* TOTP (standard mode only, revealed when the backend requires it) */}
        {showTotp && (
          <div
            className="absolute flex flex-col gap-[5px]"
            style={{ left: "calc(50% - 175px)", top: 320, width: 350 }}
          >
            <input
              type="text"
              inputMode="numeric"
              placeholder="Код 2FA из приложения"
              value={totpCode}
              onChange={(e) => setTotpCode(e.target.value)}
              className="w-full h-[44px] bg-cardbg rounded-[10px] border-none outline-none px-4
                         text-base text-primary focus:ring-2 focus:ring-primary/20"
            />
          </div>
        )}

        {/* LDAP hint */}
        {mode === "ldap" && (
          <p
            className="absolute text-[12px] text-primary/50 text-center w-[350px]"
            style={{ left: "calc(50% - 175px)", top: 320 }}
          >
            Используйте учётные данные корпоративного LDAP / Active Directory
          </p>
        )}

        {/* Error message */}
        {error && (
          <p
            className="absolute text-[14px] text-mistake text-center w-[350px]"
            style={{ left: "calc(50% - 175px)", top: showTotp ? 378 : 348 }}
          >
            {error}
          </p>
        )}

        {/* Forgot password link (standard only) */}
        {mode === "standard" && (
          <Link
            to="/forgot-password"
            className="absolute text-[12px] font-medium text-primary/75 hover:text-primary transition-colors"
            style={{ left: "calc(50% - 175px)", top: showTotp ? 418 : 378 }}
          >
            Забыли пароль?
          </Link>
        )}

        {/* Sign-up link (standard only) */}
        {mode === "standard" && (
          <Link
            to="/signup"
            className="absolute text-[12px] font-medium text-primary/75 hover:text-primary transition-colors"
            style={{ left: "calc(50% - 56px + 75px)", top: showTotp ? 418 : 378 }}
          >
            Ещё нет аккаунта?
          </Link>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={loading}
          className="absolute flex items-center justify-center
                     bg-cta rounded-btn text-[24px] font-medium text-white
                     hover:bg-active transition-colors cursor-pointer disabled:opacity-60 disabled:cursor-default"
          style={{ left: "calc(50% - 175px + 4px)", bottom: 39, width: 350, height: 50 }}
        >
          {loading ? "Вход…" : "Войти"}
        </button>
      </form>

      {/* OAuth error from callback redirect */}
      {oauthError && (
        <p className="text-[14px] text-mistake text-center">{oauthError}</p>
      )}

      {/* Social login buttons */}
      <div className="flex flex-col items-center gap-3" style={{ width: 500 }}>
        <div className="flex items-center gap-3 w-full">
          <div className="flex-1 h-px bg-primary/15" />
          <span className="text-[13px] text-primary/40 shrink-0">или войти через</span>
          <div className="flex-1 h-px bg-primary/15" />
        </div>

        <div className="flex gap-3 w-full">
          {/* Яндекс ID */}
          <a
            href={getYandexAuthUrl()}
            className="flex flex-1 items-center justify-center gap-2 h-[46px] rounded-[12px] border-2 border-primary/20 bg-mainbg hover:bg-[#FFDB4D]/20 hover:border-[#FFDB4D] transition-colors cursor-pointer"
          >
            <YandexIcon />
            <span className="text-[14px] font-medium text-primary">Яндекс ID</span>
          </a>

          {/* VK ID */}
          <a
            href={getVkAuthUrl()}
            className="flex flex-1 items-center justify-center gap-2 h-[46px] rounded-[12px] border-2 border-primary/20 bg-mainbg hover:bg-[#0077FF]/10 hover:border-[#0077FF] transition-colors cursor-pointer"
          >
            <VkIcon />
            <span className="text-[14px] font-medium text-primary">VK ID</span>
          </a>
        </div>
      </div>
    </div>
  );
}

function YandexIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="12" fill="#FC3F1D" />
      <path
        d="M13.5 6H11.8C10.2 6 9 7.1 9 8.8c0 1.4.7 2.3 2 3.1L13.5 14v4H15V6h-1.5zm0 7.2L12 12.1c-.9-.6-1.5-1.2-1.5-2.3C10.5 8.4 11.2 7.5 12.3 7.5H13.5v5.7z"
        fill="white"
      />
    </svg>
  );
}

function VkIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="12" fill="#0077FF" />
      <path
        d="M12.9 16.5h1.1s.3 0 .5-.2c.1-.2.1-.5.1-.5s0-1.5.7-1.7c.7-.2 1.6 1.4 2.5 2.1.7.5 1.2.4 1.2.4l2.4-.1s1.3-.1.7-1.1c-.1-.1-.4-.8-1.9-2.2-1.5-1.5-1.3-1.2.5-3.7 1.1-1.5 1.5-2.4 1.4-2.8-.1-.4-.9-.3-.9-.3l-2.7.1s-.2 0-.4.1c-.1.1-.2.4-.2.4s-.4 1.1-1 2.1c-1.2 2-1.7 2.1-1.9 2C14 10.9 14 10.1 14 9.5c0-1.9.3-2.6-.5-2.8-.3 0-.5-.1-1.3-.1-1 0-1.9.1-2.4.3-.3.2-.6.5-.4.5.2 0 .6.1.9.4.4.4.3 1.3.3 1.3s.2 2.2-.5 2.5c-.5.2-1.1-.2-2.5-2.2C7 8.3 6.5 7.2 6.5 7.2s-.1-.3-.3-.4C6 6.7 5.7 6.7 5.7 6.7l-2.6.1s-.4 0-.5.2c-.1.1 0 .4 0 .4s2 4.8 4.3 7.2c2.1 2.2 4.4 2 4.4 2l1.6-.2z"
        fill="white"
      />
    </svg>
  );
}
