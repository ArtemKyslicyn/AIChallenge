export interface Turn {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** Which model produced this reply. Null until the model event arrives. */
  modelId: string | null;
  /** The answer was cut short — by the provider or by the reader stopping it. */
  failed?: boolean;
}
