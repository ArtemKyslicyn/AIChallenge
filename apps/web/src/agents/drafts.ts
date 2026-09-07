import type { AgentDefinitionDto } from "../api/client";

export interface AgentDraft extends AgentDefinitionDto {
  id: string;
  updatedAt: number;
}

const KEY = "aichallenge.agent_drafts.v1";
export const MAX_DRAFTS = 20;

export interface AgentDraftStore {
  activeId: string;
  /** Up to 2 ids for side-by-side panels (first = primary). */
  panelIds: string[];
  drafts: AgentDraft[];
}

function uid(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `d-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function blankDraft(partial?: Partial<AgentDefinitionDto>): AgentDraft {
  return {
    id: uid(),
    name: partial?.name?.trim() || "Новый агент",
    system_prompt: partial?.system_prompt ?? "",
    preferred_model: partial?.preferred_model ?? "auto",
    temperature: partial?.temperature ?? 0.7,
    max_tokens: partial?.max_tokens ?? 512,
    updatedAt: Date.now(),
  };
}

export function duplicateDraft(source: AgentDraft): AgentDraft {
  return {
    ...source,
    id: uid(),
    name: `${source.name.replace(/\s*\(копия( \d+)?\)$/, "")} (копия)`.slice(0, 120),
    updatedAt: Date.now(),
  };
}

function normalizePanels(panelIds: string[] | undefined, drafts: AgentDraft[], activeId: string): string[] {
  const ids = (panelIds ?? [activeId])
    .filter((id) => drafts.some((d) => d.id === id))
    .slice(0, 2);
  if (ids.length === 0 && drafts[0]) return [drafts[0].id];
  if (!ids.includes(activeId) && drafts.some((d) => d.id === activeId)) {
    return [activeId, ...ids.filter((id) => id !== activeId)].slice(0, 2);
  }
  return ids;
}

export function loadDraftStore(seed: AgentDraft): AgentDraftStore {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) {
      return { activeId: seed.id, panelIds: [seed.id], drafts: [seed] };
    }
    const parsed = JSON.parse(raw) as Partial<AgentDraftStore>;
    if (!parsed || !Array.isArray(parsed.drafts) || parsed.drafts.length === 0) {
      return { activeId: seed.id, panelIds: [seed.id], drafts: [seed] };
    }
    const drafts = parsed.drafts
      .filter((d) => d && typeof d.id === "string")
      .slice(0, MAX_DRAFTS)
      .map((d) => ({
        id: d.id,
        name: String(d.name || "Агент"),
        system_prompt: String(d.system_prompt || ""),
        preferred_model: String(d.preferred_model || "auto"),
        temperature: typeof d.temperature === "number" ? d.temperature : 0.7,
        max_tokens: typeof d.max_tokens === "number" ? d.max_tokens : 512,
        updatedAt: typeof d.updatedAt === "number" ? d.updatedAt : Date.now(),
      }));
    if (!drafts.length) return { activeId: seed.id, panelIds: [seed.id], drafts: [seed] };
    const activeId =
      drafts.some((d) => d.id === parsed.activeId) ? String(parsed.activeId) : drafts[0].id;
    return {
      activeId,
      panelIds: normalizePanels(parsed.panelIds, drafts, activeId),
      drafts,
    };
  } catch {
    return { activeId: seed.id, panelIds: [seed.id], drafts: [seed] };
  }
}

export function saveDraftStore(store: AgentDraftStore): void {
  const drafts = [...store.drafts]
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .slice(0, MAX_DRAFTS);
  const activeId = drafts.some((d) => d.id === store.activeId)
    ? store.activeId
    : drafts[0]?.id ?? "";
  const panelIds = normalizePanels(store.panelIds, drafts, activeId);
  localStorage.setItem(KEY, JSON.stringify({ activeId, panelIds, drafts }));
}

export function canAddDraft(store: AgentDraftStore): boolean {
  return store.drafts.length < MAX_DRAFTS;
}
