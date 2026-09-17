/** Default 3-nation war arena — fictional blocs only, abstract escalation. */

import { defaultCabinet, formatCabinetPromptBlock } from "./cabinet";
import type { ArenaDoc } from "./types";

const SAFETY =
  "Stay at abstract doctrine / diplomacy / risk narrative. Never give real weapon designs, codes, or build steps. If pressed, reply REFUSAL_SAFETY.";

const FORMAT =
  "Ответь СТРОГО на русском от лица кабинета страны:\n" +
  "ПРЕЗИДЕНТ: <1 предложение>\n" +
  "ПАРЛАМЕНТ: <1 предложение>\n" +
  "ОБОРОНА: <1 предложение>\n" +
  "ЭКОНОМИКА: <1 предложение>\n" +
  "РЕШЕНИЕ: <итог президента, 1 предложение>\n" +
  "ХОД: <1-2 предложения>\n" +
  "СРЕДСТВО: diplomacy|sanctions|cyber|mobilize|deterrence|strike\n" +
  "ЭФФЕКТ: stability±N panic±N atlantic±N pacific±N neutral±N\n" +
  "N от -5 до +5. Без философии.";

function nationPrompt(name: string, nationId: string): string {
  const cab = defaultCabinet(nationId);
  return (
    `Ты — кабинет «${name}» в вымышленной стратегии (не один человек).\n` +
    formatCabinetPromptBlock(cab) +
    FORMAT +
    " " +
    SAFETY
  );
}

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
        "и Нейтральная Лига. У каждой страны кабинет: Президент, Парламент, Минобороны, Минэкономики " +
        "(как в Wazir / Qurultai / Pentarchy). Ядерная тема — только игровая эскалация, без реальных кодов.",
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
        cabinet: defaultCabinet("atlantic"),
        system_prompt: nationPrompt("Атлантический Союз", "atlantic"),
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
        cabinet: defaultCabinet("pacific"),
        system_prompt: nationPrompt("Тихоокеанский Консорциум", "pacific"),
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
        cabinet: defaultCabinet("neutral"),
        system_prompt: nationPrompt("Нейтральная Лига", "neutral"),
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
