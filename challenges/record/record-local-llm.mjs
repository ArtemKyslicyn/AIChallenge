/**
 * One take for local LLM days: live M1 Ollama (qwen36-fast), three prompts,
 * then the same hard question with stand context. Writes webm + mp4.
 */
import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const M1 = process.env.OLLAMA_URL || "http://100.90.210.109:11435";
const MODEL = process.env.OLLAMA_MODEL || "qwen36-fast:latest";
const OUT_DIR = path.join(__dirname, "../26-local-llm");
const WEBM = path.join(OUT_DIR, "challenge-26.webm");
const W = 1600;
const H = 1000;

const CONTEXT = [
  "AGENTS.md · Always",
  "Каждому ответу ассистента атрибутируется model_id (DB + SSE + UI).",
  "Публичный :443 — это xray → nginx :8443 → web :18080.",
  "На проде нельзя docker compose down. Только rolling up и проверка :443 и :8443.",
].join("\n");

const STEPS = [
  {
    id: "easy",
    day: "26 · лёгкий",
    title: "Память Agent 07",
    prompt:
      "Запомни на этот ход: имя Артем, язык Python. Ответь ровно двумя строками:\nИмя: …\nЯзык: …",
    temperature: 0,
    num_predict: 40,
    system: "Отвечай строго в запрошенном формате. Две строки, без пояснений.",
  },
  {
    id: "medium",
    day: "26 · средний",
    title: "Что такое model_id",
    prompt: "Что такое model_id в ответах ассистента на стенде AIChallenge? Два предложения.",
    temperature: 0.2,
    num_predict: 120,
    system: `Опирайся только на фрагмент.\n\n${CONTEXT}`,
  },
  {
    id: "hard-before",
    day: "29 · до",
    title: "Порт 443 без базы",
    prompt:
      "Куда ходит публичный порт 443 на стенде AIChallenge и можно ли делать docker compose down на проде? Ответь точно, с портами.",
    temperature: 0.8,
    num_predict: 160,
    system: "",
  },
  {
    id: "hard-after",
    day: "28–29 · после",
    title: "Порт 443 по фрагменту стенда",
    prompt:
      "Куда ходит публичный порт 443 на стенде AIChallenge и можно ли делать docker compose down на проде? Ответь точно, с портами.",
    temperature: 0.15,
    num_predict: 140,
    system: `Опирайся только на фрагменты. Если факта нет — так и скажи. Не выдумывай порты.\n\n${CONTEXT}`,
  },
];

function toMp4(webmPath) {
  const mp4Path = webmPath.replace(/\.webm$/i, ".mp4");
  const r = spawnSync(
    "ffmpeg",
    ["-y", "-i", webmPath, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-crf", "20", "-an", mp4Path],
    { encoding: "utf8" },
  );
  if (r.status !== 0) {
    console.error(r.stderr?.slice(-800) || r.error);
    throw new Error(`ffmpeg failed for ${webmPath}`);
  }
  console.log("wrote", mp4Path);
}

async function chat(step) {
  const messages = [];
  if (step.system) messages.push({ role: "system", content: step.system });
  messages.push({ role: "user", content: step.prompt });
  const body = {
    model: MODEL,
    stream: false,
    think: false,
    messages,
    options: { temperature: step.temperature, num_predict: step.num_predict },
  };
  const t0 = performance.now();
  const response = await fetch(`${M1}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(240_000),
  });
  if (!response.ok) throw new Error(`Ollama HTTP ${response.status}`);
  const data = await response.json();
  const wall = (performance.now() - t0) / 1000;
  const text = String(data?.message?.content || "").trim();
  const evalCount = Number(data.eval_count || 0);
  const evalNs = Number(data.eval_duration || 0);
  const tps = evalNs ? Math.round((evalCount / (evalNs / 1e9)) * 10) / 10 : 0;
  return { text, wall: Math.round(wall * 10) / 10, tps, evalCount, model: String(data.model || MODEL) };
}

async function tags() {
  const response = await fetch(`${M1}/api/tags`, { signal: AbortSignal.timeout(8_000) });
  if (!response.ok) throw new Error(`tags HTTP ${response.status}`);
  const data = await response.json();
  return (data.models || []).map((m) => ({
    name: m.name,
    size: m.details?.parameter_size || "",
    quant: m.details?.quantization_level || "",
  }));
}

async function probe(url) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 4_000);
  try {
    const response = await fetch(url, { signal: ctrl.signal });
    return response.ok ? "открыт" : `HTTP ${response.status}`;
  } catch {
    return "нет ответа";
  } finally {
    clearTimeout(timer);
  }
}

function pageHtml() {
  return `<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8" />
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: #141414; color: #f4f4f5;
    font: 18px/1.45 ui-sans-serif, system-ui, sans-serif;
  }
  header { padding: 28px 36px 8px; }
  h1 { margin: 0; font-size: 34px; font-weight: 650; letter-spacing: -0.03em; }
  .sub { margin: 8px 0 0; color: #a1a1aa; font-size: 16px; }
  .hosts { display: flex; gap: 12px; padding: 18px 36px 0; }
  .host {
    flex: 1; border: 1px solid #2a2a2a; border-radius: 12px; padding: 12px 14px;
    background: #1b1b1b;
  }
  .host b { display: block; font-size: 15px; margin-bottom: 4px; }
  .host span { color: #d4d4d8; font-size: 14px; }
  .ok { color: #86efac; }
  .bad { color: #fca5a5; }
  main { padding: 18px 36px 28px; display: grid; gap: 14px; }
  article {
    border: 1px solid #2e2e2e; border-radius: 14px; padding: 14px 16px; background: #1a1a1a;
  }
  .meta { display: flex; gap: 10px; align-items: baseline; color: #a1a1aa; font-size: 13px; }
  .pill {
    border: 1px solid #3f3f46; border-radius: 999px; padding: 2px 8px; color: #e4e4e7;
  }
  h2 { margin: 8px 0 6px; font-size: 20px; }
  pre {
    margin: 0; white-space: pre-wrap; font: 17px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace;
  }
  .wait { color: #fbbf24; }
  .stats { margin-top: 8px; color: #a1a1aa; font-size: 14px; }
</style>
</head>
<body>
  <header>
    <h1>Локальная LLM · M1 · qwen36-fast</h1>
    <p class="sub" id="sub">35.5B Q4_K_M · native /api/chat · think выключен</p>
  </header>
  <section class="hosts" id="hosts"></section>
  <main id="feed"></main>
</body>
</html>`;
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const catalog = await tags();
  const kalinin = await probe("http://100.126.31.97:11434/api/tags");
  const mac = await probe("http://127.0.0.1:11434/api/tags");
  const big = catalog.filter((m) => /35b|33b|27b|36-fast|38-fast/i.test(m.name));

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: W, height: H },
    deviceScaleFactor: 2,
    locale: "ru-RU",
    recordVideo: { dir: path.join(__dirname, ".videos"), size: { width: W, height: H } },
  });
  const page = await context.newPage();
  const runs = [];
  let ok = false;
  try {
    await page.setContent(pageHtml());
    await page.evaluate(
      ({ big, kalinin, mac, m1 }) => {
        const hosts = document.getElementById("hosts");
        const card = (title, body, kind) =>
          `<div class="host"><b>${title}</b><span class="${kind}">${body}</span></div>`;
        hosts.innerHTML = [
          card("M1 · :11435", `${m1} · ${big.map((m) => m.name).slice(0, 4).join(", ")}`, "ok"),
          card("Этот Mac · :11434", mac === "открыт" ? "есть только 8B, не сдаём" : mac, mac === "открыт" ? "ok" : "bad"),
          card("kalinin-gpu · :11434", kalinin === "открыт" ? "Ollama открыт" : "прямой порт закрыт, туннель ssh -N → :21434", "bad"),
        ].join("");
      },
      { big, kalinin, mac, m1: M1.replace("http://", "") },
    );
    await page.waitForTimeout(1600);

    for (const step of STEPS) {
      await page.evaluate((step) => {
        const feed = document.getElementById("feed");
        const node = document.createElement("article");
        node.id = `step-${step.id}`;
        node.innerHTML = `<div class="meta"><span class="pill">${step.day}</span><span>t=${step.temperature} · num_predict=${step.num_predict}</span></div><h2>${step.title}</h2><pre class="wait">Запрос на M1…</pre>`;
        feed.prepend(node);
      }, step);
      await page.waitForTimeout(500);
      const result = await chat(step);
      runs.push({ id: step.id, day: step.day, title: step.title, ...result });
      console.log(step.id, result.wall, "s", result.tps, "tok/s", result.text.slice(0, 80).replaceAll("\n", " "));
      await page.evaluate(
        ({ id, result, model }) => {
          const node = document.getElementById(`step-${id}`);
          const pre = node.querySelector("pre");
          pre.className = "";
          pre.textContent = result.text || "(пустой content)";
          const stats = document.createElement("div");
          stats.className = "stats";
          stats.textContent = `${result.wall} с · ${result.tps} ток/с · ${result.evalCount} токенов · model_id ollama/${model}`;
          node.appendChild(stats);
        },
        { id: step.id, result, model: MODEL },
      );
      await page.waitForTimeout(2200);
    }
    await page.waitForTimeout(1200);
    ok = true;
  } finally {
    const video = page.video();
    await context.close();
    await browser.close();
    if (video && ok) {
      const tmp = await video.path();
      fs.renameSync(tmp, WEBM);
      console.log("wrote", WEBM);
      toMp4(WEBM);
    }
  }

  fs.writeFileSync(
    path.join(OUT_DIR, "results.json"),
    JSON.stringify({ model: MODEL, base: M1, catalog: big, kalinin, mac, runs }, null, 2),
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
