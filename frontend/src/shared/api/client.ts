import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";
import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "../auth/tokens";

const BASE_URL = "/api/v1";

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
  withCredentials: true,
});

// Attach JWT from storage on every request
apiClient.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

function redirectToSignin(): void {
  if (!window.location.pathname.startsWith("/editor/signin")) {
    window.location.href = "/editor/signin";
  }
}

// A single refresh request is shared by all requests that 401 concurrently,
// so we never fire N parallel /auth/refresh calls (each rotates the token).
let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) throw new Error("No refresh token");
  // Bare axios (not apiClient) so this call skips the interceptors below
  // and can't recurse on its own 401.
  const { data } = await axios.post<{ access_token: string; refresh_token: string }>(
    `${BASE_URL}/auth/refresh`,
    { refresh_token: refreshToken },
  );
  setTokens(data.access_token, data.refresh_token);
  return data.access_token;
}

// On 401: try to refresh once and replay the original request; otherwise
// clear the session and bounce to sign-in. The login/refresh calls are exempt
// so their own 401s surface to the caller.
apiClient.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined;
    const status = error.response?.status;
    const url = original?.url ?? "";
    const isAuthRoute = url.includes("/auth/login") || url.includes("/auth/refresh");

    // Temp (invite) password: backend blocks everything until it is changed.
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail;
    if (status === 403 && detail === "Password change required") {
      if (!window.location.pathname.startsWith("/editor/change-password")) {
        window.location.href = "/editor/change-password";
      }
      return Promise.reject(error);
    }

    if (status !== 401 || isAuthRoute || !original) {
      return Promise.reject(error);
    }

    if (original._retry) {
      // Already retried after a refresh and still 401 — give up.
      clearTokens();
      redirectToSignin();
      return Promise.reject(error);
    }

    original._retry = true;
    try {
      refreshPromise =
        refreshPromise ??
        refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
      const newToken = await refreshPromise;
      original.headers.Authorization = `Bearer ${newToken}`;
      return await apiClient(original);
    } catch (refreshError) {
      clearTokens();
      redirectToSignin();
      return Promise.reject(refreshError);
    }
  },
);
