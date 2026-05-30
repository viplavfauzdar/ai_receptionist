import { cookies } from "next/headers";

/**
 * Returns an Authorization header using the session cookie.
 * Call this only from Server Components / Route Handlers (never from client-side code).
 * Client components should use `credentials: "include"` on fetch calls instead —
 * the browser will forward the httpOnly cookie automatically for same-site requests.
 */
export function authHeaders(): Record<string, string> {
  const token = cookies().get("reeva_session")?.value;
  return token ? { Authorization: `Bearer ${token}` } : {};
}
