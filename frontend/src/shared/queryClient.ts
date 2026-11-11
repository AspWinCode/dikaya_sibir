import { QueryClient } from "@tanstack/react-query";

/** App-wide React Query client. Lives in its own module (not inside main.tsx)
 * so the auth store can wipe the cache when the signed-in account changes —
 * otherwise the next account briefly sees the previous account's cached
 * apps/roles/users. */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
    mutations: { retry: 0 },
  },
});
