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
