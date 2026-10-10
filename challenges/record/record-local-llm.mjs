/**
 * Day 26 — live M1 Ollama take. Readable overlay, real hosts, light humor.
 * Writes challenge-26.webm + .mp4
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
  "Фрагмент стенда AIChallenge:",
  "• под каждым ответом ассистента виден model_id (DB + SSE + UI);",
  "• публичный :443 — xray → nginx :8443 → web :18080;",
  "• на проде нельзя docker compose down — только rolling up и проверка :443/:8443.",
].join("\n");

const STEPS = [
  {
    id: "easy",
    day: "26 · лёгкий",
    title: "Стикер на монитор",
    prompt:
      "Я Артем, пишу на Python. Ответь ровно двумя строками, как стикер на монитор:\nИмя: …\nЯзык: …",
    temperature: 0,
    num_predict: 40,
    system: "Только две строки в запрошенном формате. Без предисловий и юмора сверх формата.",
  },
  {
    id: "medium",
    day: "26 · средний",
    title: "model_id — не UUID чата",
    prompt:
      "Коллега думает, что model_id — это id сессии. Объясни за 2 предложения, зачем model_id под ответом на стенде AIChallenge.",
    temperature: 0.2,
    num_predict: 140,
    system: `Опирайся только на фрагмент.\n\n${CONTEXT}`,
  },
  {
    id: "hard-before",
    day: "29 · до",
    title: "Порт 443 «на глаз»",
    prompt:
      "Куда у нас публичный :443 и можно ли на проде сделать docker compose down «на всякий случай»? Ответь уверенно, с портами.",
    temperature: 0.8,
    num_predict: 180,
    system: "",
  },
  {
    id: "hard-after",
    day: "28–29 · после",
    title: "Порт 443 по бумажке со стенда",
    prompt:
      "Куда у нас публичный :443 и можно ли на проде сделать docker compose down «на всякий случай»? Ответь точно, с портами.",
    temperature: 0.15,
    num_predict: 160,
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
    margin: 0; background: #121212; color: #fafafa;
    font: 20px/1.5 ui-sans-serif, system-ui, sans-serif;
  }
  header { padding: 32px 40px 10px; }
  h1 { margin: 0; font-size: 38px; font-weight: 700; letter-spacing: -0.03em; }
  .sub { margin: 10px 0 0; color: #a1a1aa; font-size: 18px; }
  .hosts { display: flex; gap: 14px; padding: 20px 40px 0; }
  .host {
    flex: 1; border: 1px solid #2f2f2f; border-radius: 14px; padding: 14px 16px;
    background: #1a1a1a;
  }
  .host b { display: block; font-size: 17px; margin-bottom: 6px; }
  .host span { color: #e4e4e7; font-size: 15px; line-height: 1.4; }
  .ok { color: #86efac; }
  .bad { color: #fca5a5; }
  main { padding: 20px 40px 36px; display: grid; gap: 16px; }
  article {
    border: 1px solid #333; border-radius: 16px; padding: 16px 18px; background: #181818;
  }
  .meta { display: flex; gap: 12px; align-items: baseline; color: #a1a1aa; font-size: 14px; }
  .pill {
    border: 1px solid #3f3f46; border-radius: 999px; padding: 3px 10px; color: #f4f4f5;
    background: #27272a;
  }
  h2 { margin: 10px 0 8px; font-size: 24px; }
  pre {
    margin: 0; white-space: pre-wrap; font: 19px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
    color: #fafafa;
  }
  .wait { color: #fbbf24; }
  .stats { margin-top: 10px; color: #d4d4d8; font-size: 15px; }
  .ask { margin: 0 0 8px; color: #a1a1aa; font-size: 15px; }
</style>
</head>
<body>
  <header>
    <h1>День 26 · локальная LLM с компа</h1>
    <p class="sub" id="sub">M1 · qwen36-fast · 35.5B Q4_K_M · браузер сюда не ходит — только API/запись</p>
  </header>
  <section class="hosts" id="hosts"></section>
  <main id="feed"></main>
</body>
</html>`;
}

async function warmup() {
  console.log("warmup", MODEL);
  const response = await fetch(`${M1}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: MODEL,
      stream: false,
      think: false,
      keep_alive: "30m",
      messages: [{ role: "user", content: "Скажи одно слово: ок" }],
      options: { temperature: 0, num_predict: 8 },
    }),
    signal: AbortSignal.timeout(300_000),
  });
  if (!response.ok) throw new Error(`warmup HTTP ${response.status}`);
  const data = await response.json();
  const text = String(data?.message?.content || "").trim();
  if (!text) throw new Error("warmup returned empty content — model not ready");
  console.log("warmup ok:", text.slice(0, 40));
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  await warmup();
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
          card(
            "Этот Mac · :11434",
            mac === "открыт" ? "есть только 8B — в зачёт не идут" : mac,
            mac === "открыт" ? "ok" : "bad",
          ),
          card(
            "kalinin-gpu · :11434",
            kalinin === "открыт" ? "Ollama открыт" : "прямой порт закрыт · туннель ssh -N → :21434",
            "bad",
          ),
        ].join("");
      },
      { big, kalinin, mac, m1: M1.replace("http://", "") },
    );
    await page.waitForTimeout(1800);

    for (const step of STEPS) {
      await page.evaluate((step) => {
        const feed = document.getElementById("feed");
        const node = document.createElement("article");
        node.id = `step-${step.id}`;
        node.innerHTML = `<div class="meta"><span class="pill">${step.day}</span><span>t=${step.temperature} · max ${step.num_predict} ток.</span></div><h2>${step.title}</h2><p class="ask">${step.prompt.replaceAll("<", "&lt;")}</p><pre class="wait">Ждём ответ с M1…</pre>`;
        feed.prepend(node);
      }, step);
      await page.waitForTimeout(700);
      const result = await chat(step);
      runs.push({ id: step.id, day: step.day, title: step.title, ...result });
      console.log(step.id, result.wall, "s", result.tps, "tok/s", result.text.slice(0, 90).replaceAll("\n", " "));
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
      await page.waitForTimeout(2600);
    }
    await page.waitForTimeout(1400);
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
  fs.writeFileSync(
    path.join(OUT_DIR, "RESULTS.md"),
    `# 26 — результаты\n\nРолик \`challenge-26.mp4\` снят на \`${MODEL}\` (${M1}). Цифры в \`results.json\`.\n`,
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
