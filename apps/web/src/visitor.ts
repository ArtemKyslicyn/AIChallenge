/**
 * Browser-stable anonymous visitor id (localStorage).
 * Sent as X-Visitor-Id; combined server-side with hashed IP for grouping.
 */

const VISITOR_KEY = "aichallenge.visitor_id";

export function getVisitorId(): string {
  try {
    const existing = localStorage.getItem(VISITOR_KEY);
    if (existing && isUuid(existing)) return existing;
    const id = crypto.randomUUID();
    localStorage.setItem(VISITOR_KEY, id);
    return id;
  } catch {
    return crypto.randomUUID();
  }
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}
