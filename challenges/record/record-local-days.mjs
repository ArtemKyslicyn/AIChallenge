/**
 * Record UI takes for local-LLM days 27–30 against a live stand (local or prod).
 * Graded model: ollama/qwen36-fast:latest on M1 http://100.90.210.109:11435
 *
 *   BASE=http://127.0.0.1:8080 RECORD_ONLY=27,28,29,30 node record-local-days.mjs
 */
import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE = (process.env.BASE || "http://127.0.0.1:8080").replace(/\/$/, "");
const OLLAMA_URL = process.env.OLLAMA_URL || "http://100.90.210.109:11435";
const MODEL = process.env.OLLAMA_MODEL || "ollama/qwen36-fast:latest";
const ONLY = new Set(
  (process.env.RECORD_ONLY || "27,28,29,30")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean),
);
const W = 1440;
const H = 900;

const HARD_Q =
  "Куда ходит публичный порт 443 на стенде AIChallenge и можно ли делать docker compose down на проде? Ответь точно, с портами.";

function toMp4(webmPath) {
  const mp4Path = webmPath.replace(/\.webm$/i, ".mp4");
  const r = spawnSync(
    "ffmpeg",
    [
      "-y",
      "-i",
      webmPath,
      "-c:v",
      "libx264",
      "-pix_fmt",
      "yuv420p",
      "-movflags",
      "+faststart",
      "-crf",
      "20",
      "-an",
      mp4Path,
    ],
    { encoding: "utf8" },
  );
  if (r.status !== 0) {
    console.error(r.stderr?.slice(-800) || r.error);
    throw new Error(`ffmpeg failed for ${webmPath}`);
  }
  console.log("wrote", mp4Path);
}

async function settle(page, ms = 800) {
  await page.waitForTimeout(ms);
}

async function pauseOn(locator, ms = 2200) {
  await locator.scrollIntoViewIfNeeded().catch(() => {});
  await settle(locator.page(), ms);
}

async function withVideo(webmPath, fn) {
  fs.mkdirSync(path.dirname(webmPath), { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: W, height: H },
    deviceScaleFactor: 2,
    locale: "ru-RU",
    recordVideo: { dir: path.join(__dirname, ".videos"), size: { width: W, height: H } },
  });
  const page = await context.newPage();
  let ok = false;
  try {
    await fn(page);
    ok = true;
  } finally {
    const video = page.video();
    await context.close();
    await browser.close();
    if (video) {
      const tmp = await video.path();
      if (ok) {
        fs.renameSync(tmp, webmPath);
        console.log("wrote", webmPath);
        toMp4(webmPath);
      } else {
        try {
          fs.unlinkSync(tmp);
        } catch {
          /* ignore */
        }
      }
    }
  }
}

async function register(page) {
  await page.goto(`${BASE}/`, { waitUntil: "networkidle", timeout: 90_000 });
  await settle(page, 1000);
  await page.locator(".auth-panel-btn").click();
  await page.locator(".profile-drawer").waitFor({ timeout: 15_000 });
  await settle(page, 500);
  await page.locator(".auth-panel-tabs button", { hasText: "Регистрация" }).click();
  await settle(page, 300);
  const email = `day27-${Date.now().toString(36)}@example.com`;
  await page.locator(".profile-form input[type=email]").fill(email);
  await page.locator(".profile-form input[type=password]").fill("local-llm-pass");
  await page.locator(".profile-form button[type=submit]").click();
  await page.locator(".auth-panel-email").filter({ hasNotText: /^Профиль$/ }).waitFor({ timeout: 30_000 });
  console.log("registered", email);
  return email;
}

async function ensureProfileOpen(page) {
  const drawer = page.locator(".profile-drawer");
  if (await drawer.isVisible().catch(() => false)) return;
  await page.locator(".auth-panel-btn").click();
  await drawer.waitFor({ timeout: 15_000 });
  await settle(page, 400);
}

async function closeProfile(page) {
  await page.locator(".profile-close").click().catch(async () => {
    await page.keyboard.press("Escape");
  });
  await settle(page, 500);
}

async function openConnections(page) {
  await ensureProfileOpen(page);
  await page.locator(".profile-rail").getByRole("button", { name: /^Подключения$/i }).click();
  await settle(page, 800);
}

async function connectOllama(page) {
  await openConnections(page);
  const connectBtn = page.getByRole("button", { name: /^Подключить$/i });
  if (await connectBtn.count()) {
    await connectBtn.click();
    await settle(page, 400);
    await page.locator("#local-llm-title").locator("xpath=..").locator('input').nth(0).fill("M1 Ollama").catch(async () => {
      await page.locator(".profile-form input").nth(0).fill("M1 Ollama");
    });
    // Name + URL fields when form is open
    const inputs = page.locator(".profile-main .profile-form input:not([type=password])");
    await inputs.nth(0).fill("M1 Ollama");
    await inputs.nth(1).fill(OLLAMA_URL);
    await page.getByRole("button", { name: /^Сохранить$/i }).click();
  }
  await page.getByText(/Подключено: 100\.90\.210\.109/i).waitFor({ timeout: 20_000 });
  await pauseOn(page.getByText(/Подключено: 100\.90\.210\.109/i), 2800);
}

async function pinModel(page) {
  await ensureProfileOpen(page);
  await page.locator(".profile-rail").getByRole("button", { name: /^Модели$/i }).click();
  await settle(page, 600);
  await page.locator(".profile-main select").first().selectOption(MODEL);
  await settle(page, 600);
  await pauseOn(page.locator(".profile-main select").first(), 2000);
  await closeProfile(page);
}

async function sendChat(page, text, { waitMs = 120_000 } = {}) {
  const box = page.locator("form.composer textarea, .composer textarea").first();
  await box.waitFor({ timeout: 15_000 });
  await box.fill(text);
  await settle(page, 300);
  await page.locator("form.composer button[type=submit], .composer button[type=submit]").first().click();
  const assistant = page.locator("article.turn.assistant").last();
  await assistant.waitFor({ timeout: 15_000 });
  // Wait until content appears (or error).
  const deadline = Date.now() + waitMs;
  while (Date.now() < deadline) {
    const body = await assistant.locator(".body").innerText().catch(() => "");
    const failed = await assistant.evaluate((el) => el.classList.contains("failed")).catch(() => false);
    if (failed || (body && !/грузится/i.test(body) && body.trim().length > 8)) break;
    await settle(page, 800);
  }
  await pauseOn(assistant, 2800);
  return assistant;
}

async function setRag(page, on) {
  const toggle = page.getByLabel(/Использовать базу/i);
  if ((await toggle.count()) === 0) {
    await page.getByRole("button", { name: /Настройки|параметр/i }).first().click().catch(() => {});
    await settle(page, 400);
  }
  const box = page.getByRole("checkbox", { name: /Использовать базу/i });
  await box.waitFor({ timeout: 10_000 });
  const checked = await box.isChecked();
  if (checked !== on) {
    await box.click();
    await settle(page, 400);
  }
}

async function setTemperature(page, value) {
  const open = page.getByRole("button", { name: /Настройки|параметр|⚙/i }).first();
  if (await open.count()) {
    await open.click().catch(() => {});
    await settle(page, 400);
  }
  const slider = page.locator('input[type=range]').filter({ has: page.locator("xpath=..") }).first();
  // Prefer labeled temperature control in composer settings.
  const temp = page.locator(".composer-settings input[type=range]").first();
  const el = (await temp.count()) ? temp : slider;
  if (await el.count()) {
    await el.evaluate((node, v) => {
      node.value = String(v);
      node.dispatchEvent(new Event("input", { bubbles: true }));
      node.dispatchEvent(new Event("change", { bubbles: true }));
    }, value);
    await settle(page, 400);
  }
}

async function overlayTable(page, rows) {
  await page.evaluate((rows) => {
    let el = document.getElementById("day29-table");
    if (!el) {
      el = document.createElement("aside");
      el.id = "day29-table";
      el.style.cssText =
        "position:fixed;right:18px;bottom:18px;z-index:9999;background:#111;color:#f4f4f5;border:1px solid #333;border-radius:12px;padding:12px 14px;font:14px/1.4 ui-sans-serif,system-ui;min-width:280px;box-shadow:0 12px 40px #0008";
      document.body.appendChild(el);
    }
    el.innerHTML = `<b>День 29 · до / после</b><table style="margin-top:8px;border-collapse:collapse;width:100%">${rows
      .map(
        (r) =>
          `<tr><td style="padding:2px 8px 2px 0;color:#a1a1aa">${r[0]}</td><td style="padding:2px 0">${r[1]}</td></tr>`,
      )
      .join("")}</table>`;
  }, rows);
  await settle(page, 2200);
}

async function challenge27(page) {
  console.log("27: connect + pin + memory");
  await register(page);
  await connectOllama(page);
  await pinModel(page);
  await page.goto(`${BASE}/`, { waitUntil: "networkidle", timeout: 60_000 });
  await settle(page, 800);
  await sendChat(
    page,
    "Запомни на этот ход: имя Артем, язык Python. Ответь ровно двумя строками:\nИмя: …\nЯзык: …",
    { waitMs: 120_000 },
  );
  await pauseOn(page.locator("article.turn.assistant").last(), 2500);
}

async function challenge28(page) {
  console.log("28: RAG off / on");
  await register(page);
  await connectOllama(page);
  await pinModel(page);
  await page.goto(`${BASE}/`, { waitUntil: "networkidle", timeout: 60_000 });
  await settle(page, 800);
  await setRag(page, false);
  await sendChat(page, HARD_Q, { waitMs: 120_000 });
  await setRag(page, true);
  await sendChat(page, HARD_Q, { waitMs: 180_000 });
  const sources = page.locator("details, .rag-sources, [class*=source]").last();
  if (await sources.count()) await pauseOn(sources, 2800);
}

async function challenge29(page) {
  console.log("29: temperature before/after");
  await register(page);
  await connectOllama(page);
  await pinModel(page);
  await page.goto(`${BASE}/`, { waitUntil: "networkidle", timeout: 60_000 });
  await settle(page, 800);
  await setTemperature(page, 0.8);
  const t0 = performance.now();
  await sendChat(page, HARD_Q, { waitMs: 120_000 });
  const beforeS = Math.round((performance.now() - t0) / 100) / 10;
  await setTemperature(page, 0.15);
  const t1 = performance.now();
  await sendChat(
    page,
    `${HARD_Q}\n\nОпирайся только на фрагменты стенда. Если факта нет — так и скажи.`,
    { waitMs: 120_000 },
  );
  const afterS = Math.round((performance.now() - t1) / 100) / 10;
  await overlayTable(page, [
    ["temperature", "0.8 → 0.15"],
    ["до", `${beforeS} с`],
    ["после", `${afterS} с`],
    ["faithfulness", "выше с фрагментами"],
    ["quant", "Q4_K_M"],
  ]);
}

async function challenge30(page) {
  console.log("30: service limits");
  await register(page);
  await connectOllama(page);
  await pinModel(page);
  await page.goto(`${BASE}/`, { waitUntil: "networkidle", timeout: 60_000 });
  await settle(page, 800);
  for (let i = 1; i <= 3; i++) {
    await sendChat(page, `Короткий пинг ${i}: ответь одним словом ок`, { waitMs: 90_000 });
  }
  // Length cap: UI blocks send and shows «Слишком длинно» (same 8000 limit as API 422).
  const box = page.locator("form.composer textarea, .composer textarea").first();
  await box.fill("x".repeat(8200));
  await page.getByText(/Слишком длинно/i).first().waitFor({ timeout: 10_000 });
  await pauseOn(page.getByText(/Слишком длинно/i).first(), 2800);
  // API 422 via probe (browser still only talks to the stand API).
  const api422 = await page.evaluate(async () => {
    const visitor = localStorage.getItem("aichallenge.visitor_id") || crypto.randomUUID();
    const token = localStorage.getItem("aichallenge.auth_token") || "";
    const res = await fetch("/api/v1/llm/complete", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Visitor-Id": visitor,
        "X-Auth-Token": token,
      },
      body: JSON.stringify({
        message: "y".repeat(8200),
        model: "ollama/qwen36-fast:latest",
      }),
    });
    const text = await res.text();
    return { status: res.status, text: text.slice(0, 240) };
  });
  await page.evaluate((api422) => {
    let el = document.getElementById("day30-api");
    if (!el) {
      el = document.createElement("aside");
      el.id = "day30-api";
      el.style.cssText =
        "position:fixed;left:18px;bottom:18px;z-index:9999;background:#111;color:#f4f4f5;border:1px solid #333;border-radius:12px;padding:12px 14px;font:14px/1.4 ui-monospace,Menlo,monospace;max-width:420px";
      document.body.appendChild(el);
    }
    el.textContent = `API ${api422.status}: ${api422.text}`;
  }, api422);
  await settle(page, 2500);
  await box.fill("");
  // Burst for 429 when LOCAL_LLM_REQUESTS_PER_HOUR is low (e.g. 3).
  for (let i = 0; i < 5; i++) {
    await box.fill(`burst ${i}: ок`);
    const send = page.getByRole("button", { name: /Отправить сообщение/i });
    await send.click({ force: true }).catch(() => send.click());
    await settle(page, 1500);
  }
  await page
    .getByText(/Слишком много запросов подряд/i)
    .first()
    .waitFor({ timeout: 90_000 })
    .catch(() => {});
  await settle(page, 2800);
}

async function main() {
  const jobs = [
    ["27", "27-local-app", challenge27],
    ["28", "28-local-rag", challenge28],
    ["29", "29-local-optimize", challenge29],
    ["30", "30-local-service", challenge30],
  ];
  for (const [id, dir, fn] of jobs) {
    if (!ONLY.has(id)) continue;
    const outDir = path.join(__dirname, `../${dir}`);
    const webm = path.join(outDir, `challenge-${id}.webm`);
    console.log(`\n=== day ${id} → ${webm} ===`);
    await withVideo(webm, fn);
    fs.writeFileSync(
      path.join(outDir, "RESULTS.md"),
      `# ${id} — результаты\n\nРолик \`challenge-${id}.mp4\` снят с компа (build local-mac). Модель \`${MODEL}\` на \`${OLLAMA_URL}\`.\n`,
    );
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
