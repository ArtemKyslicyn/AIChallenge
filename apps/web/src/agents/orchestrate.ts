/** Client-side multi-agent orchestration (parallel / chain / roundtable). */

export type TeamMode = "parallel" | "chain" | "roundtable";

export const TEAM_MODE_LABEL: Record<TeamMode, string> = {
  parallel: "Параллельно",
  chain: "Цепочка",
  roundtable: "Обсуждение",
};

export const TEAM_MODE_HINT: Record<TeamMode, string> = {
  parallel: "Одна задача всем сразу (fan-out). Сравни ответы.",
  chain: "A → B → C: следующий видит ответ предыдущего (handoff).",
  roundtable: "Сначала все отвечают параллельно, затем каждый комментирует остальных.",
};

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
    `Шаг ${opts.step}/${opts.total}. Предыдущий агент «${opts.fromName}» ответил:`,
    "---",
    opts.fromContent.trim(),
    "---",
    "Продолжи работу с учётом этого ответа. Добавь свой вклад, не повторяй его дословно.",
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
