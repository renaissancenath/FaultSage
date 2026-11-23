// One small client for both modes. Local: cookie + X-FaultSage-Request. Cloud: cookie + CSRF header.
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public nextStep: string,
  ) {
    super(message);
  }
}

export type Mode = "local" | "cloud";
let mode: Mode = "cloud";
let orgId: string | null = null;

export function setMode(m: Mode): void {
  mode = m;
}
export function getMode(): Mode {
  return mode;
}
export function setOrg(id: string | null): void {
  orgId = id;
}

function cookie(name: string): string {
  for (const part of document.cookie.split("; ")) {
    const [k, ...v] = part.split("=");
    if (k === name) return decodeURIComponent(v.join("="));
  }
  return "";
}

function csrf(): string {
  return cookie("__Host-fs_csrf") || cookie("fs_csrf");
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const method = (init.method ?? (init.json !== undefined ? "POST" : "GET")).toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.json !== undefined) headers.set("Content-Type", "application/json");
  if (method !== "GET") {
    if (mode === "local") headers.set("X-FaultSage-Request", "1");
    else headers.set("X-CSRF-Token", csrf());
  }
  if (orgId && mode === "cloud") headers.set("X-Org-Id", orgId);
  const res = await fetch(path, {
    ...init,
    method,
    headers,
    credentials: "same-origin",
    body: init.json !== undefined ? JSON.stringify(init.json) : init.body,
  });
  if (res.status === 204) return undefined as T;
  const type = res.headers.get("content-type") ?? "";
  const body: unknown = type.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    const err = (body as { error?: { code?: string; message?: string; next_step?: string } })?.error;
    throw new ApiError(
      res.status,
      err?.code ?? "internal_error",
      err?.message ?? `Request failed with status ${res.status}.`,
      err?.next_step ?? "",
    );
  }
  return body as T;
}

export async function detectMode(): Promise<{ mode: Mode; meta: Record<string, unknown> }> {
  try {
    const meta = await api<Record<string, unknown>>("/api/v1/meta");
    return { mode: "cloud", meta };
  } catch {
    const meta = await api<Record<string, unknown>>("/api/meta");
    return { mode: "local", meta };
  }
}

/** Local dashboard: exchange the one-time token in the URL fragment for a cookie (LR step 4). */
export async function exchangeLocalToken(): Promise<boolean> {
  const m = window.location.hash.match(/(?:^#|&)t=([\w-]+)/);
  if (!m?.[1]) return false;
  history.replaceState(null, "", window.location.pathname + window.location.search);
  await api<void>("/auth/session", { method: "POST", json: { token: m[1] } });
  return true;
}
