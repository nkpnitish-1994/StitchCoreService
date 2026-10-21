const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
export type ApiError = { code?: string; message?: string; fields?: Record<string, string[]> };
export async function api<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { ...options, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers }, cache: "no-store" });
  if (!response.ok) throw await response.json() as ApiError;
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

