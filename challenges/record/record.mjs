/**
 * Record challenge 04 (×T) and 05 (Performance Studio) against prod.
 * Pins stable models, waits for real answers (no errors), slow-scrolls content → MP4.
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

/** Stable picks for Day-5 (avoid openrouter/free remaps / safety stubs). */
const TIER_MODELS = {
  weak: process.env.CHALLENGE_WEAK || "deepseek/deepseek-v4-flash",
  mid: process.env.CHALLENGE_MID || "google/gemini-2.5-flash",
  // deepseek-chat remaps to free pool on prod — use a paid/stable id
  strong: process.env.CHALLENGE_STRONG || "mistralai/mistral-nemo",
};

/** DeepSeek: ×T forces reasoning off so temperature actually applies. */
const TEMP_MODEL = process.env.CHALLENGE_TEMP_MODEL || "deepseek/deepseek-v4-flash";

const W = 1600;
const H = 1000;

async function settle(page, ms = 800) {
  await page.waitForTimeout(ms);
}

async function bumpReadability(page, zoom = 1.2) {
  await page.addStyleTag({
    content: `
      html { zoom: ${zoom} !important; }
      .temp-studio-frame, .lab-frame, .perf-studio-card {
        box-shadow: 0 0 0 2px rgba(234, 88, 12, 0.35) !important;
      }
      .temp-studio-frame-body, .lab-frame-body, .perf-studio-answer,
      .compare-pane .body, .md {
        font-size: 15px !important;
        line-height: 1.5 !important;
      }
      .models-float--studio {
        max-height: min(90vh, 940px) !important;
        height: min(90vh, 940px) !important;
      }
      .temp-studio-frame-body {
        max-height: 22rem !important;
        overflow: auto !important;
      }
      .perf-studio-answer {
        max-height: 22rem !important;
        overflow: auto !important;
        white-space: pre-wrap !important;
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

async function selectOptionContaining(select, needle) {
  const options = await select.locator("option").all();
  for (const opt of options) {
    const value = await opt.getAttribute("value");
    const label = (await opt.innerText()).trim();
    if (
      value === needle ||
      label === needle ||
      (value && value.includes(needle)) ||
      label.includes(needle)
    ) {
      await select.selectOption(value ?? needle);
      return true;
    }
  }
  // Fallback: try exact value
  try {
    await select.selectOption(needle);
    return true;
  } catch {
    console.warn("option not found:", needle);
    return false;
  }
}

async function waitFramesOk(page, { minChars = 80, timeout = 300_000 } = {}) {
  await page.waitForFunction(
    ({ minChars: min }) => {
      const frames = [...document.querySelectorAll(".temp-studio-frame")];
      if (frames.length < 3) return false;
      const bodyText = document.body?.innerText || "";
      if (bodyText.includes("/3 ответа")) return false;
      for (const frame of frames) {
        if (frame.querySelector(".compare-error")) return false;
        const text = (frame.innerText || "").replace(/\s+/g, " ").trim();
        // Header alone is short — need answer body
        if (text.length < min) return false;
      }
      return true;
    },
    { minChars },
    { timeout },
  );
}

async function waitStudioCardsOk(page, { minChars = 60, timeout = 300_000 } = {}) {
  await page.waitForFunction(
    ({ minChars: min }) => {
      const cards = [...document.querySelectorAll(".perf-studio-card")];
      if (cards.length < 3) return false;
      const bodyText = document.body?.innerText || "";
      if (/\d\/3/.test(bodyText) && bodyText.includes("Ждём")) return false;
      for (const card of cards) {
        if (card.querySelector(".compare-error")) return false;
        const t = card.innerText || "";
        if (t.includes("Ждём") || card.querySelector(".spinner")) return false;
        const answer = card.querySelector(".perf-studio-answer");
        const answerLen = (answer?.textContent || "").trim().length;
        const hasToggle = !!card.querySelector(".perf-studio-toggle");
        // Toggle appears only after content — treat as ready; else need answer text
        if (hasToggle || answerLen >= min) continue;
        return false;
      }
      return true;
    },
    { minChars },
    { timeout },
  );
}

async function challenge04(page) {
  await page.goto(BASE + "/", { waitUntil: "networkidle", timeout: 90_000 });
  await bumpReadability(page, 1.2);
  await settle(page, 1200);

  await page.getByRole("button", { name: /×T|Темп/i }).first().click();
  await settle(page, 800);

  // Pin stable model for all three temps
  const modelSelect = page.locator(".composer-model-select").first();
  await selectOptionContaining(modelSelect, TEMP_MODEL);
  await settle(page, 600);

  // Day-4 preset if present
  const preset = page.locator(".composer-temp-preset select, .composer-temp-preset .composer-model-select");
  if ((await preset.count()) > 0) {
    await selectOptionContaining(preset.first(), "0 · 0.7 · 1.2").catch(() => {});
  }

  const box = page.locator("textarea").last();
  await box.fill(PROMPT);
  await settle(page, 1000);
  await page.getByRole("button", { name: /Отправить|Send/i }).click();

  await page.getByRole("heading", { name: "Студия температуры" }).waitFor({ timeout: 60_000 });
  console.log("04: waiting for three healthy answers…");
  await waitFramesOk(page);
  await settle(page, 1500);

  // Prefer verdict, but don't fail the take if judge errors — answers are enough
  await page
    .waitForFunction(() => (document.body?.innerText || "").includes("Выводы"), {
      timeout: 120_000,
    })
    .catch(() => console.warn("04: no Выводы yet — continuing with answers"));

  const frames = page.locator(".temp-studio-frame");
  const n = await frames.count();
  for (let i = 0; i < n; i++) {
    // Jump via nav pills so the frame lands under the sticky header
    const pill = page.locator(".temp-studio-pill").nth(i);
    if ((await pill.count()) > 0) {
      await pill.click();
      await settle(page, 800);
    }
    const frame = frames.nth(i);
    await frame.scrollIntoViewIfNeeded();
    await settle(page, 2000);
    // Reject if this frame errored
    if ((await frame.locator(".compare-error").count()) > 0) {
      throw new Error(`temp frame ${i} still has error`);
    }
    const body = frame.locator(".temp-studio-frame-body, .compare-pane .body, .md").first();
    if ((await body.count()) > 0) {
      await body.evaluate((el) => {
        el.scrollTop = 0;
      });
      await settle(page, 2000);
      await body.evaluate((el) => {
        el.scrollTop = Math.min(el.scrollHeight, 320);
      });
      await settle(page, 3500);
      await body.evaluate((el) => {
        el.scrollTop = el.scrollHeight;
      });
      await settle(page, 2500);
    } else {
      await settle(page, 4000);
    }
  }

  const verdict = page.locator(".temp-studio-verdict");
  if ((await verdict.count()) > 0) {
    await verdict.first().scrollIntoViewIfNeeded();
    await settle(page, 6000);
  }
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
  await settle(page, 1000);

  // Pin tiers to stable models
  for (const [tier, model] of Object.entries(TIER_MODELS)) {
    const label =
      tier === "weak" ? "Слабая" : tier === "mid" ? "Средняя" : "Сильная";
    const select = page.getByLabel(`Модель: ${label}`);
    await selectOptionContaining(select, model);
    await settle(page, 300);
  }
  console.log("05: picks", TIER_MODELS);

  await page.locator(".perf-studio-textarea").fill(PROMPT);
  await settle(page, 800);
  await page.getByRole("button", { name: /Запустить сравнение/i }).click();

  console.log("05: waiting for three healthy cards…");
  await waitStudioCardsOk(page);
  await settle(page, 1500);

  // Wait for verdict block if it appears
  await page
    .locator(".perf-studio-verdict")
    .waitFor({ timeout: 120_000 })
    .catch(() => console.warn("05: no verdict block — continuing"));

  const cards = page.locator(".perf-studio-card");
  const n = await cards.count();
  for (let i = 0; i < n; i++) {
    const card = cards.nth(i);
    await card.scrollIntoViewIfNeeded();
    if ((await card.locator(".compare-error").count()) > 0) {
      throw new Error(`studio card ${i} has error`);
    }
    const show = card.getByRole("button", { name: /Показать ответ/i });
    if ((await show.count()) > 0) {
      await show.click();
      await settle(page, 1000);
    }
    const answer = card.locator(".perf-studio-answer");
    if ((await answer.count()) > 0) {
      await answer.evaluate((el) => {
        el.scrollTop = 0;
      });
      await settle(page, 2500);
      await answer.evaluate((el) => {
        el.scrollTop = Math.min(el.scrollHeight, 280);
      });
      await settle(page, 3500);
      await answer.evaluate((el) => {
        el.scrollTop = el.scrollHeight;
      });
      await settle(page, 2500);
    } else {
      await settle(page, 3500);
    }
  }

  const verdict = page.locator(".perf-studio-verdict");
  if ((await verdict.count()) > 0) {
    await verdict.first().scrollIntoViewIfNeeded();
    await settle(page, 6000);
  }
  await settle(page, 2000);
}

const out04 = path.join(__dirname, "../04-temperature/challenge-04.webm");
const out05 = path.join(__dirname, "../05-model-tiers/challenge-05.webm");

async function withRetries(label, fn, attempts = 2) {
  let last;
  for (let i = 1; i <= attempts; i++) {
    try {
      console.log(`${label}: attempt ${i}/${attempts}`);
      await fn();
      return;
    } catch (err) {
      last = err;
      console.error(`${label}: attempt ${i} failed:`, err?.message || err);
      if (i < attempts) await new Promise((r) => setTimeout(r, 3000));
    }
  }
  throw last;
}

const ONLY = (process.env.RECORD_ONLY || "04,05")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

if (ONLY.includes("04")) {
  console.log("Recording challenge 04 against", BASE, "model=", TEMP_MODEL);
  await withVideo(out04, (page) => withRetries("04", () => challenge04(page)));
}
if (ONLY.includes("05")) {
  console.log("Recording challenge 05 against", BASE);
  await withVideo(out05, (page) => withRetries("05", () => challenge05(page)));
}
console.log("done");
