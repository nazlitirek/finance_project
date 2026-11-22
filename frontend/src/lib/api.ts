// Backend API istemcisi. Frontend sadece kendi backend'imize bağlanır; veri sağlayıcılara veya AI API'ye değil.

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // gövde JSON değil
  }
  if (!res.ok) {
    const fromBody =
      body && typeof body === "object" && "message" in body ? String((body as { message: unknown }).message) : "";
    throw new ApiError(fromBody || `Sunucu hatası (HTTP ${res.status})`, res.status);
  }
  return body as T;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError("Backend'e bağlanılamadı. Backend'in çalıştığından emin olun (127.0.0.1:8000).", 0);
  }
  return handle<T>(res);
}

export const fetcher = <T,>(path: string) => request<T>(path);
export const apiPost = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const apiDelete = (path: string) => request<void>(path, { method: "DELETE" });
