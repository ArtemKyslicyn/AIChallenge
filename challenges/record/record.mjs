/**
 * Record challenge 04 (×T) and 05 (Performance Studio) against prod.
 * Output: ../04-temperature/challenge-04.webm, ../05-model-tiers/challenge-05.webm
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.BASE_URL || "https://aichallenge.arcilite.ru";
const PROMPT =
  process.env.CHALLENGE_PROMPT ||
  fs.readFileSync(path.join(__dirname, "../04-temperature/prompt.txt"), "utf8").trim();

const out04 = path.join(__dirname, "../04-temperature/challenge-04.webm");
const out05 = path.join(__dirname, "../05-model-tiers/challenge-05.webm");

async function settle(page, ms = 800) {
  await page.waitForTimeout(ms);
}

async function recordSegment(page, outPath, run) {
  await page.video()?.saveAs?.(outPath); // no-op until context closes; we use per-context videos
}

async function withVideo(outPath, fn) {
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    locale: "ru-RU",
    recordVideo: { dir: path.join(__dirname, ".videos"), size: { width: 1280, height: 800 } },
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
      fs.renameSync(tmp, outPath);
      console.log("wrote", outPath);
    }
  }
}

async function challenge04(page) {
  await page.goto(BASE + "/", { waitUntil: "domcontentloaded", timeout: 60_000 });
  await settle(page, 1500);

  // Dismiss nothing — click ×T mode
  const tempChip = page.getByRole("button", { name: /×T|Темп/i }).first();
  if (await tempChip.count()) {
    await tempChip.click();
  } else {
    await page.getByTitle(/temperature|Темп/i).first().click();
  }
  await settle(page, 600);

  const box = page.getByRole("textbox").last();
  await box.click();
  await box.fill(PROMPT);
  await settle(page, 400);

  await page.getByRole("button", { name: /Отправить|Send/i }).click();
  // Wait for studio answers / verdict section
  await page.waitForSelector("text=Студия температуры", { timeout: 30_000 }).catch(() => {});
  await settle(page, 2000);
  await page
    .waitForFunction(
      () => {
        const t = document.body?.innerText || "";
        return t.includes("Выводы") || (!t.includes("/3 ответа") && t.includes("t = 1.2"));
      },
      { timeout: 240_000 },
    )
    .catch(() => {});
  await settle(page, 2500);
  await page.evaluate(() => window.scrollBy(0, 500));
  await settle(page, 1500);
  await page.evaluate(() => window.scrollBy(0, 700));
  await settle(page, 2000);
}

async function challenge05(page) {
  await page.goto(BASE + "/", { waitUntil: "domcontentloaded", timeout: 60_000 });
  await settle(page, 1500);

  const modelsFab = page.getByRole("button", { name: /^Модели$/i });
  await modelsFab.click();
  await settle(page, 1000);

  // Default tab may be ranking — open Студия
  const studioTab = page.getByRole("tab", { name: /Студия/i });
  await studioTab.click();
  await settle(page, 1000);

  await page.getByText("День 5 · Performance Studio").waitFor({ timeout: 15_000 });

  const promptBox = page.locator(".perf-studio-textarea");
  await promptBox.fill(PROMPT);
  await settle(page, 500);

  await page.getByRole("button", { name: /Запустить сравнение/i }).click();
  await settle(page, 1500);

  // Wait until export appears (all three tiers finished + optional judge).
  await page
    .getByRole("button", { name: /Экспорт JSON/i })
    .waitFor({ timeout: 240_000 })
    .catch(() => {});
  await settle(page, 2500);
  await page.locator(".perf-studio").evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  }).catch(() => {});
  await settle(page, 2000);
  await page.evaluate(() => window.scrollBy(0, 200));
  await settle(page, 1500);
}

console.log("Recording challenge 04 against", BASE);
await withVideo(out04, challenge04);
console.log("Recording challenge 05 against", BASE);
await withVideo(out05, challenge05);
console.log("done");
