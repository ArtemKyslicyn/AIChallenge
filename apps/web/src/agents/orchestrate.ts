/**
 * Client-side multi-agent orchestration patterns:
 * - parallel: fan-out (optional fan-in synthesize)
 * - chain: sequential handoff
 * - roundtable: peer review rounds (+ optional synthesize)
 * - progon: matrix fan-out / fan-in (models or temperatures)
 *
 * Aligned with common 2025–26 practice: supervisor + parallel workers + dedicated reducer.
 */

import {
  AGGREGATOR_DEFINITION,
  buildProgonAggregateMessage,
  type ProgonPart,
} from "./progon";

export type TeamMode = "parallel" | "chain" | "roundtable" | "progon";

export const TEAM_MODE_LABEL: Record<TeamMode, string> = {
  parallel: "Параллельно",
  chain: "Цепочка",
  roundtable: "Обсуждение",
  progon: "Прогон",
};

export const TEAM_MODE_HINT: Record<TeamMode, string> = {
  parallel:
    "Fan-out: одна задача всем в составе сразу. При включённой склейке — fan-in через «Склейщик».",
  chain: "Sequential handoff: A → B → C. Следующий видит ответ предыдущего. Порядок = номера.",
  roundtable: "Раунд 1 параллельно, раунд 2 — комментарии. Опционально финальная склейка.",
  progon:
    "Матрица вариантов (temperature или модели) → параллельные субагенты → склейка. Префикс /прогон необязателен.",
};

export const TEAM_MODE_SCHEME: Record<TeamMode, string> = {
  parallel: "A∥B∥C → Σ",
  chain: "A → B → C",
  roundtable: "A↔B · Σ",
  progon: "t/m ∥ → Σ",
};

export { AGGREGATOR_DEFINITION };

export function buildChainHandoff(opts: {
  task: string;
  fromName: string;
  fromContent: string;
  step: number;
  total: number;
}): string {
  return [
    `Общая задача команды: ${opts.task}`,
    "",
    `Handoff ${opts.step}/${opts.total}. Предыдущий агент «${opts.fromName}» передал:`,
    "---",
    opts.fromContent.trim(),
    "---",
    "Продолжи со своей ролью. Добавь вклад, не копируй предыдущий ответ целиком. Если видишь ошибку — коротко поправь.",
  ].join("\n");
}

export function buildRoundtableFollowup(opts: {
  task: string;
  selfName: string;
  peers: { name: string; content: string }[];
}): string {
  const others = opts.peers
    .filter((p) => p.name !== opts.selfName)
    .map((p) => `«${p.name}»:\n${p.content.trim()}`)
    .join("\n\n");
  return [
    `Общая задача: ${opts.task}`,
    "",
    "Ответы коллег (раунд 1):",
    others || "(нет других ответов)",
    "",
    `Ты — «${opts.selfName}». Кратко отреагируй: согласись, поправь или дополни. Не пересказывай всё заново.`,
  ].join("\n");
}

/** Fan-in message after parallel or roundtable (dedicated reducer). */
export function buildTeamFanInMessage(opts: {
  task: string;
  parts: ProgonPart[];
  contextLabel?: string;
}): string {
  return buildProgonAggregateMessage({
    task: opts.task,
    parts: opts.parts,
  });
}

export function teamRequestBudget(opts: {
  mode: TeamMode;
  memberCount: number;
  variantCount: number;
  fanIn: boolean;
  roundtableRounds?: 1 | 2;
}): number {
  const n = Math.max(0, opts.memberCount);
  switch (opts.mode) {
    case "parallel":
      return n + (opts.fanIn && n > 1 ? 1 : 0);
    case "chain":
      return n;
    case "roundtable": {
      const r2 = (opts.roundtableRounds ?? 2) === 2 && n >= 2 ? n : 0;
      return n + r2 + (opts.fanIn && n > 1 ? 1 : 0);
    }
    case "progon":
      return opts.variantCount + (opts.fanIn && opts.variantCount > 0 ? 1 : 0);
    default:
      return n;
  }
}
