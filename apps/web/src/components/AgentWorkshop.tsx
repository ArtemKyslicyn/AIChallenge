import { useEffect, useId, useMemo, useRef, useState } from "react";

import {
  ApiError,
  clearAgentDialogByDraft,
  forkAgentDialog,
  getAgentDialogByDraft,
  listModels,
  runAgentWorkshop,
  type AgentDialogMessageDto,
  type ModelCatalogItemDto,
} from "../api/client";
import {
  blankDraft,
  canAddDraft,
  duplicateDraft,
  loadDraftStore,
  saveDraftStore,
  type AgentDraft,
  type AgentDraftStore,
  MAX_DRAFTS,
} from "../agents/drafts";
import {
  buildChainHandoff,
  buildRoundtableFollowup,
  buildTeamFanInMessage,
  TEAM_MODE_HINT,
  TEAM_MODE_LABEL,
  TEAM_MODE_SCHEME,
  teamRequestBudget,
  type TeamMode,
} from "../agents/orchestrate";
import {
  AGGREGATOR_DEFINITION,
  buildProgonVariants,
  markdownJoinParts,
  pickDefaultModelIds,
  PROGON_DEFAULT_TEMPERATURES,
  stripProgonTrigger,
  type ProgonAxis,
  type ProgonPart,
} from "../agents/progon";
import { AGENT_PRESETS } from "../agents/presets";
import {
  emptySession,
  ensureSession,
  loadSessions,
  saveSessions,
  type AgentSession,
  type ContextMode,
  type RunLine,
} from "../agents/sessions";

const CONTEXT_MODE_LABELS: Record<ContextMode, string> = {
  none: "Без эффектов",
  compress: "Сжатие",
  sliding: "Окно",
  facts: "Facts",
};

type WorkspaceMode = "solo" | "team";

const WORKSPACE_KEY = "aichallenge.agent_workspace_mode";

function loadWorkspaceMode(): WorkspaceMode {
  try {
    const v = sessionStorage.getItem(WORKSPACE_KEY);
    if (v === "team" || v === "solo") return v;
  } catch {
    /* ignore */
  }
  return "solo";
}

function draftById(store: AgentDraftStore, id: string): AgentDraft | undefined {
  return store.drafts.find((d) => d.id === id);
}

function uid(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID().slice(0, 8)
    : String(Date.now()).slice(-8);
}

function dialogMessagesToLog(messages: AgentDialogMessageDto[]): RunLine[] {
  return messages
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => ({
      id: m.id,
      messageId: m.id,
      role: m.role as "user" | "assistant",
      text: m.content,
      modelId: m.model_id ?? null,
    }));
}


interface TeamEvent {
  id: string;
  kind: "task" | "reply" | "error" | "status";
  agentName?: string;
  text: string;
  modelId?: string | null;
  tag?: string;
}

export function AgentWorkshop() {
  const titleId = useId();
  const [store, setStore] = useState<AgentDraftStore>(() =>
    loadDraftStore(blankDraft(AGENT_PRESETS[0])),
  );
  const [sessions, setSessions] = useState<Record<string, AgentSession>>(() => loadSessions());
  const [busyIds, setBusyIds] = useState<Record<string, boolean>>({});
  const [savedFlash, setSavedFlash] = useState(false);
  const [models, setModels] = useState<ModelCatalogItemDto[]>([]);
  const [mobileSheet, setMobileSheet] = useState(false);
  const [libraryQuery, setLibraryQuery] = useState("");
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>(() => loadWorkspaceMode());
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [teamMode, setTeamMode] = useState<TeamMode>("parallel");
  const [teamTask, setTeamTask] = useState("");
  const [teamLog, setTeamLog] = useState<TeamEvent[]>([]);
  const [teamBusy, setTeamBusy] = useState(false);
  const [fanIn, setFanIn] = useState(true);
  const [progonAxis, setProgonAxis] = useState<ProgonAxis>("temperature");
  const [progonModelIds, setProgonModelIds] = useState<string[]>([]);
  const abortMap = useRef<Map<string, AbortController>>(new Map());
  const teamAbort = useRef<AbortController | null>(null);
  const saveTimer = useRef<number | null>(null);
  const sessionTimer = useRef<number | null>(null);
  const storeRef = useRef(store);
  storeRef.current = store;
  const sessionsRef = useRef(sessions);
  sessionsRef.current = sessions;

  const active = draftById(store, store.activeId) ?? store.drafts[0];
  const panelIds = store.panelIds.length ? store.panelIds : [store.activeId];
  const split = panelIds.length > 1;
  const isTeam = workspaceMode === "team";

  /** Team composition preserves selection / reorder order (chain steps). */
  const teamOrderedIds = useMemo(
    () => selectedIds.filter((id) => store.drafts.some((d) => d.id === id)),
    [store.drafts, selectedIds],
  );

  const teamOrderIndex = useMemo(() => {
    const map = new Map<string, number>();
    teamOrderedIds.forEach((id, i) => map.set(id, i + 1));
    return map;
  }, [teamOrderedIds]);

  const progonVariantsPreview = useMemo(() => {
    if (teamMode !== "progon") return [];
    const baseId = teamOrderedIds[0];
    const base = baseId ? draftById(store, baseId) : undefined;
    if (!base) return [];
    return buildProgonVariants(
      {
        name: base.name,
        system_prompt: base.system_prompt,
        preferred_model: base.preferred_model,
        temperature: base.temperature,
        max_tokens: base.max_tokens,
      },
      {
        axis: progonAxis,
        temperatures: [...PROGON_DEFAULT_TEMPERATURES],
        modelIds: progonModelIds,
      },
    );
  }, [teamMode, teamOrderedIds, store, progonAxis, progonModelIds]);

  const teamBlockReason = useMemo(() => {
    const effectiveTask = stripProgonTrigger(teamTask).task;
    if (!effectiveTask) return "Введите задачу для команды";

    if (teamMode === "progon") {
      if (teamOrderedIds.length < 1) return "Выберите базового агента в составе";
      if (progonAxis === "model" && progonModelIds.length < 2) {
        return "Для прогона по моделям отметьте минимум 2 модели";
      }
      if (progonAxis === "temperature" && progonVariantsPreview.length < 2) {
        return "Не удалось собрать варианты temperature";
      }
      return null;
    }
    if (teamOrderedIds.length < 1) return "Добавьте агентов в состав";
    if (teamMode === "chain" && teamOrderedIds.length < 2) return "Для цепочки нужно минимум 2 агента";
    if (teamMode === "roundtable" && teamOrderedIds.length < 2) {
      return "Для обсуждения нужно минимум 2 агента";
    }
    return null;
  }, [
    teamTask,
    teamOrderedIds,
    teamMode,
    progonAxis,
    progonModelIds,
    progonVariantsPreview.length,
  ]);

  const requestBudget = useMemo(() => {
    return teamRequestBudget({
      mode: teamMode,
      memberCount: teamOrderedIds.length,
      variantCount: progonVariantsPreview.length,
      fanIn:
        teamMode === "progon" || teamMode === "parallel" || teamMode === "roundtable"
          ? fanIn
          : false,
    });
  }, [teamMode, teamOrderedIds.length, progonVariantsPreview.length, fanIn]);

  useEffect(() => {
    listModels()
      .then((list) => {
        setModels(list);
        setProgonModelIds((prev) => (prev.length ? prev : pickDefaultModelIds(list, 3)));
      })
      .catch(() => setModels([]));
  }, []);

  useEffect(() => {
    try {
      sessionStorage.setItem(WORKSPACE_KEY, workspaceMode);
    } catch {
      /* ignore */
    }
  }, [workspaceMode]);

  useEffect(() => {
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      saveDraftStore(store);
      setSavedFlash(true);
      window.setTimeout(() => setSavedFlash(false), 1200);
    }, 350);
    return () => {
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
    };
  }, [store]);

  useEffect(() => {
    if (sessionTimer.current) window.clearTimeout(sessionTimer.current);
    sessionTimer.current = window.setTimeout(() => saveSessions(sessions), 200);
    return () => {
      if (sessionTimer.current) window.clearTimeout(sessionTimer.current);
    };
  }, [sessions]);

  useEffect(() => {
    return () => {
      for (const c of abortMap.current.values()) c.abort();
      abortMap.current.clear();
      teamAbort.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!isTeam && store.activeId) {
      void hydrateDialog(store.activeId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- boot / mode switch only
  }, [isTeam, store.activeId]);

  const modelOptions = useMemo(() => {
    const ids = new Set(models.map((m) => m.id));
    if (!ids.has("auto")) return [{ id: "auto", label: "auto" }, ...models];
    return models;
  }, [models]);

  const filteredDrafts = useMemo(() => {
    const q = libraryQuery.trim().toLowerCase();
    if (!q) return store.drafts;
    return store.drafts.filter(
      (d) =>
        d.name.toLowerCase().includes(q) ||
        d.system_prompt.toLowerCase().includes(q),
    );
  }, [store.drafts, libraryQuery]);

  function setMode(mode: WorkspaceMode) {
    setWorkspaceMode(mode);
    if (mode === "team") {
      setSelectedIds((prev) => {
        if (prev.length) return prev;
        const id = storeRef.current.activeId;
        return id ? [id] : [];
      });
      // Prefer single panel focus in team — answers live in team log
      setStore((prev) => ({ ...prev, panelIds: [prev.activeId] }));
    }
  }

  function patchSession(id: string, patch: Partial<AgentSession>) {
    setSessions((prev) => {
      const next = {
        ...prev,
        [id]: { ...ensureSession(prev, id), ...patch },
      };
      sessionsRef.current = next;
      return next;
    });
  }

  function appendLog(id: string, line: RunLine) {
    setSessions((prev) => {
      const cur = ensureSession(prev, id);
      const next = { ...prev, [id]: { ...cur, log: [...cur.log, line] } };
      sessionsRef.current = next;
      return next;
    });
  }

  function pushTeam(ev: Omit<TeamEvent, "id">) {
    setTeamLog((prev) => [...prev, { ...ev, id: `t-${Date.now()}-${Math.random()}` }]);
  }

  function patchDraft(id: string, patch: Partial<AgentDraft>) {
    setStore((prev) => ({
      ...prev,
      drafts: prev.drafts.map((d) =>
        d.id === id ? { ...d, ...patch, updatedAt: Date.now() } : d,
      ),
    }));
  }

  function toggleSelect(id: string) {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function moveTeamMember(id: string, dir: -1 | 1) {
    setSelectedIds((prev) => {
      const i = prev.indexOf(id);
      if (i < 0) return prev;
      const j = i + dir;
      if (j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  }

  function focusAgent(id: string) {
    setStore((prev) => {
      const nextPanels =
        !isTeam && prev.panelIds.length > 1 && prev.panelIds.includes(id)
          ? prev.panelIds
          : !isTeam && prev.panelIds.length > 1
            ? [id, ...prev.panelIds.filter((x) => x !== id)].slice(0, 2)
            : [id];
      return { ...prev, activeId: id, panelIds: nextPanels };
    });
    setMobileSheet(false);
    void hydrateDialog(id);
  }

  function openSplitWith(id: string) {
    if (isTeam) return;
    setStore((prev) => {
      const primary = prev.activeId;
      if (id === primary) return prev;
      return { ...prev, activeId: id, panelIds: [primary, id].slice(0, 2) };
    });
  }

  function closeSplit() {
    setStore((prev) => ({ ...prev, panelIds: [prev.activeId] }));
  }

  function newDraft(from?: Partial<AgentDraft>) {
    if (!canAddDraft(store)) {
      window.alert(`Лимит ${MAX_DRAFTS} агентов. Удалите лишние.`);
      return;
    }
    const next = blankDraft(from);
    setSessions((prev) => ({ ...prev, [next.id]: emptySession() }));
    setStore((prev) => ({
      activeId: next.id,
      panelIds: !isTeam && split ? [next.id, ...prev.panelIds].slice(0, 2) : [next.id],
      drafts: [next, ...prev.drafts],
    }));
    if (isTeam) setSelectedIds((prev) => [...prev, next.id]);
  }

  function createFromPreset(index: number) {
    const preset = AGENT_PRESETS[index];
    if (!preset) return;
    newDraft(preset);
  }

  function onDuplicate(id: string) {
    const source = draftById(store, id);
    if (!source) return;
    if (!canAddDraft(store)) {
      window.alert(`Лимит ${MAX_DRAFTS} агентов.`);
      return;
    }
    const next = duplicateDraft(source);
    setSessions((prev) => ({ ...prev, [next.id]: emptySession() }));
    setStore((prev) => ({
      activeId: next.id,
      panelIds: !isTeam && split ? [next.id, prev.activeId].slice(0, 2) : [next.id],
      drafts: [next, ...prev.drafts],
    }));
    if (isTeam) setSelectedIds((prev) => [...prev, next.id]);
  }

  function onDelete(id: string) {
    if (store.drafts.length <= 1) {
      window.alert("Нужен хотя бы один агент.");
      return;
    }
    const d = draftById(store, id);
    if (!d || !window.confirm(`Удалить «${d.name}»?`)) return;
    abortMap.current.get(id)?.abort();
    abortMap.current.delete(id);
    setBusyIds((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    setSessions((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    setSelectedIds((prev) => prev.filter((x) => x !== id));
    setStore((prev) => {
      const drafts = prev.drafts.filter((x) => x.id !== id);
      const activeId = prev.activeId === id ? drafts[0].id : prev.activeId;
      const nextPanels = prev.panelIds.filter((x) => x !== id);
      return {
        drafts,
        activeId,
        panelIds: nextPanels.length ? nextPanels : [activeId],
      };
    });
  }

  async function clearLog(id: string) {
    patchSession(id, {
      log: [],
      status: "",
      dialogId: null,
      summaryText: null,
      facts: null,
      branchDraftId: null,
    });
    if (!isTeam) {
      try {
        await clearAgentDialogByDraft(id);
      } catch {
        /* no server dialog yet */
      }
    }
  }

  async function hydrateDialog(agentId: string) {
    if (isTeam) return;
    try {
      const dialog = await getAgentDialogByDraft(agentId);
      if (!dialog) return;
      patchSession(agentId, {
        dialogId: dialog.id,
        log: dialogMessagesToLog(dialog.messages),
        status: "",
        summaryText: dialog.summary_text || null,
        facts: dialog.facts && Object.keys(dialog.facts).length ? dialog.facts : null,
      });
    } catch {
      /* offline / empty */
    }
  }

  async function forkBranch(agentId: string, messageId: string, label: string) {
    const sess = ensureSession(sessionsRef.current, agentId);
    const dialogId = sess.dialogId;
    if (!dialogId) {
      patchSession(agentId, { status: "Сначала отправьте сообщение — нужен dialog." });
      return;
    }
    const draftId = `${agentId}__${label.toLowerCase().replace(/\s+/g, "-").slice(0, 24)}-${Date.now().toString(36)}`;
    try {
      const child = await forkAgentDialog(dialogId, {
        from_message_id: messageId,
        client_draft_id: draftId.slice(0, 64),
        label,
      });
      const branches = [
        ...(sess.branches || []),
        {
          draftId: child.client_draft_id,
          dialogId: child.id,
          label: child.branch_label || label,
          parentDialogId: child.parent_dialog_id,
        },
      ];
      patchSession(agentId, {
        status: `Ветка «${label}» создана — переключитесь ниже.`,
        branches,
      });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Не удалось создать ветку.";
      patchSession(agentId, { status: msg });
    }
  }

  async function switchBranch(agentId: string, draftId: string, dialogId: string) {
    try {
      const dialog = await getAgentDialogByDraft(draftId);
      if (!dialog) {
        patchSession(agentId, { status: "Ветка не найдена." });
        return;
      }
      patchSession(agentId, {
        dialogId: dialogId || dialog.id,
        log: dialogMessagesToLog(dialog.messages),
        summaryText: dialog.summary_text || null,
        facts: dialog.facts && Object.keys(dialog.facts).length ? dialog.facts : null,
        status: `Активна ветка · ${dialog.branch_label || draftId}`,
        branchDraftId: draftId,
      });
    } catch {
      patchSession(agentId, { status: "Не удалось переключить ветку." });
    }
  }

  /**
   * Core run. Team runs use mirror:"brief" so full text lives in the team log only.
   */
  async function runOne(
    agentId: string,
    message: string,
    opts?: {
      tag?: string;
      signal?: AbortSignal;
      clearInput?: boolean;
      mirror?: "full" | "brief" | "none";
      /** Solo: save turns in Postgres and continue with history */
      persist?: boolean;
    },
  ): Promise<{ content: string; model_id: string } | null> {
    const draft = draftById(storeRef.current, agentId);
    if (!draft) return null;
    if (!draft.system_prompt.trim()) {
      patchSession(agentId, { status: "Заполните инструкцию агента." });
      return null;
    }

    const tag = opts?.tag;
    const mirror = opts?.mirror ?? "full";

    if (mirror === "full") {
      appendLog(agentId, {
        id: `u-${Date.now()}-${agentId}`,
        role: "user",
        text: message,
        tag,
      });
    } else if (mirror === "brief") {
      appendLog(agentId, {
        id: `s-${Date.now()}-${agentId}`,
        role: "status",
        text: "Участвует в команде — ответ в ленте сверху.",
        tag,
      });
    }

    patchSession(agentId, {
      status: "Ждём ответ…",
      ...(opts?.clearInput ? { input: "" } : {}),
    });
    setBusyIds((prev) => ({ ...prev, [agentId]: true }));

    const controller = new AbortController();
    const external = opts?.signal;
    const onAbort = () => controller.abort();
    if (external) {
      if (external.aborted) controller.abort();
      else external.addEventListener("abort", onAbort, { once: true });
    }
    abortMap.current.get(agentId)?.abort();
    abortMap.current.set(agentId, controller);

    try {
      const persist = Boolean(opts?.persist);
      const sess = ensureSession(sessionsRef.current, agentId);
      const dialogId = sess.dialogId ?? null;
      const contextLimit = sess.contextLimit ?? null;
      const contextMode = sess.contextMode ?? "none";
      const clientDraftId = persist
        ? sess.branchDraftId || agentId
        : undefined;
      const result = await runAgentWorkshop(
        {
          name: draft.name,
          system_prompt: draft.system_prompt,
          preferred_model: draft.preferred_model || "auto",
          temperature: draft.temperature,
          max_tokens: draft.max_tokens,
        },
        message,
        {
          signal: controller.signal,
          persist,
          clientDraftId,
          dialogId: persist ? dialogId : undefined,
          contextLimit,
          contextMode: persist ? contextMode : "none",
          recentKeep: sess.recentKeep ?? 8,
          summarizeEvery: sess.summarizeEvery ?? 10,
        },
      );
      const tokenMeter = result.tokens ?? null;
      const compressionMeter = result.compression ?? null;
      const strategyMeter = result.context_strategy ?? null;
      if (mirror === "full") {
        if (persist && result.messages?.length) {
          const log = dialogMessagesToLog(result.messages);
          for (let i = log.length - 1; i >= 0; i--) {
            if (log[i].role === "assistant") {
              log[i] = {
                ...log[i],
                tokens: tokenMeter,
                compression: compressionMeter,
                contextStrategy: strategyMeter,
              };
              break;
            }
          }
          patchSession(agentId, {
            status: "",
            dialogId: result.dialog_id ?? dialogId,
            log,
            summaryText:
              strategyMeter?.summary_text ||
              compressionMeter?.summary_text ||
              sess.summaryText ||
              null,
            facts:
              strategyMeter?.facts && Object.keys(strategyMeter.facts).length
                ? strategyMeter.facts
                : sess.facts || null,
          });
        } else {
          appendLog(agentId, {
            id: `a-${Date.now()}-${agentId}`,
            role: "assistant",
            text: result.content,
            modelId: result.model_id,
            tag,
            speaker: draft.name,
            tokens: tokenMeter,
            compression: compressionMeter,
            contextStrategy: strategyMeter,
          });
          patchSession(agentId, {
            status: "",
            summaryText:
              strategyMeter?.summary_text ||
              compressionMeter?.summary_text ||
              sess.summaryText ||
              null,
          });
        }
      } else if (mirror === "brief") {
        appendLog(agentId, {
          id: `a-${Date.now()}-${agentId}`,
          role: "status",
          text: `Готово · ${result.model_id}`,
          modelId: result.model_id,
          tag,
        });
        patchSession(agentId, { status: "" });
      } else {
        patchSession(agentId, { status: "" });
      }
      return result;
    } catch (e) {
      if (controller.signal.aborted) {
        if (mirror !== "none") {
          appendLog(agentId, {
            id: `s-${Date.now()}`,
            role: "status",
            text: "Запрос отменён.",
            tag,
          });
        }
        patchSession(agentId, { status: "" });
      } else {
        const msg =
          e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
        if (mirror !== "none") {
          appendLog(agentId, {
            id: `e-${Date.now()}`,
            role: "error",
            text: msg,
            tag,
          });
        }
        patchSession(agentId, { status: "Не удалось получить ответ." });
      }
      return null;
    } finally {
      if (external) external.removeEventListener("abort", onAbort);
      setBusyIds((prev) => {
        const next = { ...prev };
        delete next[agentId];
        return next;
      });
      abortMap.current.delete(agentId);
    }
  }

  async function send(agentId: string) {
    const session = ensureSession(sessions, agentId);
    const message = session.input.trim();
    if (!message || busyIds[agentId]) return;
    await runOne(agentId, message, {
      clearInput: true,
      mirror: "full",
      persist: !isTeam,
    });
  }

  function stop(agentId: string) {
    abortMap.current.get(agentId)?.abort();
  }

  function stopTeam() {
    teamAbort.current?.abort();
  }

  async function runFanIn(
    task: string,
    parts: ProgonPart[],
    tag: string,
    signal: AbortSignal,
  ): Promise<void> {
    if (parts.length < 1) {
      pushTeam({ kind: "status", text: "Склейка пропущена — нет ответов", tag });
      return;
    }
    pushTeam({ kind: "status", text: "Fan-in · Склейщик", tag: `${tag} · Σ` });
    const message = buildTeamFanInMessage({ task, parts });
    try {
      const result = await runAgentWorkshop(
        {
          name: AGGREGATOR_DEFINITION.name,
          system_prompt: AGGREGATOR_DEFINITION.system_prompt,
          preferred_model: AGGREGATOR_DEFINITION.preferred_model,
          temperature: AGGREGATOR_DEFINITION.temperature ?? null,
          max_tokens: AGGREGATOR_DEFINITION.max_tokens ?? null,
        },
        message,
        signal,
      );
      pushTeam({
        kind: "reply",
        agentName: "Склейщик",
        text: result.content,
        modelId: result.model_id,
        tag: `${tag} · Σ`,
      });
    } catch (e) {
      if (signal.aborted) return;
      const fallback = markdownJoinParts({ task, parts });
      const err =
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      pushTeam({
        kind: "status",
        text: `Склейщик недоступен (${err}). Показан markdown join.`,
        tag: `${tag} · Σ`,
      });
      pushTeam({
        kind: "reply",
        agentName: "Склейка (fallback)",
        text: fallback,
        tag: `${tag} · Σ`,
      });
    }
  }

  async function runTeam() {
    const parsed = stripProgonTrigger(teamTask);
    let mode: TeamMode = teamMode;
    if (parsed.triggered) mode = "progon";
    const task = parsed.task;
    const ids = mode === "progon" ? teamOrderedIds.slice(0, 1) : teamOrderedIds;

    if (!task) {
      window.alert("Введите задачу для команды");
      return;
    }
    if (parsed.triggered && teamMode !== "progon") setTeamMode("progon");
    if (mode === "progon" && ids.length < 1) {
      window.alert("Выберите базового агента в составе");
      return;
    }
    if (mode !== "progon" && teamBlockReason) {
      window.alert(teamBlockReason);
      return;
    }
    if (mode === "progon" && progonAxis === "model" && progonModelIds.length < 2) {
      window.alert("Для прогона по моделям отметьте минимум 2 модели");
      return;
    }

    const runId = uid();
    const tag = `${TEAM_MODE_LABEL[mode]} · ${runId}`;
    const controller = new AbortController();
    teamAbort.current?.abort();
    teamAbort.current = controller;
    setTeamBusy(true);
    pushTeam({
      kind: "task",
      text: parsed.triggered ? `/прогон ${task}` : task,
      tag,
    });

    if (ids.length >= 1) {
      setStore((prev) => ({
        ...prev,
        activeId: ids[0],
        panelIds: [ids[0]],
      }));
    }

    const teamOpts = {
      tag,
      signal: controller.signal,
      clearInput: false as const,
      mirror: "brief" as const,
    };

    const doFanIn =
      fanIn && (mode === "parallel" || mode === "roundtable" || mode === "progon");

    try {
      if (mode === "progon") {
        const base = draftById(storeRef.current, ids[0])!;
        const variants = buildProgonVariants(
          {
            name: base.name,
            system_prompt: base.system_prompt,
            preferred_model: base.preferred_model,
            temperature: base.temperature,
            max_tokens: base.max_tokens,
          },
          {
            axis: progonAxis,
            temperatures: [...PROGON_DEFAULT_TEMPERATURES],
            modelIds: progonModelIds,
          },
        );
        pushTeam({
          kind: "status",
          text: `Fan-out · ${variants.length} вариантов (${progonAxis})`,
          tag,
        });
        const parts: ProgonPart[] = [];
        await Promise.all(
          variants.map(async (v) => {
            try {
              const result = await runAgentWorkshop(
                {
                  name: v.name,
                  system_prompt: v.system_prompt,
                  preferred_model: v.preferred_model,
                  temperature: v.temperature ?? null,
                  max_tokens: v.max_tokens ?? null,
                },
                task,
                controller.signal,
              );
              parts.push({
                label: v.label,
                modelId: result.model_id,
                content: result.content,
                temperature: v.temperature,
              });
              pushTeam({
                kind: "reply",
                agentName: v.name,
                text: result.content,
                modelId: result.model_id,
                tag: `${tag} · ${v.label}`,
              });
            } catch (e) {
              if (controller.signal.aborted) return;
              const msg =
                e instanceof ApiError
                  ? e.message
                  : e instanceof Error
                    ? e.message
                    : String(e);
              pushTeam({
                kind: "error",
                agentName: v.name,
                text: msg,
                tag: `${tag} · ${v.label}`,
              });
            }
          }),
        );
        if (doFanIn && !controller.signal.aborted) {
          await runFanIn(task, parts, tag, controller.signal);
        }
      } else if (mode === "parallel") {
        pushTeam({ kind: "status", text: `Fan-out · ${ids.length} агентов`, tag });
        const parts: ProgonPart[] = [];
        await Promise.all(
          ids.map(async (id) => {
            const d = draftById(storeRef.current, id)!;
            const result = await runOne(id, task, teamOpts);
            if (result) {
              parts.push({
                label: d.name,
                modelId: result.model_id,
                content: result.content,
                temperature: d.temperature,
              });
              pushTeam({
                kind: "reply",
                agentName: d.name,
                text: result.content,
                modelId: result.model_id,
                tag,
              });
            } else if (!controller.signal.aborted) {
              pushTeam({ kind: "error", agentName: d.name, text: "Нет ответа", tag });
            }
          }),
        );
        if (doFanIn && !controller.signal.aborted && parts.length > 1) {
          await runFanIn(task, parts, tag, controller.signal);
        }
      } else if (mode === "chain") {
        let previous: { name: string; content: string } | null = null;
        for (let i = 0; i < ids.length; i++) {
          if (controller.signal.aborted) break;
          const id = ids[i];
          const d = draftById(storeRef.current, id)!;
          const message =
            previous == null
              ? task
              : buildChainHandoff({
                  task,
                  fromName: previous.name,
                  fromContent: previous.content,
                  step: i + 1,
                  total: ids.length,
                });
          pushTeam({
            kind: "status",
            agentName: d.name,
            text: previous
              ? `Handoff ${i + 1}: «${previous.name}» → «${d.name}»`
              : `Старт → «${d.name}»`,
            tag,
          });
          const result = await runOne(id, message, teamOpts);
          if (!result) {
            pushTeam({ kind: "error", agentName: d.name, text: "Цепочка прервана", tag });
            break;
          }
          pushTeam({
            kind: "reply",
            agentName: d.name,
            text: result.content,
            modelId: result.model_id,
            tag,
          });
          previous = { name: d.name, content: result.content };
        }
      } else {
        const round1: { id: string; name: string; content: string; modelId: string }[] = [];
        pushTeam({ kind: "status", text: "Раунд 1 · fan-out", tag });
        await Promise.all(
          ids.map(async (id) => {
            const d = draftById(storeRef.current, id)!;
            const result = await runOne(id, task, {
              ...teamOpts,
              tag: `${tag} · R1`,
            });
            if (result) {
              round1.push({
                id,
                name: d.name,
                content: result.content,
                modelId: result.model_id,
              });
              pushTeam({
                kind: "reply",
                agentName: d.name,
                text: result.content,
                modelId: result.model_id,
                tag: `${tag} · R1`,
              });
            }
          }),
        );
        const peerParts: ProgonPart[] = [];
        if (controller.signal.aborted || round1.length < 2) {
          pushTeam({ kind: "status", text: "Раунд 2 пропущен", tag });
          for (const r of round1) {
            peerParts.push({ label: r.name, modelId: r.modelId, content: r.content });
          }
        } else {
          pushTeam({ kind: "status", text: "Раунд 2 · peer review", tag });
          await Promise.all(
            round1.map(async (self) => {
              const message = buildRoundtableFollowup({
                task,
                selfName: self.name,
                peers: round1.map((p) => ({ name: p.name, content: p.content })),
              });
              const result = await runOne(self.id, message, {
                ...teamOpts,
                tag: `${tag} · R2`,
              });
              if (result) {
                peerParts.push({
                  label: `${self.name} (R2)`,
                  modelId: result.model_id,
                  content: result.content,
                });
                pushTeam({
                  kind: "reply",
                  agentName: self.name,
                  text: result.content,
                  modelId: result.model_id,
                  tag: `${tag} · R2`,
                });
              }
            }),
          );
        }
        if (doFanIn && !controller.signal.aborted && peerParts.length > 1) {
          await runFanIn(task, peerParts, tag, controller.signal);
        }
      }
      if (controller.signal.aborted) {
        pushTeam({ kind: "status", text: "Команда остановлена", tag });
      }
    } finally {
      setTeamBusy(false);
      teamAbort.current = null;
    }
  }

  const builder = (draft: AgentDraft) => (
    <div className="agent-builder">
      <header className="agent-builder-head">
        <h3>Настройка</h3>
        <p className="agent-hint">Имя и инструкция сохраняются в этом браузере.</p>
      </header>
      <label className="agent-field">
        <span>Имя</span>
        <input
          value={draft.name}
          onChange={(e) => patchDraft(draft.id, { name: e.target.value })}
          maxLength={120}
        />
      </label>
      <label className="agent-field agent-field--grow">
        <span>Инструкция агента</span>
        <textarea
          value={draft.system_prompt}
          onChange={(e) => patchDraft(draft.id, { system_prompt: e.target.value })}
          rows={split ? 5 : 10}
          spellCheck
        />
      </label>
      <fieldset className="agent-how">
        <legend>Как отвечает</legend>
        <label className="agent-field">
          <span>Модель</span>
          <select
            value={draft.preferred_model}
            onChange={(e) => patchDraft(draft.id, { preferred_model: e.target.value })}
          >
            {modelOptions.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label || m.id}
              </option>
            ))}
          </select>
        </label>
        <div className="agent-how-row">
          <label className="agent-field">
            <span>Temp</span>
            <input
              type="number"
              min={0}
              max={2}
              step={0.1}
              value={draft.temperature ?? 0.7}
              onChange={(e) => patchDraft(draft.id, { temperature: Number(e.target.value) })}
            />
          </label>
          <label className="agent-field">
            <span>Max tokens</span>
            <input
              type="number"
              min={1}
              max={8192}
              step={1}
              value={draft.max_tokens ?? 512}
              onChange={(e) => patchDraft(draft.id, { max_tokens: Number(e.target.value) })}
            />
          </label>
        </div>
      </fieldset>
      <div className="agent-builder-actions">
        <button type="button" className="ghost-button" onClick={() => onDuplicate(draft.id)}>
          Дублировать
        </button>
        <button type="button" className="ghost-button" onClick={() => clearLog(draft.id)}>
          Очистить лог
        </button>
        <span className="agent-save" aria-live="polite">
          {savedFlash ? "Сохранено" : "Автосохранение"}
        </span>
      </div>
    </div>
  );

  function dialogBody(draft: AgentDraft, session: AgentSession, busy: boolean) {
    if (isTeam) {
      return (
        <div className="agent-log agent-log--team-hint" aria-live="polite">
          <div className="agent-log-empty">
            <p>
              Режим <strong>Команда</strong>: задание и ответы — в ленте сверху.
            </p>
            <p className="agent-hint">
              Здесь только статус участия. Чтобы поговорить лично — переключитесь на «Один агент».
            </p>
            {session.log.length > 0 ? (
              <div className="agent-team-brief-log">
                {session.log.slice(-6).map((line) => (
                  <p key={line.id} className={`agent-brief-line agent-brief-line--${line.role}`}>
                    {line.text}
                  </p>
                ))}
              </div>
            ) : null}
          </div>
          {session.status ? (
            <p className="agent-status" role="status">
              {session.status}
            </p>
          ) : null}
        </div>
      );
    }

    return (
      <>
        <div className="agent-log" aria-live="polite">
          {session.log.length === 0 ? (
            <div className="agent-log-empty">
              <p>
                <strong>С чего начать</strong>
              </p>
              <ol className="agent-first-steps">
                <li>При необходимости поправьте инструкцию слева</li>
                <li>Напишите фразу ниже — ответ сохранится в Postgres</li>
                <li>Обновите страницу и продолжите: агент помнит контекст</li>
              </ol>
              <p className="agent-hint">
                Диалог сохраняется в Postgres и восстанавливается после перезапуска (тот же браузер /
                visitor).
              </p>
            </div>
          ) : (
            session.log.map((line) => (
              <article key={line.id} className={`agent-log-line agent-log-line--${line.role}`}>
                <div className="agent-log-meta">
                  {line.tag ? <span className="agent-tag">{line.tag}</span> : null}
                  {line.role === "assistant" && line.modelId ? (
                    <span className="badge">{line.modelId}</span>
                  ) : null}
                  {line.messageId && session.dialogId ? (
                    <button
                      type="button"
                      className="ghost-button agent-fork-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        const n = (session.branches?.length || 0) + 1;
                        const label = String.fromCharCode(64 + Math.min(n, 26));
                        void forkBranch(draft.id, line.messageId!, label);
                      }}
                    >
                      Checkpoint → ветка
                    </button>
                  ) : null}
                </div>
                <p>{line.text}</p>
                {line.role === "assistant" && line.tokens ? (
                  <div className="agent-token-meter" aria-label="Токены">
                    {line.tokens.truncation.applied ? (
                      <p className="agent-token-trunc" role="status">
                        История обрезана: −{line.tokens.truncation.dropped_messages} сообщ. (~
                        {line.tokens.truncation.dropped_tokens_est} tok), budget{" "}
                        {line.tokens.truncation.budget}/{line.tokens.truncation.context_limit}
                      </p>
                    ) : null}
                    {line.contextStrategy && line.contextStrategy.mode !== "none" ? (
                      <p className="agent-token-compress" role="status">
                        {CONTEXT_MODE_LABELS[line.contextStrategy.mode as ContextMode] ||
                          line.contextStrategy.mode}
                        : {line.contextStrategy.tokens_raw_est} →{" "}
                        {line.contextStrategy.tokens_strategy_est} tok
                        {line.contextStrategy.dropped
                          ? ` · −${line.contextStrategy.dropped}`
                          : ""}
                        {line.contextStrategy.summary_refreshed ? " · сводка" : ""}
                        {line.contextStrategy.facts_updated ? " · facts↑" : ""}
                      </p>
                    ) : line.compression?.enabled ? (
                      <p className="agent-token-compress" role="status">
                        Сжатие: {line.compression.tokens_raw_est} →{" "}
                        {line.compression.tokens_compressed_est} tok
                      </p>
                    ) : null}
                    <dl className="agent-token-grid">
                      <div>
                        <dt>Запрос</dt>
                        <dd>{line.tokens.request}</dd>
                      </div>
                      <div>
                        <dt>История</dt>
                        <dd>
                          {line.tokens.history_after}
                          {line.tokens.history_before !== line.tokens.history_after
                            ? ` ← ${line.tokens.history_before}`
                            : ""}
                        </dd>
                      </div>
                      <div>
                        <dt>Ответ</dt>
                        <dd>{line.tokens.completion}</dd>
                      </div>
                      <div>
                        <dt>Всего</dt>
                        <dd>{line.tokens.total}</dd>
                      </div>
                      <div>
                        <dt>cost≈</dt>
                        <dd>{line.tokens.cost_proxy}</dd>
                      </div>
                    </dl>
                  </div>
                ) : null}
              </article>
            ))
          )}
        </div>
        {session.summaryText ? (
          <details className="agent-summary-panel">
            <summary>Сводка истории</summary>
            <p>{session.summaryText}</p>
          </details>
        ) : null}
        {session.facts && Object.keys(session.facts).length ? (
          <details className="agent-summary-panel agent-facts-panel" open>
            <summary>Facts</summary>
            <ul className="agent-facts-list">
              {Object.entries(session.facts).map(([k, v]) => (
                <li key={k}>
                  <strong>{k}</strong>: {v}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
        {session.branches && session.branches.length > 0 ? (
          <div className="agent-branches" role="navigation" aria-label="Ветки диалога">
            <span className="agent-branches-label">Ветки</span>
            {session.branches.map((b) => (
              <button
                key={b.draftId}
                type="button"
                className={
                  session.branchDraftId === b.draftId
                    ? "ghost-button agent-branch-btn is-active"
                    : "ghost-button agent-branch-btn"
                }
                onClick={() => void switchBranch(draft.id, b.draftId, b.dialogId)}
              >
                {b.label}
              </button>
            ))}
            <button
              type="button"
              className="ghost-button agent-branch-btn"
              onClick={() =>
                patchSession(draft.id, {
                  branchDraftId: null,
                  status: "Вернулись к основной ветке (draft агента).",
                })
              }
            >
              Основная
            </button>
          </div>
        ) : null}
        {session.status ? (
          <p className="agent-status" role="status">
            {session.status}
          </p>
        ) : null}
        <form
          className="agent-compose"
          onSubmit={(e) => {
            e.preventDefault();
            void send(draft.id);
          }}
        >
          <div className="agent-compose-tools">
            <label className="agent-context-mode">
              <span>Контекст</span>
              <select
                value={session.contextMode ?? "none"}
                onChange={(e) =>
                  patchSession(draft.id, {
                    contextMode: e.target.value as ContextMode,
                  })
                }
                onClick={(e) => e.stopPropagation()}
              >
                {(Object.keys(CONTEXT_MODE_LABELS) as ContextMode[]).map((m) => (
                  <option key={m} value={m}>
                    {CONTEXT_MODE_LABELS[m]}
                  </option>
                ))}
              </select>
            </label>
            {(session.contextMode ?? "none") !== "none" ? (
              <label className="agent-context-limit" title="Последние N реплик">
                <span>recent</span>
                <input
                  type="number"
                  min={2}
                  max={40}
                  step={1}
                  value={session.recentKeep ?? 8}
                  onChange={(e) => {
                    const n = Number(e.target.value);
                    if (!Number.isFinite(n) || n < 0) return;
                    patchSession(draft.id, { recentKeep: Math.floor(n) });
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
              </label>
            ) : null}
            {(session.contextMode ?? "none") === "compress" ? (
              <label className="agent-context-limit" title="Порог обновления сводки">
                <span>every</span>
                <input
                  type="number"
                  min={2}
                  max={100}
                  step={1}
                  value={session.summarizeEvery ?? 10}
                  onChange={(e) => {
                    const n = Number(e.target.value);
                    if (!Number.isFinite(n) || n < 2) return;
                    patchSession(draft.id, { summarizeEvery: Math.floor(n) });
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
              </label>
            ) : null}
            <label className="agent-context-limit">
              <span>Лимит контекста</span>
              <input
                type="number"
                min={64}
                max={128000}
                step={1}
                placeholder="8192"
                value={session.contextLimit ?? ""}
                onChange={(e) => {
                  const raw = e.target.value.trim();
                  if (raw === "") {
                    patchSession(draft.id, { contextLimit: null });
                    return;
                  }
                  const n = Number(raw);
                  if (!Number.isFinite(n) || n < 0) return;
                  patchSession(draft.id, { contextLimit: Math.floor(n) });
                }}
                onClick={(e) => e.stopPropagation()}
                title="Примерно токены (len/4). Низкое значение — демо обрезки истории."
              />
            </label>
          </div>
          <textarea
            value={session.input}
            onChange={(e) => patchSession(draft.id, { input: e.target.value })}
            rows={2}
            placeholder={`Сообщение → ${draft.name}`}
            onClick={(e) => e.stopPropagation()}
          />
          {busy ? (
            <button
              type="button"
              className="agent-send-btn"
              onClick={(e) => {
                e.stopPropagation();
                stop(draft.id);
              }}
            >
              Стоп
            </button>
          ) : (
            <button
              type="submit"
              className="agent-send-btn"
              disabled={!session.input.trim()}
              onClick={(e) => e.stopPropagation()}
            >
              Отправить
            </button>
          )}
        </form>
      </>
    );
  }

  const panel = (agentId: string) => {
    const draft = draftById(store, agentId);
    if (!draft) return null;
    const session = ensureSession(sessions, agentId);
    const busy = Boolean(busyIds[agentId]);
    const focused = store.activeId === agentId;

    return (
      <article
        key={agentId}
        className={`agent-panel${focused ? " agent-panel--focus" : ""}`}
        onClick={() => {
          if (!focused) setStore((prev) => ({ ...prev, activeId: agentId }));
        }}
      >
        <header className="agent-panel-head">
          <div className="agent-panel-title">
            <strong>{draft.name}</strong>
            {busy ? <span className="agent-busy-dot" title="Идёт запрос" /> : null}
          </div>
          <div className="agent-panel-tools">
            {!isTeam && !split ? (
              <button
                type="button"
                className="ghost-button"
                disabled={store.drafts.length < 2}
                onClick={(e) => {
                  e.stopPropagation();
                  const other = store.drafts.find((d) => d.id !== agentId);
                  if (other) openSplitWith(other.id);
                }}
              >
                + Рядом
              </button>
            ) : null}
            {!isTeam && split ? (
              <button
                type="button"
                className="ghost-button"
                onClick={(e) => {
                  e.stopPropagation();
                  if (panelIds[0] !== agentId) {
                    setStore((prev) => ({
                      ...prev,
                      activeId: agentId,
                      panelIds: [agentId],
                    }));
                  } else {
                    closeSplit();
                  }
                }}
              >
                Закрыть панель
              </button>
            ) : null}
            <button
              type="button"
              className="ghost-button agent-mobile-settings"
              onClick={(e) => {
                e.stopPropagation();
                setStore((prev) => ({ ...prev, activeId: agentId }));
                setMobileSheet(true);
              }}
            >
              Настройки
            </button>
          </div>
        </header>

        {!split ? (
          <div className="agent-panel-split">
            <aside className="agent-workshop-builder desktop-only">{builder(draft)}</aside>
            <div className="agent-workshop-dialog">{dialogBody(draft, session, busy)}</div>
          </div>
        ) : (
          <div className="agent-panel-compact">
            <details className="agent-panel-settings">
              <summary>Инструкция и модель</summary>
              {builder(draft)}
            </details>
            <div className="agent-workshop-dialog">{dialogBody(draft, session, busy)}</div>
          </div>
        )}
      </article>
    );
  };

  return (
    <section
      className={`agent-workshop${split ? " agent-workshop--split" : ""}${
        isTeam ? " agent-workshop--team" : " agent-workshop--solo"
      }`}
      aria-labelledby={titleId}
    >
      <header className="agent-workshop-top">
        <div className="agent-workshop-title-row">
          <div>
            <h2 id={titleId}>Агенты</h2>
            <p className="agent-workshop-lead">
              {isTeam
                ? "Команда: fan-out, handoff, прогон. Ответы и склейка — в ленте."
                : "Соберите агента и ведите диалог — история в Postgres, помнит после перезапуска."}
            </p>
          </div>
          <div className="agent-workspace-modes" role="group" aria-label="Режим работы">
            <button
              type="button"
              className="shell-mode-btn"
              aria-pressed={!isTeam}
              onClick={() => setMode("solo")}
            >
              Один агент
            </button>
            <button
              type="button"
              className="shell-mode-btn"
              aria-pressed={isTeam}
              onClick={() => setMode("team")}
            >
              Команда
            </button>
          </div>
        </div>
        <div className="agent-presets" role="group" aria-label="Пресеты">
          {AGENT_PRESETS.map((p, i) => (
            <button key={p.name} type="button" className="chip" onClick={() => createFromPreset(i)}>
              + {p.name}
            </button>
          ))}
          <button type="button" className="chip" onClick={() => newDraft()}>
            + Пустой
          </button>
        </div>
      </header>

      {isTeam ? (
        <section className="agent-team" aria-label="Задача команде">
          <div className="agent-team-modes" role="group" aria-label="Как работают вместе">
            {(Object.keys(TEAM_MODE_LABEL) as TeamMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                className="shell-mode-btn"
                aria-pressed={teamMode === mode}
                onClick={() => setTeamMode(mode)}
                title={TEAM_MODE_HINT[mode]}
              >
                <span className="agent-mode-scheme">{TEAM_MODE_SCHEME[mode]}</span>
                {TEAM_MODE_LABEL[mode]}
              </button>
            ))}
          </div>
          <p className="agent-hint">{TEAM_MODE_HINT[teamMode]}</p>

          <div className="agent-team-roster" aria-label="Состав команды">
            <span className="agent-team-roster-label">{teamMode === "progon" ? "Базовый агент" : "Состав"}</span>
            {teamOrderedIds.length === 0 ? (
              <span className="agent-hint">{teamMode === "progon" ? "Выберите одного базового агента слева" : "Пока пусто — отметьте агентов слева или добавьте пресет"}</span>
            ) : (
              teamOrderedIds.map((id) => {
                const d = draftById(store, id);
                if (!d) return null;
                const n = teamOrderIndex.get(id);
                return (
                  <span key={id} className="agent-team-chip">
                    {teamMode === "chain" && n ? (
                      <span className="agent-team-chip-num">{n}</span>
                    ) : null}
                    <button
                      type="button"
                      className="agent-team-chip-name"
                      onClick={() => focusAgent(id)}
                    >
                      {d.name}
                    </button>
                    {teamMode === "chain" ? (
                      <span className="agent-team-chip-move">
                        <button
                          type="button"
                          className="ghost-button"
                          aria-label="Выше в цепочке"
                          disabled={n === 1}
                          onClick={() => moveTeamMember(id, -1)}
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          className="ghost-button"
                          aria-label="Ниже в цепочке"
                          disabled={n === teamOrderedIds.length}
                          onClick={() => moveTeamMember(id, 1)}
                        >
                          ↓
                        </button>
                      </span>
                    ) : null}
                    <button
                      type="button"
                      className="ghost-button"
                      aria-label={`Убрать ${d.name}`}
                      onClick={() => toggleSelect(id)}
                    >
                      ×
                    </button>
                  </span>
                );
              })
            )}
            {filteredDrafts.some((d) => !selectedIds.includes(d.id)) ? (
              <select
                className="agent-team-add"
                value=""
                aria-label="Добавить в состав"
                onChange={(e) => {
                  const id = e.target.value;
                  if (id) toggleSelect(id);
                }}
              >
                <option value="">+ Добавить…</option>
                {filteredDrafts
                  .filter((d) => !selectedIds.includes(d.id))
                  .map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
              </select>
            ) : null}
          </div>

          {teamMode === "progon" ? (
            <div className="agent-progon-controls">
              <div className="agent-team-modes" role="group" aria-label="Ось прогона">
                <button
                  type="button"
                  className="shell-mode-btn"
                  aria-pressed={progonAxis === "temperature"}
                  onClick={() => setProgonAxis("temperature")}
                >
                  По temperature
                </button>
                <button
                  type="button"
                  className="shell-mode-btn"
                  aria-pressed={progonAxis === "model"}
                  onClick={() => setProgonAxis("model")}
                >
                  По моделям
                </button>
              </div>
              {progonAxis === "temperature" ? (
                <p className="agent-hint">Матрица: {PROGON_DEFAULT_TEMPERATURES.join(" · ")}</p>
              ) : (
                <div className="agent-progon-models" role="group" aria-label="Модели прогона">
                  {modelOptions
                    .filter((m) => m.id !== "auto")
                    .slice(0, 8)
                    .map((m) => {
                      const on = progonModelIds.includes(m.id);
                      return (
                        <label key={m.id} className={`agent-progon-model${on ? " is-on" : ""}`}>
                          <input
                            type="checkbox"
                            checked={on}
                            onChange={() => {
                              setProgonModelIds((prev) => {
                                if (prev.includes(m.id)) return prev.filter((x) => x !== m.id);
                                if (prev.length >= 4) return prev;
                                return [...prev, m.id];
                              });
                            }}
                          />
                          {m.label || m.id}
                        </label>
                      );
                    })}
                </div>
              )}
            </div>
          ) : null}

          {teamMode === "parallel" || teamMode === "roundtable" || teamMode === "progon" ? (
            <label className="agent-fanin-toggle">
              <input
                type="checkbox"
                checked={fanIn}
                onChange={(e) => setFanIn(e.target.checked)}
              />
              Fan-in: склеить через «Склейщик» (supervisor)
            </label>
          ) : null}

          <p className="agent-team-budget" role="status">
            Запросов ≈ <strong>{requestBudget}</strong>
            {teamMode === "progon" && progonVariantsPreview.length
              ? ` · ${progonVariantsPreview.map((v) => v.label).join(", ")}`
              : ""}
          </p>

          <form
            className="agent-team-form"
            onSubmit={(e) => {
              e.preventDefault();
              void runTeam();
            }}
          >
            <textarea
              value={teamTask}
              onChange={(e) => setTeamTask(e.target.value)}
              rows={2}
              placeholder={teamMode === "progon" ? "/прогон объясни temperature…" : "Задача для команды…"}
              disabled={teamBusy}
            />
            {teamBusy ? (
              <button type="button" className="agent-send-btn" onClick={stopTeam}>
                Стоп
              </button>
            ) : (
              <button type="submit" className="agent-send-btn" disabled={Boolean(teamBlockReason)}>
                Запустить
              </button>
            )}
          </form>
          {teamBlockReason && !teamBusy ? (
            <p className="agent-team-block" role="status">
              {teamBlockReason}
            </p>
          ) : null}

          {teamLog.length > 0 ? (
            <div className="agent-team-log" aria-live="polite">
              <div className="agent-team-log-head">
                <strong>Лента команды</strong>
                <button type="button" className="ghost-button" onClick={() => setTeamLog([])}>
                  Очистить
                </button>
              </div>
              {teamLog.map((ev) => (
                <article key={ev.id} className={`agent-team-event agent-team-event--${ev.kind}`}>
                  <div className="agent-log-meta">
                    {ev.tag ? <span className="agent-tag">{ev.tag}</span> : null}
                    {ev.agentName ? <strong>{ev.agentName}</strong> : null}
                    {ev.modelId ? <span className="badge">{ev.modelId}</span> : null}
                  </div>
                  <p>{ev.text}</p>
                </article>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}

      <div className="agent-workshop-layout">
        <aside className="agent-rail" aria-label="Список агентов">
          <div className="agent-rail-head">
            <input
              className="agent-rail-search"
              value={libraryQuery}
              onChange={(e) => setLibraryQuery(e.target.value)}
              placeholder="Найти…"
              aria-label="Поиск агентов"
            />
            <button type="button" className="ghost-button" onClick={() => newDraft()} title="Новый">
              +
            </button>
          </div>
          <ul className="agent-rail-list">
            {filteredDrafts.map((d) => {
              const busy = Boolean(busyIds[d.id]);
              const inPanel = panelIds.includes(d.id);
              const checked = selectedIds.includes(d.id);
              const order = teamOrderIndex.get(d.id);
              return (
                <li key={d.id}>
                  {isTeam ? (
                    <label className="agent-rail-check">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleSelect(d.id)}
                        aria-label={`В команду: ${d.name}`}
                      />
                      {teamMode === "chain" && order ? (
                        <span className="agent-rail-order">{order}</span>
                      ) : null}
                    </label>
                  ) : null}
                  <button
                    type="button"
                    className={`agent-rail-item${store.activeId === d.id ? " is-active" : ""}${
                      inPanel ? " is-open" : ""
                    }`}
                    onClick={() => focusAgent(d.id)}
                  >
                    <span className="agent-rail-name">{d.name}</span>
                    {busy ? <span className="agent-busy-dot" /> : null}
                  </button>
                  <div className="agent-rail-item-actions">
                    {!isTeam && split && !inPanel ? (
                      <button
                        type="button"
                        className="ghost-button"
                        title="Открыть рядом"
                        onClick={() => openSplitWith(d.id)}
                      >
                        ‖
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="ghost-button"
                      title="Дублировать"
                      onClick={() => onDuplicate(d.id)}
                    >
                      ⎘
                    </button>
                    <button
                      type="button"
                      className="ghost-button"
                      title="Удалить"
                      onClick={() => onDelete(d.id)}
                    >
                      ×
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="agent-rail-foot">
            {store.drafts.length}/{MAX_DRAFTS}
            {isTeam && teamOrderedIds.length ? ` · в команде ${teamOrderedIds.length}` : ""}
          </p>
        </aside>

        <div className={`agent-panels${split ? " agent-panels--split" : ""}`}>
          {panelIds.map((id) => panel(id))}
        </div>
      </div>

      {mobileSheet && active ? (
        <div className="agent-sheet" role="dialog" aria-modal="true" aria-label="Настройки агента">
          <div className="agent-sheet-backdrop" onClick={() => setMobileSheet(false)} />
          <div className="agent-sheet-panel">
            <header className="agent-sheet-head">
              <h3>{active.name}</h3>
              <button type="button" className="ghost-button" onClick={() => setMobileSheet(false)}>
                Закрыть
              </button>
            </header>
            {builder(active)}
          </div>
        </div>
      ) : null}
    </section>
  );
}
