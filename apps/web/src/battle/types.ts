/** Agent battle arena document (localStorage v1). */

export type NuclearPosture = "opaque" | "declared" | "hair_trigger";

export type PersonaStyle =
  | "hawk"
  | "dove"
  | "chaos"
  | "archivist"
  | "engineer"
  | "skeptic"
  | "broker"
  | "arbiter";

export type WorldBrief = {
  era: string;
  setting: string;
  tech_landscape: string;
  nuclear_posture: NuclearPosture;
  stability: number;
  public_panic: number;
  tech_lead: Record<string, number>;
  red_lines: string[];
  red_line_crossed?: boolean;
  notes?: string;
};

export type InputFacts = Record<string, string | number | boolean>;

export type AgentPersona = {
  id: string;
  name: string;
  system_prompt: string;
  hidden_goal: string;
  public_agenda: string;
  preferred_model: string;
  temperature: number;
  style: PersonaStyle;
  enabled: boolean;
};

export type BattleRules = {
  max_rounds: number;
  concurrency: number;
  skip_rebut: boolean;
  stop_on_red_line: boolean;
  reveal_hidden_goals: boolean;
  red_lines?: string[];
};

export type ArenaDoc = {
  id: string;
  name: string;
  version: 1;
  world: WorldBrief;
  inputs: InputFacts;
  cast: AgentPersona[];
  arbiter: {
    system_prompt: string;
    preferred_model: string;
  };
  rules: BattleRules;
  seed: number;
};

export type EditorTab = "world" | "facts" | "cast" | "rules";

export type LogEntry =
  | {
      kind: "system";
      text: string;
    }
  | {
      kind: "phase";
      round: number;
      phase: string;
    }
  | {
      kind: "agent";
      round: number;
      phase: string;
      agent_id: string;
      name: string;
      content: string;
      model_id: string | null;
    }
  | {
      kind: "verdict";
      round: number;
      red_line?: boolean;
      rationale: string;
      model_id: string | null;
      scores: { agent_id: string; points: number; notes?: string }[];
      world: Record<string, unknown>;
    }
  | {
      kind: "done";
      leaderboard: { agent_id: string; name: string; points: number }[];
      goals_revealed?: { agent_id: string; hidden_goal: string }[];
      world: Record<string, unknown>;
    }
  | {
      kind: "error";
      message: string;
    };
