import { probeComplete, type ProbeGenerationDto } from "../api/client";
import {
  buildExpertRolePrompt,
  buildExpertSynthesisPrompt,
  buildMetaPhase2Prompt,
  buildStrategyPrompt,
} from "./buildPrompt";
import type { ExpertRoleId } from "./buildPrompt";
import type { PromptStrategyId } from "./types";

export interface ProbeRunOptions {
  model: string;
  temperature: number;
  reasoning: boolean;
  sessionContext?: string;
}

export interface ExpertSlotResult {
  id: ExpertRoleId;
  label: string;
  content: string;
  model_id: string | null;
  error: string | null;
  loading: boolean;
}

export interface StrategyRunResult {
  content: string;
  model_id: string;
  metaPrompt?: string;
  expertSlots?: ExpertSlotResult[];
  latencyMs?: number;
}

type StatusFn = (hint: string) => void;
type ExpertProgressFn = (slots: ExpertSlotResult[]) => void;

export async function runPromptStrategy(
  strategyId: PromptStrategyId,
  taskText: string,
  options: ProbeRunOptions,
  signal?: AbortSignal,
  onStatus?: StatusFn,
  onExpertProgress?: ExpertProgressFn,
): Promise<StrategyRunResult> {
  const body: { model: string } & ProbeGenerationDto = {
    model: options.model,
    temperature: options.temperature,
    reasoning: options.reasoning,
    prompt_format: false,
    prompt_length: false,
    prompt_stop: false,
  };
  const started = performance.now();

  if (strategyId === "expert_panel") {
    return runExpertPanel(taskText, options, body, signal, onStatus, onExpertProgress, started);
  }

  if (strategyId === "meta_prompt") {
    onStatus?.("Фаза 1: составляем промпт…");
    const phase1 = await probeComplete(
      buildStrategyPrompt("meta_prompt", taskText, options.sessionContext),
      body,
      signal,
    );
    const metaPrompt = phase1.content.trim();
    if (!metaPrompt) {
      throw new Error("Meta-prompt: модель не вернула текст промпта.");
    }
    onStatus?.("Фаза 2: решаем по промпту…");
    const phase2 = await probeComplete(buildMetaPhase2Prompt(metaPrompt), body, signal);
    return {
      content: phase2.content,
      model_id: phase2.model_id,
      metaPrompt,
      latencyMs: Math.round(performance.now() - started),
    };
  }

  const prompt = buildStrategyPrompt(strategyId, taskText, options.sessionContext);
  const result = await probeComplete(prompt, body, signal);
  return {
    content: result.content,
    model_id: result.model_id,
    latencyMs: Math.round(performance.now() - started),
  };
}

async function runExpertPanel(
  taskText: string,
  options: ProbeRunOptions,
  body: { model: string } & ProbeGenerationDto,
  signal: AbortSignal | undefined,
  onStatus: StatusFn | undefined,
  onExpertProgress: ExpertProgressFn | undefined,
  started: number,
): Promise<StrategyRunResult> {
  const labels: Record<Exclude<ExpertRoleId, "synthesis">, string> = {
    analyst: "Аналитик",
    engineer: "Инженер",
    critic: "Критик",
  };
  const roles = ["analyst", "engineer", "critic"] as const;

  let slots: ExpertSlotResult[] = [
    ...roles.map((id) => ({
      id,
      label: labels[id],
      content: "",
      model_id: null as string | null,
      error: null as string | null,
      loading: true,
    })),
    {
      id: "synthesis" as const,
      label: "Итог",
      content: "",
      model_id: null,
      error: null,
      loading: false,
    },
  ];
  onExpertProgress?.(slots);
  onStatus?.("Эксперты 0/3…");

  const results = await Promise.all(
    roles.map(async (roleId) => {
      try {
        const res = await probeComplete(
          buildExpertRolePrompt(roleId, taskText, options.sessionContext),
          body,
          signal,
        );
        return { roleId, ok: true as const, content: res.content, model_id: res.model_id };
      } catch (e) {
        return {
          roleId,
          ok: false as const,
          error: e instanceof Error ? e.message : String(e),
        };
      }
    }),
  );

  const byRole: Record<string, string> = { analyst: "", engineer: "", critic: "" };
  let lastModel: string | null = null;
  let done = 0;
  slots = slots.map((slot) => {
    if (slot.id === "synthesis") return slot;
    const hit = results.find((r) => r.roleId === slot.id)!;
    if (hit.ok) {
      done += 1;
      byRole[slot.id] = hit.content;
      lastModel = hit.model_id;
      return {
        ...slot,
        loading: false,
        content: hit.content,
        model_id: hit.model_id,
        error: null,
      };
    }
    return {
      ...slot,
      loading: false,
      content: "",
      model_id: null,
      error: hit.error,
    };
  });
  onExpertProgress?.(slots);
  onStatus?.(`Эксперты ${done}/3 · синтез…`);

  slots = slots.map((s) =>
    s.id === "synthesis" ? { ...s, loading: true } : s,
  );
  onExpertProgress?.(slots);

  try {
    const synth = await probeComplete(
      buildExpertSynthesisPrompt(
        taskText,
        {
          analyst: byRole.analyst,
          engineer: byRole.engineer,
          critic: byRole.critic,
        },
        options.sessionContext,
      ),
      body,
      signal,
    );
    slots = slots.map((s) =>
      s.id === "synthesis"
        ? {
            ...s,
            loading: false,
            content: synth.content,
            model_id: synth.model_id,
            error: null,
          }
        : s,
    );
    onExpertProgress?.(slots);
    const composed = [
      `### Аналитик\n${byRole.analyst || "—"}`,
      `### Инженер\n${byRole.engineer || "—"}`,
      `### Критик\n${byRole.critic || "—"}`,
      `### Итог\n${synth.content}`,
    ].join("\n\n");
    return {
      content: composed,
      model_id: synth.model_id || lastModel || options.model,
      expertSlots: slots,
      latencyMs: Math.round(performance.now() - started),
    };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    slots = slots.map((s) =>
      s.id === "synthesis"
        ? { ...s, loading: false, error: msg, content: "" }
        : s,
    );
    onExpertProgress?.(slots);
    const composed = [
      `### Аналитик\n${byRole.analyst || "—"}`,
      `### Инженер\n${byRole.engineer || "—"}`,
      `### Критик\n${byRole.critic || "—"}`,
      `### Итог\n(ошибка синтеза: ${msg})`,
    ].join("\n\n");
    if (done === 0) throw new Error(msg);
    return {
      content: composed,
      model_id: lastModel || options.model,
      expertSlots: slots,
      latencyMs: Math.round(performance.now() - started),
    };
  }
}
