/** Temperature studio (×T): three parallel probes at configurable temperatures. */

export type TempSlotId = "t0" | "t07" | "t12";

export type TempAccent = "cold" | "warm" | "hot";

export interface TempSlotDef {
  id: TempSlotId;
  temperature: number;
  /** Short header, e.g. «t = 0». */
  label: string;
  /** One-line expectation before answers arrive. */
  hint: string;
  accent: TempAccent;
}

/** Slot keys stay fixed so the judge JSON schema stays stable. */
export const TEMP_SLOT_IDS: TempSlotId[] = ["t0", "t07", "t12"];

export const DEFAULT_TEMP_STUDIO_TEMPS: [number, number, number] = [0, 0.7, 1.2];

export interface TempStudioPreset {
  id: string;
  label: string;
  temps: [number, number, number];
}

export const TEMP_STUDIO_PRESETS: readonly TempStudioPreset[] = [
  { id: "day4", label: "Урок: 0 · 0.7 · 1.2", temps: [0, 0.7, 1.2] },
  { id: "soft", label: "Мягко: 0.2 · 0.5 · 0.8", temps: [0.2, 0.5, 0.8] },
  { id: "wide", label: "Широко: 0 · 1.0 · 1.5", temps: [0, 1, 1.5] },
  { id: "hot", label: "Жарко: 0.8 · 1.2 · 1.8", temps: [0.8, 1.2, 1.8] },
];

const HINTS = [
  "Ниже — стабильнее и точнее",
  "Середина — баланс ясности и живости",
  "Выше — креатив и разнообразие",
] as const;

const ACCENTS: TempAccent[] = ["cold", "warm", "hot"];

export function clampTemp(n: number): number {
  if (!Number.isFinite(n)) return 0.7;
  return Math.round(Math.max(0, Math.min(2, n)) * 100) / 100;
}

export function formatTemp(t: number): string {
  const c = clampTemp(t);
  return Number.isInteger(c) ? String(c) : c.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

export function normalizeTempTriple(raw: unknown): [number, number, number] {
  if (!Array.isArray(raw) || raw.length !== 3) {
    return [...DEFAULT_TEMP_STUDIO_TEMPS];
  }
  return [clampTemp(Number(raw[0])), clampTemp(Number(raw[1])), clampTemp(Number(raw[2]))];
}

export function tempsRecord(
  temps: [number, number, number],
): Record<TempSlotId, number> {
  return { t0: temps[0], t07: temps[1], t12: temps[2] };
}

export function slotDefsFromTemps(temps: [number, number, number]): TempSlotDef[] {
  const sorted = [...temps];
  return TEMP_SLOT_IDS.map((id, i) => ({
    id,
    temperature: sorted[i],
    label: `t = ${formatTemp(sorted[i])}`,
    hint: HINTS[i],
    accent: ACCENTS[i],
  }));
}

/** Default Day-4 slots (backward-compatible export). */
export const TEMP_STUDIO_SLOTS: readonly TempSlotDef[] = slotDefsFromTemps(
  DEFAULT_TEMP_STUDIO_TEMPS,
);

export function tempSlotById(
  id: TempSlotId,
  temps: [number, number, number] = DEFAULT_TEMP_STUDIO_TEMPS,
): TempSlotDef {
  const found = slotDefsFromTemps(temps).find((s) => s.id === id);
  if (!found) throw new Error(`Unknown temp slot: ${id}`);
  return found;
}

export function matchPresetId(temps: [number, number, number]): string {
  const hit = TEMP_STUDIO_PRESETS.find(
    (p) =>
      p.temps[0] === temps[0] && p.temps[1] === temps[1] && p.temps[2] === temps[2],
  );
  return hit?.id ?? "custom";
}
