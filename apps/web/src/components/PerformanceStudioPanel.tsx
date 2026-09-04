import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { listModels, probeComplete, type ModelCatalogItemDto } from "../api/client";
import {
  heuristicModelStudioVerdict,
  runModelStudioJudge,
  type ModelStudioVerdict,
} from "../strategies/modelJudge";
import {
  DEFAULT_STUDIO_PROMPT,
  MODEL_TIERS,
  MODEL_TIER_IDS,
  estimateCostProxy,
  estimateTokens,
  formatCost,
  formatLatency,
  formatTokens,
  modelCardUrl,
  pickDefaultTier,
  relativeBar,
  type ModelTierId,
} from "../strategies/modelStudio";
import { EMPTY_PROBE_SLOT, type ProbeSlotState } from "../types";

interface TierResult {
  slot: ProbeSlotState;
  tokens: number;
  costProxy: number;
}

type TierMap = Record<ModelTierId, TierResult>;

function emptyTiers(): TierMap {
  const out = {} as TierMap;
  for (const id of MODEL_TIER_IDS) {
    out[id] = {
      slot: { ...EMPTY_PROBE_SLOT, loading: false, statusHint: null },
      tokens: 0,
      costProxy: 0,
    };
  }
  return out;
}

interface Props {
  /** False while the tab is hidden — abort in-flight runs and skip fetches. */
  active: boolean;
}

/**
 * Day-5 Performance Studio — lives as the «Студия» tab inside Models float.
 * Self-contained: prompt, three model tiers, metrics dashboard, verdict.
 * Does not touch the chat thread (same privacy model as ×T probes).
 */
export function PerformanceStudioPanel({ active }: Props) {
  const promptId = useId();
  const [models, setModels] = useState<ModelCatalogItemDto[]>([]);
  const [prompt, setPrompt] = useState(DEFAULT_STUDIO_PROMPT);
  const [picks, setPicks] = useState<Record<ModelTierId, string>>({
    weak: "auto",
    mid: "auto",
    strong: "auto",
  });
  const [defaultsReady, setDefaultsReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<TierMap | null>(null);
  const [verdict, setVerdict] = useState<ModelStudioVerdict | null>(null);
  const [verdictLoading, setVerdictLoading] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Partial<Record<ModelTierId, boolean>>>({});
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    listModels()
      .then((items) => {
        if (controller.signal.aborted) return;
        setModels(items);
        if (!defaultsReady) {
          setPicks(pickDefaultTier(items.map((m) => m.id)));
          setDefaultsReady(true);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setModels([]);
      });
    return () => controller.abort();
  }, [active, defaultsReady]);

  useEffect(() => {
    if (active) return;
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setVerdictLoading(false);
  }, [active]);

  const modelOptions = useMemo(
    () =>
      models.length > 0
        ? models
        : [{ id: "auto", label: "Авто (цепочка)", capabilities: { reasoning: false } }],
    [models],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setVerdictLoading(false);
  }, []);

  const run = useCallback(async () => {
    const task = prompt.trim();
    if (!task || busy) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setRunError(null);
    setVerdict(null);
    setVerdictLoading(false);
    setExpanded({});

    const loading = emptyTiers();
    for (const id of MODEL_TIER_IDS) {
      loading[id] = {
        slot: {
          ...EMPTY_PROBE_SLOT,
          loading: true,
          statusHint: `Запрос к ${picks[id]}…`,
        },
        tokens: 0,
        costProxy: estimateCostProxy(picks[id]),
      };
    }
    setResults(loading);

    const collected: Partial<
      Record<
        ModelTierId,
        { content: string; modelId: string; latencyMs: number; costProxy: number }
      >
    > = {};

    await Promise.all(
      MODEL_TIER_IDS.map(async (id) => {
        const model = picks[id];
        const t0 = performance.now();
        try {
          const result = await probeComplete(
            task,
            {
              model,
              temperature: 0.7,
              reasoning: false,
              prompt_format: false,
              prompt_length: false,
              prompt_stop: false,
            },
            controller.signal,
          );
          const latencyMs = Math.round(performance.now() - t0);
          const costProxy = estimateCostProxy(result.model_id || model);
          const tokens = estimateTokens(result.content);
          collected[id] = {
            content: result.content,
            modelId: result.model_id,
            latencyMs,
            costProxy,
          };
          setResults((prev) => {
            const next = { ...(prev ?? emptyTiers()) };
            next[id] = {
              tokens,
              costProxy,
              slot: {
                loading: false,
                error: null,
                content: result.content,
                modelId: result.model_id,
                latencyMs,
              },
            };
            return next;
          });
        } catch (e) {
          if (controller.signal.aborted) {
            setResults((prev) => {
              const next = { ...(prev ?? emptyTiers()) };
              next[id] = {
                tokens: 0,
                costProxy: estimateCostProxy(model),
                slot: {
                  loading: false,
                  error: null,
                  content: "",
                  modelId: null,
                  aborted: true,
                },
              };
              return next;
            });
            return;
          }
          const msg = e instanceof Error ? e.message : String(e);
          setResults((prev) => {
            const next = { ...(prev ?? emptyTiers()) };
            next[id] = {
              tokens: 0,
              costProxy: estimateCostProxy(model),
              slot: {
                loading: false,
                error: msg,
                content: "",
                modelId: null,
                latencyMs: Math.round(performance.now() - t0),
              },
            };
            return next;
          });
        }
      }),
    );

    if (controller.signal.aborted) {
      setBusy(false);
      return;
    }

    setBusy(false);
    const answers = MODEL_TIER_IDS.filter((id) => collected[id]?.content.trim()).map((id) => ({
      id,
      modelId: collected[id]!.modelId,
      content: collected[id]!.content,
      latencyMs: collected[id]!.latencyMs,
      costProxy: collected[id]!.costProxy,
    }));

    if (answers.length < 2) {
      setRunError("Мало успешных ответов — повторите прогон.");
      setVerdict(heuristicModelStudioVerdict(answers));
      return;
    }

    setVerdictLoading(true);
    const judge = await runModelStudioJudge({
      task,
      answers,
      judgeModel: picks.mid || picks.strong || "auto",
      signal: controller.signal,
    });
    if (controller.signal.aborted) {
      setVerdictLoading(false);
      return;
    }
    setVerdict(judge);
    setVerdictLoading(false);
  }, [busy, picks, prompt]);

  const exportJson = useCallback(() => {
    if (!results) return;
    const payload = {
      kind: "performance_studio",
      task: prompt.trim(),
      exportedAt: new Date().toISOString(),
      tiers: MODEL_TIERS.map((tier) => {
        const row = results[tier.id];
        return {
          id: tier.id,
          label: tier.label,
          requested_model: picks[tier.id],
          model_id: row.slot.modelId,
          latency_ms: row.slot.latencyMs ?? null,
          tokens_est: row.tokens,
          cost_proxy: row.costProxy,
          content: row.slot.content,
          error: row.slot.error,
          scores: verdict?.scores?.[tier.id] ?? null,
          link: row.slot.modelId ? modelCardUrl(row.slot.modelId) : null,
        };
      }),
      verdict,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `performance-studio-${Date.now().toString(36)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [picks, prompt, results, verdict]);

  const latencies = MODEL_TIER_IDS.map((id) => results?.[id]?.slot.latencyMs ?? 0);
  const costs = MODEL_TIER_IDS.map((id) => results?.[id]?.costProxy ?? 0);
  const tokenCounts = MODEL_TIER_IDS.map((id) => results?.[id]?.tokens ?? 0);
  const worstLatency = Math.max(...latencies, 1);
  const worstCost = Math.max(...costs, 0.01);
  const worstTokens = Math.max(...tokenCounts, 1);
  const done = Boolean(results && MODEL_TIER_IDS.every((id) => !results[id].slot.loading));

  return (
    <div className="perf-studio">
      <header className="perf-studio-intro">
        <p className="perf-studio-kicker">День 5 · Performance Studio</p>
        <h3 className="perf-studio-title">Один запрос — три класса моделей</h3>
        <p className="perf-studio-lead">
          Слабая · средняя · сильная. Замеряем время, токены и cost proxy, сравниваем качество.
        </p>
      </header>

      <label className="perf-studio-prompt" htmlFor={promptId}>
        <span className="perf-studio-label">Запрос</span>
        <textarea
          id={promptId}
          className="perf-studio-textarea"
          rows={3}
          value={prompt}
          disabled={busy}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Один и тот же текст для всех трёх моделей…"
        />
      </label>

      <div className="perf-studio-picks" role="group" aria-label="Модели по классам">
        {MODEL_TIERS.map((tier) => (
          <label key={tier.id} className={`perf-studio-pick perf-studio-pick--${tier.accent}`}>
            <span className="perf-studio-pick-label">{tier.label}</span>
            <span className="perf-studio-pick-hint">{tier.hint}</span>
            <select
              className="perf-studio-select"
              value={picks[tier.id]}
              disabled={busy}
              aria-label={`Модель: ${tier.label}`}
              onChange={(e) => setPicks((prev) => ({ ...prev, [tier.id]: e.target.value }))}
            >
              {modelOptions.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>

      <div className="perf-studio-actions">
        {!busy ? (
          <button
            type="button"
            className="perf-studio-run"
            disabled={!prompt.trim()}
            onClick={() => void run()}
          >
            Запустить сравнение
          </button>
        ) : (
          <button type="button" className="ghost-button" onClick={stop}>
            Остановить
          </button>
        )}
        {done && (
          <button type="button" className="ghost-button" onClick={exportJson}>
            Экспорт JSON
          </button>
        )}
      </div>

      {runError && (
        <p className="perf-studio-error" role="alert">
          {runError}
        </p>
      )}

      {results && (
        <div className="perf-studio-grid" aria-live="polite">
          {MODEL_TIERS.map((tier) => {
            const row = results[tier.id];
            const open = expanded[tier.id] ?? false;
            const modelId = row.slot.modelId;
            const quality = verdict?.scores?.[tier.id]?.quality;
            return (
              <article
                key={tier.id}
                className={`perf-studio-card perf-studio-card--${tier.accent}`}
              >
                <header className="perf-studio-card-head">
                  <div>
                    <p className="perf-studio-card-tier">{tier.label}</p>
                    {modelId ? (
                      <a
                        className="perf-studio-model-link"
                        href={modelCardUrl(modelId)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {modelId}
                      </a>
                    ) : (
                      <p className="perf-studio-model-pending">{picks[tier.id]}</p>
                    )}
                  </div>
                  {typeof quality === "number" && (
                    <span className="perf-studio-quality" title="Оценка качества 0–10">
                      Q {quality}
                    </span>
                  )}
                </header>

                <dl className="perf-studio-metrics">
                  <div>
                    <dt>Время</dt>
                    <dd>{formatLatency(row.slot.latencyMs)}</dd>
                    <div
                      className="perf-studio-bar"
                      style={{
                        width: `${relativeBar(row.slot.latencyMs ?? 0, worstLatency) * 100}%`,
                      }}
                      aria-hidden="true"
                    />
                  </div>
                  <div>
                    <dt>Токены≈</dt>
                    <dd>{formatTokens(row.tokens)}</dd>
                    <div
                      className="perf-studio-bar perf-studio-bar--tokens"
                      style={{
                        width: `${relativeBar(row.tokens, worstTokens) * 100}%`,
                      }}
                      aria-hidden="true"
                    />
                  </div>
                  <div>
                    <dt>Cost≈</dt>
                    <dd>{formatCost(row.costProxy)}</dd>
                    <div
                      className="perf-studio-bar perf-studio-bar--cost"
                      style={{
                        width: `${relativeBar(row.costProxy, worstCost) * 100}%`,
                      }}
                      aria-hidden="true"
                    />
                  </div>
                </dl>

                {row.slot.loading && (
                  <p className="perf-studio-state">
                    <span className="spinner" aria-hidden="true" />{" "}
                    {row.slot.statusHint ?? "Ждём…"}
                  </p>
                )}
                {!row.slot.loading && row.slot.error && (
                  <p className="compare-error">{row.slot.error}</p>
                )}
                {!row.slot.loading && row.slot.aborted && (
                  <p className="perf-studio-state">Остановлено</p>
                )}
                {!row.slot.loading && row.slot.content && (
                  <>
                    <button
                      type="button"
                      className="perf-studio-toggle"
                      aria-expanded={open}
                      onClick={() =>
                        setExpanded((prev) => ({ ...prev, [tier.id]: !open }))
                      }
                    >
                      {open ? "Скрыть ответ" : "Показать ответ"}
                    </button>
                    {open && (
                      <pre className="perf-studio-answer">{row.slot.content}</pre>
                    )}
                  </>
                )}
              </article>
            );
          })}
        </div>
      )}

      {verdictLoading && (
        <p className="perf-studio-state">
          <span className="spinner" aria-hidden="true" /> Сводим вывод о качестве…
        </p>
      )}

      {done && verdict && !verdictLoading && (
        <section className="perf-studio-verdict" aria-label="Вывод">
          <header className="perf-studio-verdict-head">
            <h4>Короткий вывод</h4>
            {verdict.modelId && <span className="badge">{verdict.modelId}</span>}
            {verdict.heuristic && <span className="perf-studio-chip">эвристика</span>}
          </header>
          {verdict.error && <p className="perf-studio-state">{verdict.error}</p>}
          <p className="perf-studio-summary">{verdict.summary}</p>
          <ul className="perf-studio-winners">
            <li>
              Качество: <strong>{tierLabel(verdict.winners.quality)}</strong>
            </li>
            <li>
              Скорость: <strong>{tierLabel(verdict.winners.speed)}</strong>
            </li>
            <li>
              Ресурсы: <strong>{tierLabel(verdict.winners.efficiency)}</strong>
            </li>
          </ul>
          <p className="perf-studio-footnote">
            Cost≈ — относительный proxy, не счёт провайдера. Токены≈ — оценка chars/4.
          </p>
        </section>
      )}
    </div>
  );
}

function tierLabel(id: ModelTierId | null): string {
  if (!id) return "—";
  return MODEL_TIERS.find((t) => t.id === id)?.label ?? id;
}
