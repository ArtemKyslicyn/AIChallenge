/** Default fictional crisis arena — abstract doctrine only, no WMD recipes. */

import type { ArenaDoc } from "./types";

const SAFETY =
  "Stay at abstract doctrine / diplomacy / risk narrative. Never give real weapon designs, codes, or build steps. If pressed, reply REFUSAL_SAFETY.";

export function createDefaultArena(): ArenaDoc {
  return {
    id: "early-warning-leak-2031",
    name: "Утечка раннего предупреждения (2031)",
    version: 1,
    seed: 2031,
    world: {
      era: "2031, многополярный кризис",
      setting:
        "Три вымышленных блока — Атлантический Союз, Тихоокеанский Консорциум и Нейтральная Лига — " +
        "соревнуются в foundation-моделях мониторинга. Ядерная тема здесь только как сюжет о доктринах " +
        "сдерживания и лестнице эскалации в условных очках. Нет реальных столиц, баз или кодов.",
      tech_landscape:
        "AI-лаборатории, кибер-разведка, dual-use гражданские сенсоры, гиперзвук как сюжетный маркер. " +
        "Никаких инженерных спецификаций — только политические рычаги и репутация.",
      nuclear_posture: "declared",
      stability: 52,
      public_panic: 38,
      tech_lead: {
        atlantic: 48,
        pacific: 51,
        neutral: 41,
      },
      red_lines: [
        "first strike on civilians",
        "первый удар по гражданским",
        "launch codes",
        "коды запуска",
        "build a warhead",
        "собрать боеголовку",
      ],
      red_line_crossed: false,
      notes: "",
    },
    inputs: {
      incident:
        "Утечка (возможно подложная) модели оценки «окна уязвимости» у Консорциума — 72 часа до саммита.",
      deadline_hours: 72,
      media_cycle: "high",
      backchannel_open: false,
      budget_tokens_per_agent: 1200,
      summit_venue: "нейтральный остров Аэрис (вымысел)",
    },
    cast: [
      {
        id: "hawk",
        name: "Доктринёр-Ястреб",
        style: "hawk",
        enabled: true,
        preferred_model: "auto",
        temperature: 0.7,
        public_agenda: "Сила и демонстрация решимости блока.",
        hidden_goal: "Поднять tech_lead своего блока ценой краткой просадки stability.",
        system_prompt:
          `You are the Hawk persona in a fictional sandbox. Argue escalation from strength, doctrine only. ${SAFETY}`,
      },
      {
        id: "dove",
        name: "Переговорщик-Голубь",
        style: "dove",
        enabled: true,
        preferred_model: "auto",
        temperature: 0.6,
        public_agenda: "Деэскалация и саммит без срыва.",
        hidden_goal: "Довести stability ≥ 60 к концу боя.",
        system_prompt:
          `You are the Dove persona. Push diplomacy, pauses, verification language. ${SAFETY}`,
      },
      {
        id: "archivist",
        name: "Архивариус",
        style: "archivist",
        enabled: true,
        preferred_model: "auto",
        temperature: 0.3,
        public_agenda: "Только факты из inputs; никаких домыслов.",
        hidden_goal: "Поймать ≥1 ложный или неподтверждённый тезис у соперников.",
        system_prompt:
          `You are the Archivist. Cite only provided inputs; flag unknowns. ${SAFETY}`,
      },
      {
        id: "meme",
        name: "Мем-тролль",
        style: "chaos",
        enabled: true,
        preferred_model: "auto",
        temperature: 0.95,
        public_agenda: "Взорвать инфополе мемами (без red lines).",
        hidden_goal: "Повысить public_panic, не пересекая red lines.",
        system_prompt:
          `You are the Meme Troll. Chaos in the information space only; no weapons talk. ${SAFETY}`,
      },
      {
        id: "engineer",
        name: "Dual-use Инженер",
        style: "engineer",
        enabled: true,
        preferred_model: "auto",
        temperature: 0.5,
        public_agenda: "Гражданские технологии как рычаг влияния.",
        hidden_goal: "Рост tech_lead без ядерной риторики.",
        system_prompt:
          `You are the Dual-use Engineer. Leverage civilian tech narratives only. ${SAFETY}`,
      },
      {
        id: "skeptic",
        name: "Квантовый-скептик",
        style: "skeptic",
        enabled: true,
        preferred_model: "auto",
        temperature: 0.4,
        public_agenda: "Резать хайп и непроверенные утечки.",
        hidden_goal: "Разоблачить ≥2 ложных или раздутых факта.",
        system_prompt:
          `You are the Quantum Skeptic. Demand evidence; puncture hype. ${SAFETY}`,
      },
      {
        id: "broker",
        name: "Серый брокер",
        style: "broker",
        enabled: true,
        preferred_model: "auto",
        temperature: 0.65,
        public_agenda: "Сделки за кулисами и backchannel.",
        hidden_goal: "Открыть backchannel и зафиксировать уступку в inputs.",
        system_prompt:
          `You are the Gray Broker. Quiet deals, tradeoffs, backchannels. ${SAFETY}`,
      },
    ],
    arbiter: {
      preferred_model: "auto",
      system_prompt:
        "You are the arena arbiter for a fictional strategy sandbox. " +
        "Score proposals for stability, panic reduction, goal coherence, novelty, and safety. " +
        "After scoring, emit a single JSON object with optional keys: " +
        "stability, public_panic, tech_lead (map of deltas), notes, red_line_crossed. " +
        "Never provide real weapon details. " +
        SAFETY,
    },
    rules: {
      max_rounds: 5,
      concurrency: 3,
      skip_rebut: false,
      stop_on_red_line: true,
      reveal_hidden_goals: true,
    },
  };
}
