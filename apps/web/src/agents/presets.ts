import type { AgentDefinitionDto } from "../api/client";
import { AGGREGATOR_DEFINITION } from "./progon";

/** Client-side Day-6 presets (no server YAML). */
export const AGENT_PRESETS: AgentDefinitionDto[] = [
  {
    name: "Краткий редактор",
    system_prompt:
      "Ты краткий редактор текста. Правишь стиль и ясность, не меняя смысл. Отвечай только отредактированным текстом без предисловий.",
    preferred_model: "auto",
    temperature: 0.3,
    max_tokens: 512,
  },
  {
    name: "Объяснятор",
    system_prompt:
      "Ты терпеливый преподаватель. Объясняй просто, коротко, с одним примером. Без воды и без списков из десяти пунктов, если не просят.",
    preferred_model: "auto",
    temperature: 0.5,
    max_tokens: 700,
  },
  {
    name: AGGREGATOR_DEFINITION.name,
    system_prompt: AGGREGATOR_DEFINITION.system_prompt,
    preferred_model: AGGREGATOR_DEFINITION.preferred_model,
    temperature: AGGREGATOR_DEFINITION.temperature ?? 0.3,
    max_tokens: AGGREGATOR_DEFINITION.max_tokens ?? 900,
  },
];
