import type { GuestMcpServerDto } from "./api/client";

export const MEDIA_SSE_TOOL_NAMES = new Set([
  "generate_image",
  "generate_video",
  "generate_comic",
]);

export function isMediaSseToolName(name: string): boolean {
  return MEDIA_SSE_TOOL_NAMES.has(name);
}

/** First enabled connected server — enough for the muted composer line. */
export function pickConnectedGuest(
  servers: GuestMcpServerDto[],
): { name: string; count: number } | null {
  const connected = servers.filter((s) => s.enabled && s.status === "connected");
  if (connected.length === 0) return null;
  return { name: connected[0].name, count: connected.length };
}

export function guestMcpHowToLine(args: {
  signedIn: boolean;
  enabled: boolean;
  connectedName: string | null;
  singleMode: boolean;
}): string {
  if (!args.signedIn) {
    return "Свой MCP: Войти в профиле → Подключения → вставить адрес.";
  }
  if (!args.enabled) {
    return "Свой MCP выключен в этом чате. Настройки → «Свой сервер в этом чате».";
  }
  if (!args.connectedName) {
    return "Подключить свой MCP: Подключения и модели — в профиле.";
  }
  if (!args.singleMode) {
    return `«${args.connectedName}» подключён. Переключитесь на обычный чат — там модель вызовет умения.`;
  }
  return `Подключён «${args.connectedName}». Пишите в чат обычным языком — модель сама вызовет умения.`;
}
