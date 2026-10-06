/**
 * Start the in-memory mock backend when VITE_USE_MOCKS=true. No-op otherwise.
 * msw and the handlers are dynamically imported so they are excluded from
 * production bundles entirely.
 */
export async function startMocks(): Promise<void> {
  if (import.meta.env.VITE_USE_MOCKS !== "true") return;

  const [{ setupWorker }, { handlers }] = await Promise.all([
    import("msw/browser"),
    import("./handlers"),
  ]);

  const worker = setupWorker(...handlers);
  await worker.start({
    onUnhandledRequest: "bypass", // let real assets / unmocked calls through
  });
  console.info("[mocks] MSW enabled — using in-memory mock backend");
}
