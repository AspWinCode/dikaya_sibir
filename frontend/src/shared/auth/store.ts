import { create } from "zustand";
import {
  login as apiLogin,
  logout as apiLogout,
  fetchMe,
  type CurrentUser,
  type LoginPayload,
} from "../api/auth";
import { clearTokens, getRefreshToken, isAuthenticated, setTokens } from "./tokens";
import { queryClient } from "../queryClient";

interface AuthState {
  user: CurrentUser | null;
  /** True until the initial "am I logged in?" check resolves. */
  initializing: boolean;
  isAuthenticated: boolean;
  login: (payload: LoginPayload) => Promise<void>;
  logout: () => Promise<void>;
  /** Load the current user if a token exists (call once on app start). */
  bootstrap: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  initializing: true,
  isAuthenticated: isAuthenticated(),

  login: async (payload) => {
    const tokens = await apiLogin(payload);
    // New account: drop everything cached for the previous one.
    queryClient.clear();
    setTokens(tokens.access_token, tokens.refresh_token);
    set({ isAuthenticated: true });
    const user = await fetchMe();
    set({ user });
  },

  logout: async () => {
    const refresh = getRefreshToken();
    if (refresh) {
      try {
        await apiLogout(refresh);
      } catch {
        /* best-effort — clear locally regardless */
      }
    }
    clearTokens();
    queryClient.clear();
    set({ user: null, isAuthenticated: false });
  },

  bootstrap: async () => {
    if (!isAuthenticated()) {
      set({ initializing: false, isAuthenticated: false });
      return;
    }
    try {
      const user = await fetchMe();
      set({ user, isAuthenticated: true, initializing: false });
    } catch {
      clearTokens();
      set({ user: null, isAuthenticated: false, initializing: false });
    }
  },
}));

/** Tokens live in localStorage, shared by every tab of the site. Signing in
 * as another account (or signing out) in one tab silently swapped the session
 * under all the others: their store still showed the old user while every API
 * call ran as the new one — "accounts redirect to each other". Follow the
 * storage event so every tab always reflects the account actually in use. */
if (typeof window !== "undefined") {
  window.addEventListener("storage", (e) => {
    if (e.key !== null && e.key !== "access_token") return;
    const state = useAuthStore.getState();
    if (!isAuthenticated()) {
      queryClient.clear();
      useAuthStore.setState({ user: null, isAuthenticated: false, initializing: false });
      return;
    }
    void fetchMe()
      .then((user) => {
        if (user.id !== state.user?.id) queryClient.clear();
        useAuthStore.setState({ user, isAuthenticated: true, initializing: false });
      })
      .catch(() => {
        /* token rotation race — the next request/refresh will sort it out */
      });
  });
}
