/** Day 11 — parse explicit chat directives into memory writes (mirrors API). */

export type MemoryLayerId = "working" | "long_term";

export interface ParsedMemoryWrite {
  layer: MemoryLayerId;
  kind: string;
  key?: string;
  value: string;
}

export const MEMORY_CHAT_HINTS: { label: string; fill: string; title: string }[] = [
  {
    label: "Цель",
    fill: "запомни цель: ",
    title: "Рабочая память · цель задачи",
  },
  {
    label: "Чеклист",
    fill: "в чеклист: ",
    title: "Рабочая память · пункт чеклиста",
  },
  {
    label: "Имя",
    fill: "меня зовут ",
    title: "Долговременная · профиль",
  },
  {
    label: "Решение",
    fill: "запомни решение: ",
    title: "Долговременная · решение",
  },
  {
    label: "Знание",
    fill: "запомни знание стек=",
    title: "Долговременная · знание key=value",
  },
];

function splitKv(raw: string): { key: string; value: string } {
  const text = raw.trim();
  for (const sep of ["=", ":"]) {
    const i = text.indexOf(sep);
    if (i > 0) {
      const key = text.slice(0, i).trim();
      const value = text.slice(i + 1).trim();
      if (key && value) return { key, value };
    }
  }
  return { key: "", value: text };
}

/** Returns a write when the message is an explicit memory directive; else null. */
export function parseMemoryChatCommand(text: string): ParsedMemoryWrite | null {
  const raw = text.trim();
  if (!raw) return null;

  const slash = raw.match(/^\/(?:mem(?:ory)?|память)\s+(\S+)\s+(\S+)\s+([\s\S]+)$/i);
  if (slash) {
    const layerTok = slash[1].toLowerCase();
    const kindTok = slash[2].toLowerCase();
    const rest = slash[3].trim();
    const working = ["working", "w", "рабочая", "работа", "task"].includes(layerTok);
    const longTerm = ["long", "long_term", "lt", "долговременная", "долго", "ltm"].includes(
      layerTok,
    );
    if (working) {
      if (["goal", "цель"].includes(kindTok)) {
        return { layer: "working", kind: "goal", value: rest };
      }
      if (["check", "checklist", "checklist_item", "чеклист", "todo"].includes(kindTok)) {
        return { layer: "working", kind: "checklist_item", value: rest };
      }
      if (["scratch", "note", "черновик"].includes(kindTok)) {
        const { key, value } = splitKv(rest);
        return { layer: "working", kind: "scratch", key: key || "note", value };
      }
    }
    if (longTerm) {
      if (["name", "имя"].includes(kindTok)) {
        return { layer: "long_term", kind: "profile", key: "name", value: rest };
      }
      if (["profile", "профиль"].includes(kindTok)) {
        const { key, value } = splitKv(rest);
        return { layer: "long_term", kind: "profile", key: key || "name", value };
      }
      if (["decision", "решение"].includes(kindTok)) {
        return { layer: "long_term", kind: "decision", value: rest };
      }
      if (["knowledge", "знание", "know"].includes(kindTok)) {
        const { key, value } = splitKv(rest);
        return { layer: "long_term", kind: "knowledge", key: key || "fact", value };
      }
    }
    return null;
  }

  const short = raw.match(
    /^\/(w|l|р|д)\s+(цель|чеклист|имя|решение|знание|goal|check|name|decision|knowledge)\s*[:：]?\s*([\s\S]+)$/i,
  );
  if (short) {
    const flag = short[1].toLowerCase();
    const kindTok = short[2].toLowerCase();
    const rest = short[3].trim();
    const working = flag === "w" || flag === "р";
    if (working && (kindTok === "цель" || kindTok === "goal")) {
      return { layer: "working", kind: "goal", value: rest };
    }
    if (working && (kindTok === "чеклист" || kindTok === "check")) {
      return { layer: "working", kind: "checklist_item", value: rest };
    }
    if (!working && (kindTok === "имя" || kindTok === "name")) {
      return { layer: "long_term", kind: "profile", key: "name", value: rest };
    }
    if (!working && (kindTok === "решение" || kindTok === "decision")) {
      return { layer: "long_term", kind: "decision", value: rest };
    }
    if (!working && (kindTok === "знание" || kindTok === "knowledge")) {
      const { key, value } = splitKv(rest);
      return { layer: "long_term", kind: "knowledge", key: key || "fact", value };
    }
    return null;
  }

  let m = raw.match(/^запомни\s+в\s+рабоч\w*\s+цель\s*[:：]\s*([\s\S]+)$/i);
  if (m) return { layer: "working", kind: "goal", value: m[1].trim() };

  m = raw.match(/^запомни\s+цель\s*[:：]\s*([\s\S]+)$/i);
  if (m) return { layer: "working", kind: "goal", value: m[1].trim() };

  m = raw.match(/^(?:в\s+чеклист|чеклист)\s*[:：]\s*([\s\S]+)$/i);
  if (m) return { layer: "working", kind: "checklist_item", value: m[1].trim() };

  m = raw.match(/^запомни\s+в\s+долговременн\w*\s+(?:имя|профиль)\s*[:：]\s*([\s\S]+)$/i);
  if (m) return { layer: "long_term", kind: "profile", key: "name", value: m[1].trim() };

  m = raw.match(/^(?:запомни\s+меня|меня\s+зовут)\s*[:：]?\s+([\s\S]+)$/i);
  if (m) return { layer: "long_term", kind: "profile", key: "name", value: m[1].trim() };

  m = raw.match(/^запомни\s+имя\s*[:：]\s*([\s\S]+)$/i);
  if (m) return { layer: "long_term", kind: "profile", key: "name", value: m[1].trim() };

  m = raw.match(/^запомни\s+решение\s*[:：]\s*([\s\S]+)$/i);
  if (m) return { layer: "long_term", kind: "decision", value: m[1].trim() };

  m = raw.match(/^запомни\s+знание\s*[:：]?\s*([\s\S]+)$/i);
  if (m) {
    const { key, value } = splitKv(m[1]);
    return { layer: "long_term", kind: "knowledge", key: key || "fact", value };
  }

  return null;
}

export function describeMemoryWrite(write: ParsedMemoryWrite): string {
  const layer = write.layer === "working" ? "рабочая" : "долговременная";
  switch (write.kind) {
    case "goal":
      return `${layer} · цель: ${write.value}`;
    case "checklist_item":
      return `${layer} · чеклист: ${write.value}`;
    case "scratch":
      return `${layer} · черновик ${write.key || "note"}: ${write.value}`;
    case "profile":
      return `${layer} · профиль ${write.key || "name"}: ${write.value}`;
    case "decision":
      return `${layer} · решение: ${write.value}`;
    case "knowledge":
      return `${layer} · знание ${write.key || "fact"}: ${write.value}`;
    default:
      return `${layer} · ${write.kind}: ${write.value}`;
  }
}
