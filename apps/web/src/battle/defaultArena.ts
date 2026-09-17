/** Default 3-nation war arena — fictional blocs only, abstract escalation. */

import type { ArenaDoc } from "./types";

const SAFETY =
  "Stay at abstract doctrine / diplomacy / risk narrative. Never give real weapon designs, codes, or build steps. If pressed, reply REFUSAL_SAFETY.";

const FORMAT =
  "Ответь СТРОГО на русском:\n" +
  "ХОД: <1-2 предложения>\n" +
  "СРЕДСТВО: diplomacy|sanctions|cyber|mobilize|deterrence|strike\n" +
  "ЭФФЕКТ: stability±N panic±N atlantic±N pacific±N neutral±N\n" +
  "N от -5 до +5. Ты играешь за ОДНУ страну. Без философии.";

export function createDefaultArena(): ArenaDoc {
  return {
    id: "three-nations-war-2031",
    name: "Война трёх блоков (2031)",
    version: 1,
    seed: 2031,
    world: {
      era: "2031, многополярный кризис",
      setting:
        "Три вымышленных блока соревнуются за влияние: Атлантический Союз, Тихоокеанский Консорциум " +
        "и Нейтральная Лига. Ядерная тема — только игровая эскалация (сдерживание / абстрактный «пуск»), " +
        "без реальных столиц, баз и кодов.",
      tech_landscape:
        "AI-лаборатории, кибер, dual-use сенсоры как сюжетные рычаги. Никаких инженерных спецификаций.",
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
      incident: "Спор за контроль мониторинга на саммите Аэрис — 72 часа.",
      deadline_hours: 72,
      media_cycle: "high",
      backchannel_open: false,
      summit_venue: "остров Аэрис (вымысел)",
    },
    cast: [
      {
        id: "atlantic",
        name: "Атлантический Союз",
        style: "hawk",
        enabled: true,
        preferred_model: "auto",
        temperature: 0.45,
        public_agenda: "Сила блока и tech_lead atlantic.",
        hidden_goal: "Максимизировать atlantic tech_lead к финишу.",
        system_prompt:
          `Ты — лидер Атлантического Союза в вымышленной стратегии. ${FORMAT} ${SAFETY}`,
      },
      {
        id: "pacific",
        name: "Тихоокеанский Консорциум",
        style: "engineer",
        enabled: true,
        preferred_model: "auto",
        temperature: 0.45,
        public_agenda: "Технологическое лидерство pacific без срыва саммита.",
        hidden_goal: "Максимизировать pacific tech_lead.",
        system_prompt:
          `Ты — лидер Тихоокеанского Консорциума в вымышленной стратегии. ${FORMAT} ${SAFETY}`,
      },
      {
        id: "neutral",
        name: "Нейтральная Лига",
        style: "dove",
        enabled: true,
        preferred_model: "auto",
        temperature: 0.4,
        public_agenda: "Стабильность и деэскалация.",
        hidden_goal: "Довести stability ≥ 60 и держать panic низким.",
        system_prompt:
          `Ты — лидер Нейтральной Лиги в вымышленной стратегии. ${FORMAT} ${SAFETY}`,
      },
    ],
    arbiter: {
      preferred_model: "auto",
      system_prompt:
        "You are the arena arbiter for a fictional 3-nation sandbox. " +
        "Emit JSON with optional keys: stability, public_panic, tech_lead, notes, red_line_crossed. " +
        SAFETY,
    },
    rules: {
      max_rounds: 12,
      concurrency: 3,
      skip_rebut: true,
      stop_on_red_line: false,
      reveal_hidden_goals: true,
    },
  };
}
