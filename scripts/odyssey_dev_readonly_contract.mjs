// Read-only n8n proxy contract for browser smoke testing.
// No authentication, persistence, product mutation or write endpoints.
export const OPERATIONS = Object.freeze({
  "/api/conversation": Object.freeze(["main", "progress", "history"]),
  "/api/notes": Object.freeze(["query", "capabilities", "detail", "backlinks"]),
  "/api/calendar": Object.freeze(["month", "day", "schedule"]),
});

export const MAX_REQUEST_BYTES = 32 * 1024;
export const MAX_RESPONSE_BYTES = 2 * 1024 * 1024;

export function approvedRead(pathname, method, payload) {
  if (method !== "POST" || !Object.hasOwn(OPERATIONS, pathname)) return false;
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return false;
  if (typeof payload.operation !== "string") return false;
  if (!OPERATIONS[pathname].includes(payload.operation)) return false;
  // Never authorize a second mutation hidden in payload fields.
  if (Object.hasOwn(payload, "mutations") || Object.hasOwn(payload, "write") ||
      Object.hasOwn(payload, "action") || Object.hasOwn(payload, "events")) return false;
  return true;
}

export function approvedStaticPath(pathname) {
  if (pathname === "/") return "index.html";
  if (typeof pathname !== "string" || !pathname.startsWith("/")) return null;
  let name;
  try { name = decodeURIComponent(pathname.slice(1)); } catch { return null; }
  if (!name || name.startsWith("/") || name.includes("\\") || name.includes("\0") ||
      name.split("/").some(x=>x==="" || x===".." || x===".")) return null;
  if (!/^[A-Za-z0-9_./-]+$/.test(name)) return null;
  if (!/\.(?:html|js|css|svg|json|png|ico|webp|woff2)$/.test(name)) return null;
  return name;
}
