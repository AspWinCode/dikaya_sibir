/**
 * Build the end-user runtime URL for an app: `<origin>/app/?app=<id>`.
 * Falls back to the runtime root when no app id is supplied.
 */
export function buildRuntimeUrl(appId: string | null | undefined, origin: string): string {
  const base = origin.replace(/\/+$/, "");
  return appId ? `${base}/app/?app=${appId}` : `${base}/app/`;
}

/**
 * Build the editor (App Builder) URL for an app:
 * `<origin>/editor/views?app=<id>`.
 */
export function buildEditorUrl(appId: string | null | undefined, origin: string): string {
  const base = origin.replace(/\/+$/, "");
  return appId ? `${base}/editor/views?app=${appId}` : `${base}/editor/`;
}

/** Build a shareable invite URL: `<origin>/editor/invite/<token>`. */
export function buildInviteUrl(token: string, origin: string): string {
  const base = origin.replace(/\/+$/, "");
  return `${base}/editor/invite/${encodeURIComponent(token)}`;
}
