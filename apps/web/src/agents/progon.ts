/** Fan-out / fan-in «Прогон» — matrix variants + aggregate (client-side). */

export type ProgonAxis = "temperature" | "model";

export const PROGON_MAX_VARIANTS = 4;
export const PROGON_DEFAULT_TEMPERATURES = [0.2, 0.7, 1.2] as const;

export interface ProgonBaseDefinition {
  name: string;
  system_prompt: string;
  preferred_model: string;
  temperature?: number | null;
  max_tokens?: number | null;
}

export interface ProgonMatrix {
  axis: ProgonAxis;
  temperatures?: number[];
  modelIds?: string[];
}

export interface ProgonVariant extends ProgonBaseDefinition {
  /** Short UI / log label */
  label: string;
  /** Extra mission line so workers do not duplicate (scatter-gather practice) */
  mission: string;
}

export interface ProgonPart {
  label: string;
  modelId: string;
  content: string;
  temperature?: number | null;
}

const TRIGGER = /^\s*\/прогон\b[ \t]*/iu;

/** Strip leading `/прогон` if present. */
export function stripProgonTrigger(raw: string): { triggered: boolean; task: string } {
  const m = raw.match(TRIGGER);
  if (!m) return { triggered: false, task: raw.trim() };
  return { triggered: true, task: raw.slice(m[0].length).trim() };
}

function clampTemps(temps: number[]): number[] {
  const out: number[] = [];
  for (const t of temps) {
    if (!Number.isFinite(t)) continue;
    const c = Math.min(2, Math.max(0, Math.round(t * 100) / 100));
    if (!out.includes(c)) out.push(c);
    if (out.length >= PROGON_MAX_VARIANTS) break;
  }
  return out;
}

function missionForTemp(t: number): string {
  if (t <= 0.35) {
    return "Вариант «точный»: максимум ясности и фактов, минимум фантазии. Один цельный ответ.";
  }
  if (t <= 0.85) {
    return "Вариант «сбалансированный»: ясно и живо, один короткий пример уместен.";
  }
  return "Вариант «смелый»: допустимы неожиданные углы и метафоры, но без потери смысла задачи.";
}

function missionForModel(modelId: string, index: number): string {
  return `Вариант #${index + 1} (модель «${modelId}»): ответь самостоятельно, не ссылайся на другие варианты.`;
}

/**
 * Build independent worker definitions from one base draft + matrix.
 * Temperatures and models are mutually exclusive axes (v1).
 */
export function buildProgonVariants(
  base: ProgonBaseDefinition,
  matrix: ProgonMatrix,
): ProgonVariant[] {
  const prompt = base.system_prompt.trim();
  const maxTokens = base.max_tokens ?? 700;

  if (matrix.axis === "temperature") {
    const temps = clampTemps(
      matrix.temperatures?.length
        ? matrix.temperatures
        : [...PROGON_DEFAULT_TEMPERATURES],
    );
    if (!temps.length) return [];
    return temps.map((t) => {
      const mission = missionForTemp(t);
      return {
        name: `${base.name} · t=${t}`,
        system_prompt: `${prompt}\n\n[Миссия прогона]\n${mission}`,
        preferred_model: base.preferred_model || "auto",
        temperature: t,
        max_tokens: maxTokens,
        label: `t=${t}`,
        mission,
      };
    });
  }

  const ids = (matrix.modelIds ?? [])
    .map((id) => id.trim())
    .filter(Boolean)
    .filter((id, i, arr) => arr.indexOf(id) === i)
    .slice(0, PROGON_MAX_VARIANTS);
  return ids.map((modelId, index) => {
    const mission = missionForModel(modelId, index);
    return {
      name: `${base.name} · ${modelId}`,
      system_prompt: `${prompt}\n\n[Миссия прогона]\n${mission}`,
      preferred_model: modelId,
      temperature: base.temperature ?? 0.7,
      max_tokens: maxTokens,
      label: modelId,
      mission,
    };
  });
}

/** N workers + 1 optional aggregator. */
export function estimateProgonRequests(variantCount: number, withAggregate: boolean): number {
  const n = Math.max(0, variantCount);
  return n + (withAggregate && n > 0 ? 1 : 0);
}

export function buildProgonAggregateMessage(opts: {
  task: string;
  parts: ProgonPart[];
}): string {
  const blocks = opts.parts
    .map((p, i) => {
      const meta = [
        `#${i + 1}`,
        p.label,
        p.modelId ? `model_id=${p.modelId}` : null,
        p.temperature != null ? `temp=${p.temperature}` : null,
      ]
        .filter(Boolean)
        .join(" · ");
      return `### ${meta}\n${p.content.trim()}`;
    })
    .join("\n\n");

  return [
    "Задача пользователя:",
    opts.task.trim(),
    "",
    "Ниже — независимые ответы субагентов (fan-out). Склей их:",
    "1) Кратко: где согласны",
    "2) Где расходятся (с метками вариантов / model_id)",
    "3) Итоговый ответ пользователю — один связный текст",
    "Не выдумывай факты, которых нет в блоках.",
    "",
    blocks || "(нет успешных ответов)",
  ].join("\n");
}

/** Deterministic merge when aggregator LLM fails. */
export function markdownJoinParts(opts: { task: string; parts: ProgonPart[] }): string {
  const body = opts.parts
    .map((p) => {
      const head = `### ${p.label}${p.modelId ? ` · \`${p.modelId}\`` : ""}`;
      return `${head}\n\n${p.content.trim()}`;
    })
    .join("\n\n");
  return [`## Прогон: ${opts.task.trim()}`, "", body || "_Нет ответов_"].join("\n");
}

export const AGGREGATOR_DEFINITION: ProgonBaseDefinition = {
  name: "Склейщик",
  system_prompt:
    "Ты reducer / supervisor после параллельного fan-out. На входе — одна задача и несколько независимых ответов с метками. " +
    "Сравни кратко, укажи согласия и расхождения (с model_id/метками), затем дай один итоговый ответ пользователю. " +
    "Без воды, без повторения всех блоков дословно.",
  preferred_model: "auto",
  temperature: 0.3,
  max_tokens: 900,
};

/** Pick up to `max` concrete model ids from catalog (skip auto). */
export function pickDefaultModelIds(
  catalog: { id: string }[],
  max = 3,
): string[] {
  const ids = catalog.map((m) => m.id).filter((id) => id && id !== "auto");
  return ids.slice(0, max);
}
