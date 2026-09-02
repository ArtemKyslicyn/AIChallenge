import { probeComplete } from "../api/client";
import { buildJudgePrompt } from "./buildPrompt";
import type { PromptStrategyId } from "./types";
import { PROMPT_STRATEGIES } from "./definitions";

export interface JudgeScorecard {
  winnerId: PromptStrategyId | null;
  scores: Partial<Record<PromptStrategyId, number>>;
  rationale: string;
  accuracyNotes: string;
  modelId: string | null;
  raw?: string;
  error?: string | null;
}

const EMPTY_SCORES: Partial<Record<PromptStrategyId, number>> = {
  direct: 0,
  step_by_step: 0,
  meta_prompt: 0,
  expert_panel: 0,
};

export async function runLabJudge(options: {
  task: string;
  goldenAnswer?: string;
  rubric?: string;
  answers: { id: PromptStrategyId; content: string }[];
  model: string;
  temperature?: number;
  signal?: AbortSignal;
}): Promise<JudgeScorecard> {
  const labeled = options.answers.map((a) => ({
    id: a.id,
    label: PROMPT_STRATEGIES.find((s) => s.id === a.id)?.label ?? a.id,
    content: a.content,
  }));
  const prompt = buildJudgePrompt(
    options.task,
    options.goldenAnswer ?? "",
    options.rubric ?? "",
    labeled,
  );
  try {
    const result = await probeComplete(
      prompt,
      {
        model: options.model,
        temperature: options.temperature ?? 0.2,
        reasoning: false,
        prompt_format: false,
        prompt_length: false,
        prompt_stop: false,
      },
      options.signal,
    );
    return parseJudgeJson(result.content, result.model_id);
  } catch (e) {
    return {
      winnerId: null,
      scores: { ...EMPTY_SCORES },
      rationale: "",
      accuracyNotes: "",
      modelId: null,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

function parseJudgeJson(raw: string, modelId: string): JudgeScorecard {
  const cleaned = raw.replace(/```json\s*/gi, "").replace(/```/g, "").trim();
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start < 0 || end <= start) {
    return {
      winnerId: null,
      scores: { ...EMPTY_SCORES },
      rationale: cleaned.slice(0, 280),
      accuracyNotes: "",
      modelId,
      raw: cleaned,
      error: "Судья не вернул JSON.",
    };
  }
  try {
    const data = JSON.parse(cleaned.slice(start, end + 1)) as {
      winner_id?: string;
      scores?: Record<string, number>;
      rationale?: string;
      accuracy_notes?: string;
    };
    const scores: Partial<Record<PromptStrategyId, number>> = { ...EMPTY_SCORES };
    for (const id of Object.keys(EMPTY_SCORES) as PromptStrategyId[]) {
      const v = data.scores?.[id];
      if (typeof v === "number") scores[id] = Math.max(0, Math.min(10, Math.round(v)));
    }
    const winnerRaw = data.winner_id;
    const winnerId =
      winnerRaw && winnerRaw in EMPTY_SCORES
        ? (winnerRaw as PromptStrategyId)
        : (Object.entries(scores).sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0))[0]?.[0] as
            | PromptStrategyId
            | undefined) ?? null;
    return {
      winnerId,
      scores,
      rationale: String(data.rationale || "").trim(),
      accuracyNotes: String(data.accuracy_notes || "").trim(),
      modelId,
      raw: cleaned,
      error: null,
    };
  } catch {
    return {
      winnerId: null,
      scores: { ...EMPTY_SCORES },
      rationale: cleaned.slice(0, 280),
      accuracyNotes: "",
      modelId,
      raw: cleaned,
      error: "Не удалось разобрать вердикт судьи.",
    };
  }
}
