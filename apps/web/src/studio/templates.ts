/** Built-in graph templates + default demo for «Схема Агентов». */

import type { Edge, Node } from "@xyflow/react";

import type { AgentNodeData } from "./types";

function n(
  id: string,
  kind: AgentNodeData["kind"],
  label: string,
  x: number,
  y: number,
  extra?: Partial<AgentNodeData>,
): Node<AgentNodeData> {
  return {
    id,
    type: "agentGraph",
    position: { x, y },
    data: { kind, label, ...extra },
  };
}

function e(id: string, source: string, target: string): Edge {
  return {
    id,
    source,
    target,
    sourceHandle: "out",
    targetHandle: "in",
    type: "smoothstep",
  };
}

export type GraphTemplate = {
  id: string;
  title: string;
  blurb: string;
  nodes: Node<AgentNodeData>[];
  edges: Edge[];
};

/** Default run prompt paired with the showcase demo. */
export const DEMO_RUN_INPUT =
  "Придумай концепт чат-платформы для командной работы: 3 фичи, риски и короткий план MVP на 2 недели.";

/**
 * Showcase DAG: brief → 3 parallel lenses → merge → editor → end.
 * Used as the first-open default scheme.
 */
export const DEMO_TEMPLATE: GraphTemplate = {
  id: "demo",
  title: "Демо: идея → MVP",
  blurb: "Бриф → 3 параллельных агента → слияние → редактор",
  nodes: [
    n("d-start", "start", "Идея", 40, 230),
    n("d-brief", "agent", "Бриф", 240, 210, {
      preferredModel: "auto",
      systemPrompt:
        "Ты product-brief агент. Из входа пользователя выдели: цель, аудиторию, ограничение и один критерий успеха. Ответ — до 8 коротких строк, без воды.",
    }),
    n("d-scout", "agent", "Скаут", 480, 40, {
      preferredModel: "auto",
      systemPrompt:
        "Ты исследователь. По брифу предложи 3 свежих угла/аналога и что позаимствовать. Только конкретика, список.",
    }),
    n("d-arch", "agent", "Архитектор", 480, 210, {
      preferredModel: "auto",
      systemPrompt:
        "Ты системный архитектор продукта. По брифу нарисуй минимальную архитектуру: модули, потоки данных, что отложить. Коротко, маркированный список.",
    }),
    n("d-risk", "agent", "Скептик", 480, 380, {
      preferredModel: "auto",
      systemPrompt:
        "Ты адвокат дьявола. Найди 4 главных риска и по одному смягчению на каждый. Жёстко, но конструктивно.",
    }),
    n("d-merge", "merge", "Сборка", 740, 210, {
      systemPrompt:
        "Собери три взгляда в единый черновик без повторов: угол → архитектура → риски. Сохрани структуру.",
    }),
    n("d-edit", "agent", "Редактор", 960, 190, {
      preferredModel: "auto",
      systemPrompt:
        "Ты выпускающий редактор. Преврати черновик в демо-ответ для показа заказчику: заголовок, 3 фичи, риски, план на 2 недели. Ясно и убедительно, без markdown-таблиц.",
    }),
    n("d-end", "end", "MVP-питч", 1180, 230),
  ],
  edges: [
    e("de1", "d-start", "d-brief"),
    e("de2", "d-brief", "d-scout"),
    e("de3", "d-brief", "d-arch"),
    e("de4", "d-brief", "d-risk"),
    e("de5", "d-scout", "d-merge"),
    e("de6", "d-arch", "d-merge"),
    e("de7", "d-risk", "d-merge"),
    e("de8", "d-merge", "d-edit"),
    e("de9", "d-edit", "d-end"),
  ],
};

export const GRAPH_TEMPLATES: GraphTemplate[] = [
  DEMO_TEMPLATE,
  {
    id: "chain",
    title: "Цепочка",
    blurb: "Старт → Агент A → Агент B → Конец",
    nodes: [
      n("t-start", "start", "Старт", 80, 160),
      n("t-a", "agent", "Агент A", 280, 140, {
        systemPrompt: "Ты первый агент. Кратко уточни задачу.",
      }),
      n("t-b", "agent", "Агент B", 500, 140, {
        systemPrompt: "Ты второй агент. Доработай ответ предыдущего.",
      }),
      n("t-end", "end", "Конец", 720, 160),
    ],
    edges: [
      e("e1", "t-start", "t-a"),
      e("e2", "t-a", "t-b"),
      e("e3", "t-b", "t-end"),
    ],
  },
  {
    id: "parallel",
    title: "Параллель → слияние",
    blurb: "Два агента параллельно, затем Merge",
    nodes: [
      n("p-start", "start", "Старт", 60, 180),
      n("p-a", "agent", "Агент A", 280, 60, {
        systemPrompt: "Ответь с точки зрения краткости.",
      }),
      n("p-b", "agent", "Агент B", 280, 260, {
        systemPrompt: "Ответь с точки зрения полноты.",
      }),
      n("p-merge", "merge", "Слияние", 520, 160),
      n("p-end", "end", "Конец", 740, 180),
    ],
    edges: [
      e("pe1", "p-start", "p-a"),
      e("pe2", "p-start", "p-b"),
      e("pe3", "p-a", "p-merge"),
      e("pe4", "p-b", "p-merge"),
      e("pe5", "p-merge", "p-end"),
    ],
  },
];

/** Fresh copy of the showcase demo (safe to mutate). */
export function cloneDemoGraph(name = DEMO_TEMPLATE.title): {
  name: string;
  nodes: Node<AgentNodeData>[];
  edges: Edge[];
  updatedAt: string;
} {
  return {
    name,
    nodes: structuredClone(DEMO_TEMPLATE.nodes),
    edges: structuredClone(DEMO_TEMPLATE.edges),
    updatedAt: new Date().toISOString(),
  };
}
