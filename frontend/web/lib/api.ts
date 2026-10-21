const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";
export type ApiError = { code?: string; message?: string; fields?: Record<string, string[]> };
let refreshing: Promise<string | undefined> | undefined;
async function refreshAccess(): Promise<string | undefined> {
  const refresh = localStorage.getItem("stitchcore_refresh");
  if (!refresh) return;
  try {
    const response = await fetch(`${API_URL}/auth/token/refresh`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh }) });
    if (!response.ok) return;
    const data = await response.json();
    localStorage.setItem("stitchcore_access", data.access);
    if (data.refresh) localStorage.setItem("stitchcore_refresh", data.refresh);
    return data.access;
  } catch { return; }
}
export async function api<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const send = (access?: string) => fetch(`${API_URL}${path}`, { ...options, headers: { "Content-Type": "application/json", ...(access ? { Authorization: `Bearer ${access}` } : {}), ...options.headers }, cache: "no-store" });
  let response = await send(token);
  if (response.status === 401 && token && typeof window !== "undefined") {
    if (!refreshing) refreshing = refreshAccess().finally(() => { refreshing = undefined; });
    const access = await refreshing;
    if (access) response = await send(access);
    else { localStorage.removeItem("stitchcore_access"); localStorage.removeItem("stitchcore_refresh"); location.assign("/login"); }
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: "The service is temporarily unavailable. Please retry." }));
    throw error as ApiError;
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

