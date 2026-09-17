/** Battle means (abstract doctrine actions) — game VFX vocabulary. */

export type BattleMeans =
  | "diplomacy"
  | "sanctions"
  | "cyber"
  | "mobilize"
  | "deterrence"
  | "strike";

export const MEANS_META: Record<
  BattleMeans,
  { label: string; icon: string; hue: string }
> = {
  diplomacy: { label: "Дипломатия", icon: "◇", hue: "#6eb5c0" },
  sanctions: { label: "Санкции", icon: "⛓", hue: "#c0785a" },
  cyber: { label: "Кибер", icon: "⚡", hue: "#7ec8a0" },
  mobilize: { label: "Мобилизация", icon: "▲", hue: "#d4a84b" },
  deterrence: { label: "Сдерживание", icon: "◎", hue: "#e0b35a" },
  strike: { label: "Пуск / удар", icon: "⇡", hue: "#d45c4a" },
};

const ALIASES: Record<string, BattleMeans> = {
  diplomacy: "diplomacy",
  дип: "diplomacy",
  дипломатия: "diplomacy",
  talks: "diplomacy",
  sanctions: "sanctions",
  санкции: "sanctions",
  эмбарго: "sanctions",
  cyber: "cyber",
  кибер: "cyber",
  инфо: "cyber",
  mobilize: "mobilize",
  мобилизация: "mobilize",
  deterrence: "deterrence",
  сдерживание: "deterrence",
  ядерн: "deterrence",
  strike: "strike",
  пуск: "strike",
  удар: "strike",
  ракет: "strike",
  launch: "strike",
  missile: "strike",
};

export function parseMeans(text: string): BattleMeans {
  const raw = (text || "").toLowerCase();
  const meansLine = raw.match(/средство\s*:\s*([^\n]+)/i);
  const chunk = (meansLine?.[1] || raw).slice(0, 220);
  for (const [alias, means] of Object.entries(ALIASES)) {
    if (chunk.includes(alias)) return means;
  }
  if (raw.includes("panic") && raw.includes("+")) return "deterrence";
  if (raw.includes("stability") && raw.includes("+")) return "diplomacy";
  return "mobilize";
}

export function meansTargetFaction(
  actorId: string,
  means: BattleMeans,
  factions: string[],
): string | null {
  const others = factions.filter((f) => f !== actorId);
  if (!others.length) return null;
  if (means === "diplomacy") return "summit";
  if (means === "strike" || means === "sanctions" || means === "cyber") {
    return others[0] ?? null;
  }
  return actorId;
}
