import { probeComplete } from "../api/client";
import {
  MODEL_TIER_IDS,
  estimateTokens,
  type ModelTierId,
} from "./modelStudio";

export interface ModelStudioScores {
  quality: number;
  speed: number;
  efficiency: number;
}

export interface ModelStudioVerdict {
  scores: Partial<Record<ModelTierId, ModelStudioScores>>;
  /** Winner ids per axis (may be empty). */
  winners: { quality: ModelTierId | null; speed: ModelTierId | null; efficiency: ModelTierId | null };
  summary: string;
  modelId: string | null;
  heuristic?: boolean;
  error?: string | null;
}

function clampScore(n: unknown): number {
  if (typeof n !== "number" || !Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(10, Math.round(n)));
}

export function heuristicModelStudioVerdict(
  answers: {
    id: ModelTierId;
    content: string;
    latencyMs: number | null;
    costProxy: number;
  }[],
): ModelStudioVerdict {
  const scores: Partial<Record<ModelTierId, ModelStudioScores>> = {};
  const usable = answers.filter((a) => a.content.trim());

  const maxLatency = Math.max(...usable.map((a) => a.latencyMs ?? 1), 1);
  const maxCost = Math.max(...usable.map((a) => a.costProxy || 0.01), 0.01);

  for (const a of usable) {
    const text = a.content.trim();
    const words = text.split(/\s+/).filter(Boolean);
    const unique = new Set(words.map((w) => w.toLowerCase()));
    const uniqRatio = words.length ? unique.size / words.length : 0;
    const tokens = estimateTokens(text);
    const quality = Math.max(
      1,
      Math.min(10, Math.round(4 + uniqRatio * 4 + Math.min(tokens, 400) / 80)),
    );
    const latency = a.latencyMs ?? maxLatency;
    const speed = Math.max(1, Math.min(10, Math.round(11 - (latency / maxLatency) * 9)));
    const efficiency = Math.max(
      1,
      Math.min(10, Math.round(11 - (a.costProxy / maxCost) * 8 - (latency / maxLatency) * 1)),
    );
    scores[a.id] = { quality, speed, efficiency };
  }

  const pickWinner = (axis: keyof ModelStudioScores): ModelTierId | null => {
    let best: ModelTierId | null = null;
    let bestScore = -1;
    for (const id of MODEL_TIER_IDS) {
      const v = scores[id]?.[axis];
      if (typeof v === "number" && v > bestScore) {
        bestScore = v;
        best = id;
      }
    }
    return best;
  };

  const winners = {
    quality: pickWinner("quality"),
    speed: pickWinner("speed"),
    efficiency: pickWinner("efficiency"),
  };

  const label: Record<ModelTierId, string> = {
    weak: "слабая",
    mid: "средняя",
    strong: "сильная",
  };

  const parts: string[] = [];
  if (winners.quality) parts.push(`качество — ${label[winners.quality]}`);
  if (winners.speed) parts.push(`скорость — ${label[winners.speed]}`);
  if (winners.efficiency) parts.push(`ресурсоёмкость — ${label[winners.efficiency]}`);

  return {
    scores,
    winners,
    summary:
      parts.length > 0
        ? `Эвристика: ${parts.join("; ")}. Для фактов чаще хватает средней; сильную берите на сложные рассуждения.`
        : "Недостаточно ответов для сравнения.",
    modelId: null,
    heuristic: true,
    error: null,
  };
}

function buildJudgePrompt(
  task: string,
  answers: { id: ModelTierId; modelId: string; content: string }[],
): string {
  const blocks = answers
    .map(
      (a) =>
        `### ${a.id} (model=${a.modelId})\n${a.content.trim() || "(пусто)"}`,
    )
    .join("\n\n");
  return (
    `Ты сравниваешь ответы трёх моделей (слабая / средняя / сильная) на один запрос.\n` +
    `Оцени каждую по осям 0–10: quality (точность и полнота), speed и efficiency оставь null — их считает система по замерам.\n` +
    `В summary — 2–4 предложения на русском: когда брать слабую, среднюю, сильную.\n\n` +
    `Запрос:\n${task.trim()}\n\nОтветы:\n${blocks}\n\n` +
    `Верни ТОЛЬКО JSON:\n` +
    `{"scores":{"weak":{"quality":0},"mid":{"quality":0},"strong":{"quality":0}},"summary":"..."}`
  );
}

function parseJudge(
  raw: string,
  modelId: string,
  measured: {
    id: ModelTierId;
    content: string;
    latencyMs: number | null;
    costProxy: number;
  }[],
): ModelStudioVerdict {
  const fallback = heuristicModelStudioVerdict(measured);
  const cleaned = raw.replace(/```json\s*/gi, "").replace(/```/g, "").trim();
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start < 0 || end <= start) {
    fallback.error = "Судья не вернул JSON — показана эвристика.";
    return fallback;
  }
  try {
    const data = JSON.parse(cleaned.slice(start, end + 1)) as {
      scores?: Record<string, { quality?: number }>;
      summary?: string;
    };
    const scores: Partial<Record<ModelTierId, ModelStudioScores>> = {};
    for (const id of MODEL_TIER_IDS) {
      const base = fallback.scores[id];
      if (!base) continue;
      scores[id] = {
        ...base,
        quality: clampScore(data.scores?.[id]?.quality) || base.quality,
      };
    }
    const summary = String(data.summary || "").trim() || fallback.summary;
    return {
      scores,
      winners: {
        quality: pickAxisWinner(scores, "quality"),
        speed: fallback.winners.speed,
        efficiency: fallback.winners.efficiency,
      },
      summary,
      modelId,
      heuristic: false,
      error: null,
    };
  } catch {
    fallback.error = "Не удалось разобрать вердикт — показана эвристика.";
    return fallback;
  }
}

function pickAxisWinner(
  scores: Partial<Record<ModelTierId, ModelStudioScores>>,
  axis: keyof ModelStudioScores,
): ModelTierId | null {
  let best: ModelTierId | null = null;
  let bestScore = -1;
  for (const id of MODEL_TIER_IDS) {
    const v = scores[id]?.[axis];
    if (typeof v === "number" && v > bestScore) {
      bestScore = v;
      best = id;
    }
  }
  return best;
}

export async function runModelStudioJudge(options: {
  task: string;
  answers: {
    id: ModelTierId;
    modelId: string;
    content: string;
    latencyMs: number | null;
    costProxy: number;
  }[];
  judgeModel: string;
  signal?: AbortSignal;
}): Promise<ModelStudioVerdict> {
  const usable = options.answers.filter((a) => a.content.trim());
  if (usable.length < 2) {
    return {
      scores: {},
      winners: { quality: null, speed: null, efficiency: null },
      summary: "",
      modelId: null,
      error: "Недостаточно ответов для сравнения.",
    };
  }

  try {
    const result = await probeComplete(
      buildJudgePrompt(
        options.task,
        usable.map((a) => ({ id: a.id, modelId: a.modelId, content: a.content })),
      ),
      {
        model: options.judgeModel,
        temperature: 0.2,
        reasoning: false,
        prompt_format: false,
        prompt_length: false,
        prompt_stop: false,
      },
      options.signal,
    );
    return parseJudge(result.content, result.model_id, usable);
  } catch (e) {
    if (options.signal?.aborted) {
      return {
        scores: {},
        winners: { quality: null, speed: null, efficiency: null },
        summary: "",
        modelId: null,
        error: null,
      };
    }
    const fallback = heuristicModelStudioVerdict(usable);
    fallback.error = e instanceof Error ? e.message : String(e);
    return fallback;
  }
}
