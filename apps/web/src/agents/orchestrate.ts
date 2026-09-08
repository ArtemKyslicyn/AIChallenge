/** Client-side multi-agent orchestration (parallel / chain / roundtable). */

export type TeamMode = "parallel" | "chain" | "roundtable";

export const TEAM_MODE_LABEL: Record<TeamMode, string> = {
  parallel: "Параллельно",
  chain: "Цепочка",
  roundtable: "Обсуждение",
};

export const TEAM_MODE_HINT: Record<TeamMode, string> = {
  parallel: "Одна задача — всем сразу. Удобно сравнить ответы.",
  chain: "По очереди: следующий видит ответ предыдущего. Порядок = номера в составе.",
  roundtable: "Сначала все отвечают, потом каждый коротко комментирует остальных.",
};

export const TEAM_MODE_SCHEME: Record<TeamMode, string> = {
  parallel: "A · B · C",
  chain: "A → B → C",
  roundtable: "A ↔ B ↔ C",
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
