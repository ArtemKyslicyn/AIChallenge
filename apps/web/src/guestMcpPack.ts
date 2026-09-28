/** Parse guest MCP JSON packs (AIChallenge + Cursor-style mcpServers). */

export type GuestMcpPackEntry = {
  name: string;
  url: string;
  token: string;
};

export type GuestMcpPackParseResult = {
  entries: GuestMcpPackEntry[];
  skipped: string[];
};

function bearerFromHeaders(headers: unknown): string {
  if (!headers || typeof headers !== "object") return "";
  const h = headers as Record<string, unknown>;
  for (const [key, value] of Object.entries(h)) {
    if (key.toLowerCase() !== "authorization") continue;
    const raw = String(value ?? "").trim();
    const m = /^Bearer\s+(.+)$/i.exec(raw);
    return m ? m[1].trim() : raw;
  }
  return "";
}

function asEntry(name: string, url: string, token: string): GuestMcpPackEntry | null {
  const u = url.trim();
  if (!u) return null;
  return { name: name.trim() || u, url: u, token: token.trim() };
}

/**
 * Accepts:
 * - `{ "servers": [ { "name", "url", "token?" } ] }`
 * - Cursor/Claude `{ "mcpServers": { "name": { "url", "headers"? } } }`
 * - bare array of `{ name, url, token? }`
 * Stdio entries (command/args) are skipped with a reason.
 */
export function parseGuestMcpPack(raw: unknown): GuestMcpPackParseResult {
  const entries: GuestMcpPackEntry[] = [];
  const skipped: string[] = [];

  if (Array.isArray(raw)) {
    for (const item of raw) {
      if (!item || typeof item !== "object") {
        skipped.push("элемент не объект");
        continue;
      }
      const row = item as Record<string, unknown>;
      const name = String(row.name ?? "");
      if (row.command) {
        skipped.push(`${name || "сервер"}: stdio — нужен HTTP URL (туннель)`);
        continue;
      }
      const entry = asEntry(name, String(row.url ?? ""), String(row.token ?? ""));
      if (!entry) {
        skipped.push(`${name || "сервер"}: нет url`);
        continue;
      }
      entries.push(entry);
    }
    return { entries, skipped };
  }

  if (!raw || typeof raw !== "object") {
    return { entries, skipped: ["нужен JSON-объект или массив"] };
  }

  const root = raw as Record<string, unknown>;

  if (Array.isArray(root.servers)) {
    return parseGuestMcpPack(root.servers);
  }

  const mcpServers = root.mcpServers;
  if (mcpServers && typeof mcpServers === "object" && !Array.isArray(mcpServers)) {
    for (const [name, cfg] of Object.entries(mcpServers as Record<string, unknown>)) {
      if (!cfg || typeof cfg !== "object") {
        skipped.push(`${name}: пустой конфиг`);
        continue;
      }
      const c = cfg as Record<string, unknown>;
      if (c.command) {
        skipped.push(`${name}: stdio — нужен HTTP URL (туннель)`);
        continue;
      }
      const token =
        typeof c.token === "string" && c.token
          ? c.token
          : bearerFromHeaders(c.headers);
      const entry = asEntry(name, String(c.url ?? ""), token);
      if (!entry) {
        skipped.push(`${name}: нет url`);
        continue;
      }
      entries.push(entry);
    }
    return { entries, skipped };
  }

  return { entries, skipped: ["ожидался servers[] или mcpServers{}"] };
}

export function parseGuestMcpPackText(text: string): GuestMcpPackParseResult {
  const trimmed = text.trim();
  if (!trimmed) return { entries: [], skipped: ["пустой файл"] };
  try {
    return parseGuestMcpPack(JSON.parse(trimmed) as unknown);
  } catch {
    return { entries: [], skipped: ["не удалось разобрать JSON"] };
  }
}
