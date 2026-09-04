/** Comic strip persistence fence (mirrors API `comic+json` block). */

export type ComicTextMode = "bubble" | "caption" | "both";

export interface ComicCharacter {
  id: string;
  name: string;
  look: string;
}

export interface ComicPanelState {
  index: number;
  status: "pending" | "ok" | "error";
  text_mode: ComicTextMode;
  image_url?: string | null;
  speaker?: string | null;
  dialogue?: string | null;
  caption?: string | null;
  error?: string | null;
  visual?: string;
}

export interface ComicStripState {
  comic_id: string;
  title: string;
  panel_count: number;
  characters: ComicCharacter[];
  panels: ComicPanelState[];
  done?: boolean;
}

const FENCE_RE = /```comic\+json\s*([\s\S]*?)```/i;

export function stripComicFence(content: string): string {
  return (content || "").replace(FENCE_RE, "").trim();
}

export function extractComicFromContent(content: string): ComicStripState | null {
  const match = FENCE_RE.exec(content || "");
  if (!match) return null;
  try {
    const data = JSON.parse(match[1]) as {
      comic_id?: string;
      title?: string;
      characters?: ComicCharacter[];
      panels?: Array<Record<string, unknown>>;
    };
    const panelsRaw = Array.isArray(data.panels) ? data.panels : [];
    const panels: ComicPanelState[] = panelsRaw.map((p, i) => {
      const statusRaw = String(p.status || "");
      const image_url = typeof p.image_url === "string" ? p.image_url : null;
      const status: ComicPanelState["status"] =
        statusRaw === "ok" || statusRaw === "error" || statusRaw === "pending"
          ? statusRaw
          : image_url
            ? "ok"
            : "error";
      const mode = String(p.text_mode || "bubble");
      return {
        index: Number(p.index) || i + 1,
        status,
        text_mode: mode === "caption" || mode === "both" ? mode : "bubble",
        image_url,
        speaker: typeof p.speaker === "string" ? p.speaker : null,
        dialogue: typeof p.dialogue === "string" ? p.dialogue : null,
        caption: typeof p.caption === "string" ? p.caption : null,
        error: typeof p.error === "string" ? p.error : null,
      };
    });
    if (panels.length < 1) return null;
    return {
      comic_id: String(data.comic_id || "comic"),
      title: String(data.title || "Comic"),
      panel_count: panels.length,
      characters: Array.isArray(data.characters) ? data.characters : [],
      panels,
      done: true,
    };
  } catch {
    return null;
  }
}

export function emptyPanels(count: number): ComicPanelState[] {
  return Array.from({ length: Math.max(0, count) }, (_, i) => ({
    index: i + 1,
    status: "pending" as const,
    text_mode: "bubble" as const,
  }));
}
