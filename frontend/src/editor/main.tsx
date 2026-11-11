import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { EditorApp } from "./EditorApp";
import { startMocks } from "@/mocks/browser";
import { queryClient } from "@/shared/queryClient";
import "@/index.css";

const root = document.getElementById("root");
if (!root) throw new Error("#root element not found");

// Start MSW first (when enabled) so the very first requests are intercepted.
void startMocks().then(() => {
  createRoot(root).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <EditorApp />
        <ReactQueryDevtools initialIsOpen={false} />
      </QueryClientProvider>
    </StrictMode>,
  );
});
