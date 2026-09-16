/** Open-world layout helpers for the live agent-battle map. */

export type MapPoint = { x: number; y: number };

export type MapZoneId = "atlantic" | "pacific" | "neutral" | "summit";

export const MAP_ZONES: Record<
  MapZoneId,
  { label: string; short: string; center: MapPoint; hue: string }
> = {
  atlantic: {
    label: "Атлантический Союз",
    short: "Атлантика",
    center: { x: 22, y: 42 },
    hue: "#3d7ea6",
  },
  pacific: {
    label: "Тихоокеанский Консорциум",
    short: "Пацифик",
    center: { x: 78, y: 38 },
    hue: "#2f8f6b",
  },
  neutral: {
    label: "Нейтральная Лига",
    short: "Нейтралы",
    center: { x: 48, y: 68 },
    hue: "#c4a35a",
  },
  summit: {
    label: "Остров Аэрис",
    short: "Аэрис",
    center: { x: 52, y: 48 },
    hue: "#e8d5a3",
  },
};

const STYLE_ZONE: Record<string, MapZoneId> = {
  hawk: "atlantic",
  dove: "summit",
  archivist: "neutral",
  chaos: "pacific",
  engineer: "pacific",
  skeptic: "neutral",
  broker: "summit",
};

export function clampMapPoint(p: MapPoint): MapPoint {
  return {
    x: Math.max(4, Math.min(96, p.x)),
    y: Math.max(6, Math.min(92, p.y)),
  };
}

export function defaultTokenPosition(
  agentId: string,
  style: string,
  index: number,
  total: number,
): MapPoint {
  const zone = STYLE_ZONE[style] ?? "summit";
  const base = MAP_ZONES[zone].center;
  const angle = (index / Math.max(total, 1)) * Math.PI * 2;
  const radius = 6 + (index % 3) * 2.2;
  return clampMapPoint({
    x: base.x + Math.cos(angle) * radius,
    y: base.y + Math.sin(angle) * radius + (agentId.length % 3) * 0.4,
  });
}

/** Soft realtime drift toward faction pressure from live world meters. */
export function driftTowardWorld(
  point: MapPoint,
  techLead: Record<string, number>,
  panic: number,
  stability: number,
): MapPoint {
  const atlantic = Number(techLead.atlantic ?? 50);
  const pacific = Number(techLead.pacific ?? 50);
  const neutral = Number(techLead.neutral ?? 50);
  const sum = atlantic + pacific + neutral || 1;
  const pull = {
    x:
      (MAP_ZONES.atlantic.center.x * atlantic +
        MAP_ZONES.pacific.center.x * pacific +
        MAP_ZONES.neutral.center.x * neutral) /
      sum,
    y:
      (MAP_ZONES.atlantic.center.y * atlantic +
        MAP_ZONES.pacific.center.y * pacific +
        MAP_ZONES.neutral.center.y * neutral) /
      sum,
  };
  const tension = Math.min(1, Math.max(0, panic / 100));
  const calm = Math.min(1, Math.max(0, stability / 100));
  const strength = 0.04 + tension * 0.06 - calm * 0.02;
  return clampMapPoint({
    x: point.x + (pull.x - point.x) * strength,
    y: point.y + (pull.y - point.y) * strength,
  });
}

/** Visual scale for a faction aura (1 = baseline). */
export function zonePowerScale(score: number): number {
  const n = Number.isFinite(score) ? score : 50;
  return Math.max(0.55, Math.min(1.55, 0.55 + n / 100));
}

export function truncateCaption(text: string, max = 72): string {
  const flat = text.replace(/\s+/g, " ").trim();
  if (!flat) return "";
  if (flat.length <= max) return flat;
  return `${flat.slice(0, max - 1)}…`;
}
