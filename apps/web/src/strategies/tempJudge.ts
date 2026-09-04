import { probeComplete } from "../api/client";
import {
  TEMP_SLOT_IDS,
  formatTemp,
  type TempSlotId,
} from "./tempStudio";

export interface TempAxisScores {
  accuracy: number;
  creativity: number;
  diversity: number;
}

export interface TempJudgeScorecard {
  scores: Partial<Record<TempSlotId, TempAxisScores>>;
  /** Best tasks for each temperature setting. */
  bestFor: Partial<Record<TempSlotId, string>>;
  summary: string;
  modelId: string | null;
  raw?: string;
  error?: string | null;
  /** True when scores came from local heuristics, not the LLM judge. */
  heuristic?: boolean;
}

const EMPTY_AXES: TempAxisScores = { accuracy: 0, creativity: 0, diversity: 0 };

function clampScore(n: unknown): number {
  if (typeof n !== "number" || !Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(10, Math.round(n)));
}

function buildTempJudgePrompt(
  task: string,
  answers: { id: TempSlotId; temperature: number; content: string }[],
): string {
  const blocks = answers
    .map(
      (a) =>
        `### ${a.id} (temperature=${a.temperature})\n${a.content.trim() || "(пусто)"}`,
    )
    .join("\n\n");

  const labels = answers.map((a) => `t=${formatTemp(a.temperature)}`).join(", ");

  return (
    `Ты — методист по параметру temperature в LLM. Один и тот же запрос выполнен при ${labels}.\n` +
    `Сравни ответы по осям (0–10 целые):\n` +
    `- accuracy — фактическая точность, следование вопросу, отсутствие выдумок\n` +
    `- creativity — оригинальность формулировок и идей\n` +
    `- diversity — разнообразие лексики, стиля, вариантов (не «воды»)\n\n` +
    `Для каждой температуры кратко (1 предложение) напиши, для каких задач она лучше.\n` +
    `В summary — 2–4 предложения общих выводов на русском.\n\n` +
    `Запрос пользователя:\n${task.trim()}\n\n` +
    `Ответы:\n${blocks}\n\n` +
    `Верни ТОЛЬКО JSON без markdown:\n` +
    `{"scores":{"t0":{"accuracy":0,"creativity":0,"diversity":0},` +
    `"t07":{"accuracy":0,"creativity":0,"diversity":0},` +
    `"t12":{"accuracy":0,"creativity":0,"diversity":0}},` +
    `"best_for":{"t0":"...","t07":"...","t12":"..."},` +
    `"summary":"..."}`
  );
}

/** Cheap local fallback if the judge call fails — still gives a usable Day-4 card. */
export function heuristicTempJudge(
  answers: { id: TempSlotId; temperature?: number; content: string }[],
): TempJudgeScorecard {
  const byId = new Map(answers.map((a) => [a.id, a]));
  const scores: Partial<Record<TempSlotId, TempAxisScores>> = {};
  const bestFor: Partial<Record<TempSlotId, string>> = {
    t0: "Факты, код, инструкции, где важна повторяемость.",
    t07: "Обычный диалог, объяснения, письма — баланс ясности и живости.",
    t12: "Мозговой штурм, слоганы, сюжеты — когда нужны варианты.",
  };

  for (const a of answers) {
    const text = a.content.trim();
    const words = text.split(/\s+/).filter(Boolean);
    const unique = new Set(words.map((w) => w.toLowerCase()));
    const uniqRatio = words.length ? unique.size / words.length : 0;
    const len = text.length;
    // Soft prior by slot order (low / mid / high), not a claim of truth.
    const priorAcc = a.id === "t0" ? 8 : a.id === "t07" ? 7 : 5;
    const creativity = Math.max(
      1,
      Math.min(10, Math.round(3 + uniqRatio * 5 + Math.min(len, 800) / 200)),
    );
    const diversity = Math.max(1, Math.min(10, Math.round(uniqRatio * 10)));
    scores[a.id] = {
      accuracy: priorAcc,
      creativity,
      diversity,
    };
    const t = a.temperature;
    if (typeof t === "number") {
      if (a.id === "t0") {
        bestFor.t0 = `Низкая t=${formatTemp(t)}: факты, код, инструкции.`;
      } else if (a.id === "t07") {
        bestFor.t07 = `Средняя t=${formatTemp(t)}: диалог и объяснения.`;
      } else {
        bestFor.t12 = `Высокая t=${formatTemp(t)}: идеи и варианты.`;
      }
    }
  }

  const tLabels = TEMP_SLOT_IDS.map((id) => {
    const t = byId.get(id)?.temperature;
    return typeof t === "number" ? `t=${formatTemp(t)}` : id;
  }).join(" / ");

  return {
    scores,
    bestFor,
    summary:
      `Оценка эвристическая (судья недоступен): ${tLabels}. ` +
      "Ниже обычно стабильнее, выше — разнообразнее. Сверьте факты глазами.",
    modelId: null,
    heuristic: true,
    error: null,
  };
}

function parseTempJudgeJson(raw: string, modelId: string): TempJudgeScorecard {
  const cleaned = raw.replace(/```json\s*/gi, "").replace(/```/g, "").trim();
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start < 0 || end <= start) {
    return {
      scores: {},
      bestFor: {},
      summary: cleaned.slice(0, 280),
      modelId,
      raw: cleaned,
      error: "Судья не вернул JSON.",
    };
  }
  try {
    const data = JSON.parse(cleaned.slice(start, end + 1)) as {
      scores?: Record<string, Partial<TempAxisScores>>;
      best_for?: Record<string, string>;
      summary?: string;
    };
    const scores: Partial<Record<TempSlotId, TempAxisScores>> = {};
    for (const id of TEMP_SLOT_IDS) {
      const row = data.scores?.[id];
      scores[id] = {
        accuracy: clampScore(row?.accuracy),
        creativity: clampScore(row?.creativity),
        diversity: clampScore(row?.diversity),
      };
    }
    const bestFor: Partial<Record<TempSlotId, string>> = {};
    for (const id of TEMP_SLOT_IDS) {
      const tip = data.best_for?.[id];
      if (typeof tip === "string" && tip.trim()) bestFor[id] = tip.trim();
    }
    return {
      scores,
      bestFor,
      summary: String(data.summary || "").trim(),
      modelId,
      raw: cleaned,
      error: null,
    };
  } catch {
    return {
      scores: {},
      bestFor: {},
      summary: cleaned.slice(0, 280),
      modelId,
      raw: cleaned,
      error: "Не удалось разобрать вердикт судьи.",
    };
  }
}

export async function runTempStudioJudge(options: {
  task: string;
  answers: { id: TempSlotId; content: string; temperature: number }[];
  model: string;
  signal?: AbortSignal;
}): Promise<TempJudgeScorecard> {
  const usable = options.answers.filter((a) => a.content.trim().length > 0);
  if (usable.length < 2) {
    return {
      scores: {},
      bestFor: {},
      summary: "",
      modelId: null,
      error: "Недостаточно ответов для сравнения.",
    };
  }

  try {
    const result = await probeComplete(
      buildTempJudgePrompt(options.task, usable),
      {
        model: options.model,
        temperature: 0.2,
        reasoning: false,
        prompt_format: false,
        prompt_length: false,
        prompt_stop: false,
      },
      options.signal,
    );
    const parsed = parseTempJudgeJson(result.content, result.model_id);
    if (parsed.error || !TEMP_SLOT_IDS.some((id) => parsed.scores[id])) {
      const fallback = heuristicTempJudge(usable);
      fallback.error = parsed.error
        ? `${parsed.error} Показана эвристика.`
        : "Слабый JSON судьи — показана эвристика.";
      return fallback;
    }
    return parsed;
  } catch (e) {
    if (options.signal?.aborted) {
      return {
        scores: {},
        bestFor: {},
        summary: "",
        modelId: null,
        error: null,
      };
    }
    const fallback = heuristicTempJudge(usable);
    fallback.error = e instanceof Error ? e.message : String(e);
    return fallback;
  }
}

export function emptyTempAxes(): TempAxisScores {
  return { ...EMPTY_AXES };
}
