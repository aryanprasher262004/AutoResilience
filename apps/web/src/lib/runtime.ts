/**
 * Where this console runs. Only `local` exists today: the browser talks to an engine on
 * the same machine through the /api/backend proxy, with no authentication. Desktop (a
 * Tauri shell over the same local stack) and Cloud (an authenticated, multi-tenant
 * workspace) are planned; mode-specific behaviour belongs behind this module so pages
 * do not hard-code the local assumptions.
 */
export type RuntimeMode = "local" | "desktop" | "cloud";

export const RUNTIME_MODES: Record<RuntimeMode, { label: string; status: "available" | "planned"; summary: string }> = {
  local: {
    label: "Local",
    status: "available",
    summary: "Engine, database and console on this machine; the API is reachable only through this console's proxy.",
  },
  desktop: {
    label: "Desktop",
    status: "planned",
    summary: "A desktop shell that starts and supervises the same local stack.",
  },
  cloud: {
    label: "Cloud",
    status: "planned",
    summary: "A hosted, authenticated workspace. Requires authentication and tenancy, which do not exist yet.",
  },
};

export const RUNTIME_MODE: RuntimeMode = "local";

export const CONSOLE_VERSION = process.env.AUTORESILIENCE_CONSOLE_VERSION ?? "unknown";

export const REPOSITORY_URL = "https://github.com/aryanprasher262004/AutoResilience";

/** Documentation lives in the repository until a docs site exists. */
export function docsUrl(path: string): string {
  return `${REPOSITORY_URL}/blob/main/${path}`;
}
