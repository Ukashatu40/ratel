// Thin wrapper around fetch for the RatelBSS API. Errors use the contract shape {"error": {"code", "message"}}.
const BASE: string = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(method: string, path: string, body?: unknown, idempotencyKey?: string): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey; // every state-changing call accepts one
  if (method !== "GET") headers["X-Ratel-Desk"] = "1"; // the API refuses a changing request without it (a forged page cannot add it)
  const res = await fetch(BASE + path, {
    method,
    headers,
    credentials: "include", // the staff session cookie (POST /v1/auth/login sets it)
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let code = "unknown";
    let message = res.statusText;
    try {
      const data = await res.json();
      code = data?.error?.code ?? code;
      message = data?.error?.message ?? message;
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(res.status, code, message);
  }
  if (res.status === 204) return undefined as T; // nothing to read
  return (await res.json()) as T;
}

export const apiGet = <T,>(path: string) => request<T>("GET", path);
export const apiPost = <T,>(path: string, body: unknown, idempotencyKey?: string) => request<T>("POST", path, body, idempotencyKey);

// One key per user action. Reusing it on a retry makes the backend treat the retry as the same request.
export function newIdempotencyKey(): string {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  const b = new Uint8Array(16);
  globalThis.crypto.getRandomValues(b);
  return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
}
export const apiPut = <T,>(path: string, body: unknown, idempotencyKey?: string) => request<T>("PUT", path, body, idempotencyKey);
