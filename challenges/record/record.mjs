/**
 * Record challenge 04 (×T) and 05 (Performance Studio) against prod.
 * Writes high-visibility .webm then converts to .mp4 via ffmpeg.
 */
import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.BASE_URL || "https://aichallenge.arcilite.ru";
const PROMPT =
  process.env.CHALLENGE_PROMPT ||
  fs.readFileSync(path.join(__dirname, "../04-temperature/prompt.txt"), "utf8").trim();

const W = 1600;
const H = 1000;

async function settle(page, ms = 800) {
  await page.waitForTimeout(ms);
}

async function bumpReadability(page, zoom = 1.25) {
  await page.addStyleTag({
    content: `
      html { zoom: ${zoom} !important; }
      .temp-studio-frame, .lab-frame, .perf-studio-card {
        box-shadow: 0 0 0 2px rgba(234, 88, 12, 0.35) !important;
      }
      .temp-studio-frame-body, .lab-frame-body, .perf-studio-answer pre,
      .compare-pane .body, .md {
        font-size: 15px !important;
        line-height: 1.5 !important;
      }
      .models-float--studio {
        max-height: min(88vh, 920px) !important;
        height: min(88vh, 920px) !important;
      }
    `,
  });
}

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
  return mp4Path;
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
  try {
    await fn(page);
  } finally {
    const video = page.video();
    await context.close();
    await browser.close();
    if (video) {
      const tmp = await video.path();
      fs.renameSync(tmp, webmPath);
      console.log("wrote", webmPath);
      toMp4(webmPath);
    }
  }
}

async function dwellScroll(page, selector, holdMs = 3500) {
  const loc = page.locator(selector).first();
  if ((await loc.count()) === 0) return;
  await loc.scrollIntoViewIfNeeded();
  await settle(page, holdMs);
}

async function challenge04(page) {
  await page.goto(BASE + "/", { waitUntil: "networkidle", timeout: 90_000 });
  await bumpReadability(page, 1.2);
  await settle(page, 1200);

  await page.getByRole("button", { name: /×T|Темп/i }).first().click();
  await settle(page, 800);

  const box = page.locator("textarea").last();
  await box.click();
  await box.fill(PROMPT);
  await settle(page, 1000);

  await page.getByRole("button", { name: /Отправить|Send/i }).click();
  await page.getByRole("heading", { name: "Студия температуры" }).waitFor({ timeout: 60_000 });
  await settle(page, 2000);

  // Wait until all three answers landed (no "N/3 ответа") and preferably Выводы.
  await page.waitForFunction(
    () => {
      const t = document.body?.innerText || "";
      if (t.includes("/3 ответа")) return false;
      return t.includes("t = 0") && (t.includes("Выводы") || t.includes("t = 1.2"));
    },
    { timeout: 300_000 },
  );
  await settle(page, 2000);

  // Slow tour of each temperature answer
  const frames = page.locator(".temp-studio-frame");
  const n = await frames.count();
  for (let i = 0; i < n; i++) {
    await frames.nth(i).scrollIntoViewIfNeeded();
    await settle(page, 4500);
    // Peek inside scrollable body
    await frames
      .nth(i)
      .locator(".temp-studio-frame-body, .compare-pane")
      .first()
      .evaluate((el) => {
        el.scrollTop = Math.min(180, el.scrollHeight);
      })
      .catch(() => {});
    await settle(page, 2500);
  }

  await dwellScroll(page, ".temp-studio-verdict", 6000);
  await settle(page, 2000);
}

async function challenge05(page) {
  await page.goto(BASE + "/", { waitUntil: "networkidle", timeout: 90_000 });
  await bumpReadability(page, 1.15);
  await settle(page, 1200);

  await page.getByRole("button", { name: /^Модели$/i }).click();
  await settle(page, 1000);
  await page.getByRole("tab", { name: /Студия/i }).click();
  await settle(page, 1200);
  await page.getByText("День 5 · Performance Studio").waitFor({ timeout: 20_000 });
  await settle(page, 1500);

  await page.locator(".perf-studio-textarea").fill(PROMPT);
  await settle(page, 1000);
  await page.getByRole("button", { name: /Запустить сравнение/i }).click();

  await page.getByRole("button", { name: /Экспорт JSON/i }).waitFor({ timeout: 300_000 });
  await settle(page, 2500);

  // Expand each tier answer if collapsed, then linger on metrics + text
  const cards = page.locator(".perf-studio-card");
  const n = await cards.count();
  for (let i = 0; i < n; i++) {
    const card = cards.nth(i);
    await card.scrollIntoViewIfNeeded();
    const expand = card.getByRole("button", { name: /Показать ответ|Скрыть ответ/i });
    if ((await expand.count()) > 0) {
      const label = await expand.first().innerText();
      if (/Показать/.test(label)) {
        await expand.first().click();
        await settle(page, 1000);
      }
    }
    await settle(page, 4000);
  }

  // Verdict / summary if present
  await dwellScroll(page, ".perf-studio-verdict, .perf-studio-summary, .perf-studio", 5000);
  await settle(page, 2500);
}

const out04 = path.join(__dirname, "../04-temperature/challenge-04.webm");
const out05 = path.join(__dirname, "../05-model-tiers/challenge-05.webm");

console.log("Recording challenge 04 against", BASE);
await withVideo(out04, challenge04);
console.log("Recording challenge 05 against", BASE);
await withVideo(out05, challenge05);
console.log("done");
