/**
 * Record challenges 04–07 against prod.
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
      .temp-studio-frame, .lab-frame, .perf-studio-card,
      .agent-log-line--assistant, .agent-team-event--reply {
        box-shadow: 0 0 0 2px rgba(234, 88, 12, 0.35) !important;
      }
      .temp-studio-frame-body, .lab-frame-body, .perf-studio-answer,
      .compare-pane .body, .md, .agent-log-line, .agent-team-event p {
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
      .agent-log, .agent-team-log {
        max-height: min(48vh, 520px) !important;
      }
    `,
  });
}

async function acceptDialogs(page) {
  page.on("dialog", (d) => d.accept().catch(() => {}));
}

async function waitAgentAssistant(page, { minChars = 8, timeout = 180_000 } = {}) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const snap = await page.evaluate(({ minChars: min }) => {
      const status = [...document.querySelectorAll(".agent-status")]
        .map((el) => el.textContent || "")
        .join(" ");
      const lines = [...document.querySelectorAll(".agent-log-line--assistant")];
      const last = lines[lines.length - 1];
      const text = (last?.textContent || "").trim();
      const badge = last?.querySelector(".badge");
      const err =
        /не удалось|unreadable|ошибка|rate limit|слишком много/i.test(status + " " + text);
      if (err) return { ok: false, err: status || text.slice(0, 160) };
      if (text.length >= min && badge && (badge.textContent || "").trim()) return { ok: true };
      if (text.length >= Math.max(min, 60)) return { ok: true };
      return { ok: false };
    }, { minChars });
    if (snap.ok) return;
    if (snap.err) throw new Error(`agent answer failed: ${snap.err}`);
    await settle(page, 1000);
  }
  throw new Error("waitAgentAssistant timeout");
}

/** Wait until a *new* assistant line appears (avoids accepting the previous short «ок»). */
async function waitAgentAssistantAfter(page, prevCount, opts = {}) {
  const { minChars = 8, timeout = 180_000 } = opts;
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const n = await page.locator(".agent-log-line--assistant").count();
    if (n > prevCount) {
      await waitAgentAssistant(page, { minChars, timeout: Math.max(5_000, deadline - Date.now()) });
      return;
    }
    const status = await page.locator(".agent-status").allTextContents().catch(() => []);
    const joined = status.join(" ");
    if (/не удалось|unreadable|ошибка|rate limit|слишком много/i.test(joined)) {
      throw new Error(`agent answer failed: ${joined.slice(0, 160)}`);
    }
    await settle(page, 800);
  }
  throw new Error("waitAgentAssistantAfter timeout");
}

async function sendSoloAndWait(page, text, { minChars = 8, timeout = 180_000 } = {}) {
  const prev = await page.locator(".agent-log-line--assistant").count();
  await page.locator(".agent-compose textarea").first().fill(text);
  await settle(page, 700);
  await page.locator(".agent-workshop--solo .agent-send-btn").click();
  await waitAgentAssistantAfter(page, prev, { minChars, timeout });
}

async function waitTeamAnswers(page, { minAnswers = 2, timeout = 300_000 } = {}) {
  await page.waitForFunction(
    ({ minAnswers: min }) => {
      const ok = [...document.querySelectorAll(".agent-team-event--reply")].filter((el) => {
        const text = (el.querySelector("p")?.textContent || "").trim();
        const badge = el.querySelector(".badge");
        return text.length > 8 && Boolean(badge);
      });
      if (ok.length >= min) return true;
      const send = document.querySelector(".agent-team-form .agent-send-btn");
      const busy = (send?.textContent || "").includes("Стоп");
      // Idle with at least one reply — accept partial team runs (rate limits etc.)
      return !busy && ok.length >= 1;
    },
    { minAnswers },
    { timeout },
  );
}

async function pauseOn(locator, ms = 3500) {
  if ((await locator.count()) > 0) {
    await locator.first().scrollIntoViewIfNeeded();
    await settle(locator.page(), ms);
  }
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
        console.warn("discarded failed take", tmp);
      }
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

const AGENT_STRONG = process.env.CHALLENGE_AGENT_MODEL || "google/gemini-2.5-flash";

const STRING_THEORY_CAST = [
  {
    name: "Алкаш",
    system:
      "Ты Алкаш — простой парень из бара. Говоришь коротко, по-житейски, с лёгкой иронией. " +
      "Сложные темы (типа теории струн) объясняешь через пиво, гитарные струны и «ну всё типа вибрирует». " +
      "Без жёсткого мата. Ответ: 2–4 предложения, оставайся в роли.",
    temperature: "0.9",
    maxTokens: "400",
  },
  {
    name: "Аристотель",
    system:
      "Ты Аристотель. Говоришь торжественно, ясно, через причины и категории (форма, материя, цель). " +
      "Теорию струн связываешь с идеей первооснов мира, но без псевдонаучного бреда. " +
      "Ответ: 3–5 предложений, оставайся в роли.",
    temperature: "0.5",
    maxTokens: "500",
  },
  {
    name: "Программист",
    system:
      "Ты сеньор-программист. Объясняешь физику аналогиями из кода и инженерии: " +
      "волны, спектры, размерности как слои абстракции, «модель vs реализация». " +
      "Чётко, без воды. Ответ: 3–5 предложений, оставайся в роли.",
    temperature: "0.4",
    maxTokens: "500",
  },
];

const TEAM_TOPIC =
  "Обсудите теорию струн: что это такое простыми словами и зачем она физикам. Каждый — в своём характере, коротко (2–5 предложений).";

async function fillActiveBuilder(page, persona) {
  const builder = page.locator(".agent-workshop-builder .agent-builder, .agent-builder").first();
  await builder.waitFor({ timeout: 15_000 });
  const nameInput = builder.locator("label.agent-field").filter({ hasText: /^Имя/ }).locator("input");
  await nameInput.fill(persona.name);
  await settle(page, 400);
  const instr = builder
    .locator("label.agent-field")
    .filter({ hasText: /Инструкция/ })
    .locator("textarea");
  await instr.fill(persona.system);
  await settle(page, 400);
  const modelSelect = builder.locator("fieldset.agent-how select").first();
  await selectOptionContaining(modelSelect, AGENT_STRONG);
  await settle(page, 300);
  const temp = builder.locator("label.agent-field").filter({ hasText: /^Temp/ }).locator("input");
  if ((await temp.count()) > 0) {
    await temp.fill(persona.temperature);
  }
  const maxTok = builder
    .locator("label.agent-field")
    .filter({ hasText: /Max tokens/i })
    .locator("input");
  if ((await maxTok.count()) > 0) {
    await maxTok.fill(persona.maxTokens);
  }
  await settle(page, 600);
}

/** Prefer preset chip; otherwise +Пустой and fill definition (works without redeploy). */
async function ensurePersona(page, persona) {
  const chip = page.getByRole("button", { name: new RegExp(`\\+?\\s*${persona.name}`, "i") });
  if ((await chip.count()) > 0) {
    await chip.first().click();
    await settle(page, 900);
    // Pin strong model even if preset already set
    await fillActiveBuilder(page, persona).catch(() => {});
    return;
  }
  await page.getByRole("button", { name: /\+?\s*Пустой/i }).first().click();
  await settle(page, 900);
  await fillActiveBuilder(page, persona);
}

async function selectTeamAll(page) {
  const checks = page.locator(".agent-rail-check input[type=checkbox]");
  const n = await checks.count();
  for (let i = 0; i < n; i++) {
    const c = checks.nth(i);
    if (!(await c.isChecked())) {
      await c.check().catch(() => {});
      await settle(page, 250);
    }
  }
}

/** Check agents in given name order (for chain handoff). */
async function selectTeamByNames(page, names) {
  const items = page.locator(".agent-rail-list > li");
  const count = await items.count();
  // Clear selection
  for (let i = 0; i < count; i++) {
    const box = items.nth(i).locator("input[type=checkbox]");
    if ((await box.count()) && (await box.isChecked())) {
      await box.uncheck().catch(() => {});
      await settle(page, 200);
    }
  }
  for (const name of names) {
    for (let i = 0; i < count; i++) {
      const li = items.nth(i);
      const label = await li.locator(".agent-rail-name").innerText().catch(() => "");
      if (new RegExp(name, "i").test(label)) {
        const box = li.locator("input[type=checkbox]");
        if (!(await box.isChecked())) {
          await box.check();
          await settle(page, 300);
        }
        break;
      }
    }
  }
}

async function setFanIn(page, on) {
  const box = page.locator(".agent-fanin-toggle input[type=checkbox]");
  if ((await box.count()) === 0) return;
  const checked = await box.first().isChecked();
  if (checked !== on) {
    await box.first().setChecked(on);
    await settle(page, 400);
  }
}

async function runTeamMode(page, modeLabel, task, { minAnswers = 2, fanIn = true, names = null } = {}) {
  await page.getByRole("button", { name: new RegExp(modeLabel, "i") }).first().click();
  await settle(page, 1200);
  if (names?.length) {
    await selectTeamByNames(page, names);
  } else {
    await selectTeamAll(page);
  }
  await setFanIn(page, fanIn);
  await pauseOn(page.locator(".agent-team"), 2000);
  const teamBox = page.locator(".agent-team-form textarea");
  await teamBox.fill(task);
  await settle(page, 1000);
  await page.locator(".agent-team-form .agent-send-btn").click();
  console.log(`06: team ${modeLabel} — waiting…`);
  await waitTeamAnswers(page, { minAnswers, timeout: 360_000 });
  await settle(page, 1500);
  const replies = page.locator(".agent-team-event--reply");
  const n = await replies.count();
  for (let i = Math.max(0, n - Math.min(n, 5)); i < n; i++) {
    await pauseOn(replies.nth(i), 3200);
  }
}

async function challenge06(page) {
  const soloAsk =
    fs.readFileSync(path.join(__dirname, "../06-first-agent/prompt.txt"), "utf8").trim() ||
    TEAM_TOPIC;
  acceptDialogs(page);
  await page.goto(BASE + "/?shell=agents", { waitUntil: "networkidle", timeout: 90_000 });
  await bumpReadability(page, 1.1);
  await settle(page, 1600);

  await page.getByRole("heading", { name: /^Агенты$/i }).waitFor({ timeout: 30_000 });
  await page.getByRole("button", { name: /Один агент/i }).click();
  await settle(page, 1000);

  console.log("06: create cast — Алкаш, Аристотель, Программист @", AGENT_STRONG);
  for (const persona of STRING_THEORY_CAST) {
    await ensurePersona(page, persona);
    await pauseOn(page.locator(".agent-builder").first(), 2200);
  }

  // Solo: Аристотель explains string theory
  await page.locator(".agent-rail-item").filter({ hasText: /Аристотель/i }).first().click();
  await settle(page, 800);
  await pauseOn(page.locator(".agent-builder").first(), 2500);

  const box = page.locator(".agent-compose textarea").first();
  await box.fill(
    "Кейс · Один агент: в трёх предложениях объясни теорию струн так, будто слушатель умный, но не физик.",
  );
  await settle(page, 1200);
  await page.locator(".agent-workshop--solo .agent-send-btn").click();
  console.log("06: solo Аристотель…");
  await waitAgentAssistant(page, { minChars: 40, timeout: 240_000 });
  await pauseOn(page.locator(".agent-log-line--assistant").last(), 5500);

  // Team modes with the same clear topic
  await page.getByRole("button", { name: /^Команда$/i }).click();
  await settle(page, 1400);
  const castNames = STRING_THEORY_CAST.map((p) => p.name);
  await selectTeamByNames(page, castNames);
  await pauseOn(page.locator(".agent-team-roster"), 2500);

  await runTeamMode(page, "Параллельно", `Кейс · Параллельно.\n${TEAM_TOPIC}`, {
    minAnswers: 2,
    fanIn: true,
    names: castNames,
  });

  await runTeamMode(
    page,
    "Цепочка",
    `Кейс · Цепочка (Алкаш → Аристотель → Программист).\n${TEAM_TOPIC}\nКаждый улучшает мысль предыдущего.`,
    { minAnswers: 2, fanIn: false, names: castNames },
  );

  await runTeamMode(
    page,
    "Обсуждение",
    `Кейс · Обсуждение / roundtable.\n${TEAM_TOPIC}\nПотом коротко покритикуйте друг друга.`,
    { minAnswers: 2, fanIn: true, names: castNames },
  );

  await page.getByRole("button", { name: /Прогон/i }).first().click();
  await settle(page, 1000);
  // Прогон: один базовый — Аристотель
  await selectTeamByNames(page, ["Аристотель"]);
  await pauseOn(page.locator(".agent-progon-controls"), 2800);
  await setFanIn(page, true);
  await page
    .locator(".agent-team-form textarea")
    .fill(
      `/прогон Кейс · Прогон temperature: одним абзацем — что такое теория струн и зачем она нужна.`,
    );
  await settle(page, 1000);
  await page.locator(".agent-team-form .agent-send-btn").click();
  console.log("06: progon…");
  await waitTeamAnswers(page, { minAnswers: 2, timeout: 360_000 });
  const progonReplies = page.locator(".agent-team-event--reply");
  const pn = await progonReplies.count();
  for (let i = Math.max(0, pn - 5); i < pn; i++) {
    await pauseOn(progonReplies.nth(i), 3000);
  }
  await settle(page, 2000);
}

async function challenge07(page) {
  acceptDialogs(page);
  await page.goto(BASE + "/?shell=agents", { waitUntil: "networkidle", timeout: 90_000 });
  await bumpReadability(page, 1.1);
  await settle(page, 1600);

  await page.getByRole("heading", { name: /^Агенты$/i }).waitFor({ timeout: 30_000 });
  await page.getByRole("button", { name: /Один агент/i }).click();
  await settle(page, 900);

  // Dedicated memory tester agent
  await ensurePersona(page, {
    name: "Тестер памяти",
    system:
      "Ты тестовый агент памяти (День 7). Кратко подтверждай факты о пользователе. " +
      "Когда просят формат ответа — соблюдай его буквально, без лишнего текста.",
    temperature: "0.2",
    maxTokens: "256",
  });
  await pauseOn(page.locator(".agent-builder").first(), 2800);

  const clearBtn = page.getByRole("button", { name: /Очистить лог/i });
  if ((await clearBtn.count()) > 0) {
    await clearBtn.first().click();
    await settle(page, 1000);
  }

  const intro =
    fs.readFileSync(path.join(__dirname, "../07-context-memory/prompt.txt"), "utf8").trim() ||
    "Меня зовут Артем. Любимый язык — Python.";

  console.log("07: A — store Артем + Python…");
  await page.locator(".agent-compose textarea").first().fill(intro);
  await settle(page, 1400);
  await page.locator(".agent-workshop--solo .agent-send-btn").click();
  await waitAgentAssistant(page, { minChars: 10, timeout: 240_000 });
  await pauseOn(page.locator(".agent-log-line--user").last(), 3500);
  await pauseOn(page.locator(".agent-log-line--assistant").last(), 5000);

  console.log("07: B — reload (restart)…");
  await page.reload({ waitUntil: "networkidle", timeout: 90_000 });
  await bumpReadability(page, 1.1);
  await settle(page, 2000);
  await page.getByRole("heading", { name: /^Агенты$/i }).waitFor({ timeout: 30_000 });
  await page.getByRole("button", { name: /Один агент/i }).click();
  await settle(page, 1200);

  await page.waitForFunction(
    () => {
      const users = [...document.querySelectorAll(".agent-log-line--user")];
      return users.some((el) => /Артем|Python/i.test(el.textContent || ""));
    },
    { timeout: 60_000 },
  );
  await pauseOn(
    page.locator(".agent-log-line--user").filter({ hasText: /Артем|Python/i }).first(),
    4000,
  );

  const recall =
    "Кейс B · после перезапуска. Ответь ровно двумя строками:\nИмя: <только имя>\nЯзык: <только язык>";
  await page.locator(".agent-compose textarea").first().fill(recall);
  await settle(page, 1200);
  await page.locator(".agent-workshop--solo .agent-send-btn").click();
  console.log("07: B — recall…");
  await waitAgentAssistant(page, { minChars: 5, timeout: 240_000 });
  const last = page.locator(".agent-log-line--assistant").last();
  const text = await last.innerText();
  if (!/артем/i.test(text) || !/python/i.test(text)) {
    throw new Error(`07 B fail — expected Артем+Python in: ${text.slice(0, 240)}`);
  }
  await pauseOn(last, 6500);

  console.log("07: C — clear wipes memory…");
  await page.getByRole("button", { name: /Очистить лог/i }).first().click();
  await settle(page, 2000);
  await pauseOn(page.locator(".agent-log-empty, .agent-log").first(), 3000);

  await page
    .locator(".agent-compose textarea")
    .first()
    .fill("Кейс C · после очистки. Как меня зовут? Если не знаешь из истории — скажи «не знаю».");
  await settle(page, 1000);
  await page.locator(".agent-workshop--solo .agent-send-btn").click();
  await waitAgentAssistant(page, { minChars: 3, timeout: 180_000 });
  await pauseOn(page.locator(".agent-log-line--assistant").last(), 5000);
  await settle(page, 2000);
}

async function challenge08(page) {
  acceptDialogs(page);
  await page.goto(BASE + "/?shell=agents", { waitUntil: "networkidle", timeout: 90_000 });
  await bumpReadability(page, 1.1);
  await settle(page, 1600);

  await page.getByRole("heading", { name: /^Агенты$/i }).waitFor({ timeout: 30_000 });
  await page.getByRole("button", { name: /Один агент/i }).click();
  await settle(page, 900);

  await ensurePersona(page, {
    name: "Токен-метр",
    system:
      "Ты агент учёта токенов. Отвечай коротко (1–3 предложения), без списков.",
    temperature: "0.2",
    maxTokens: "160",
  });
  await pauseOn(page.locator(".agent-builder").first(), 2200);

  const clearBtn = page.getByRole("button", { name: /Очистить лог/i });
  if ((await clearBtn.count()) > 0) {
    await clearBtn.first().click();
    await settle(page, 800);
  }

  // Default limit — short dialog
  console.log("08: A short…");
  await page.locator(".agent-compose textarea").first().fill(
    "Кейс A · короткий: что такое токен в LLM? Одним предложением.",
  );
  await settle(page, 1000);
  await page.locator(".agent-workshop--solo .agent-send-btn").click();
  await waitAgentAssistant(page, { minChars: 10, timeout: 180_000 });
  await pauseOn(page.locator(".agent-token-meter").last(), 4500);

  // Grow history
  console.log("08: B long…");
  const fat = "яблоко ".repeat(40);
  for (let i = 1; i <= 4; i++) {
    await page
      .locator(".agent-compose textarea")
      .first()
      .fill(`Кейс B · блок ${i}: запомни «${fat}». Подтверди номер ${i}.`);
    await settle(page, 700);
    await page.locator(".agent-workshop--solo .agent-send-btn").click();
    await waitAgentAssistant(page, { minChars: 5, timeout: 180_000 });
    await pauseOn(page.locator(".agent-token-meter").last(), 2800);
  }

  // Overflow — force React-controlled input update
  console.log("08: C overflow…");
  const limitInput = page.locator(".agent-context-limit input");
  await limitInput.click();
  await limitInput.fill("120");
  await settle(page, 400);
  await page.waitForFunction(() => {
    const el = document.querySelector(".agent-context-limit input");
    return el instanceof HTMLInputElement && el.value === "120";
  });
  await pauseOn(limitInput, 2000);
  await page
    .locator(".agent-compose textarea")
    .first()
    .fill(
      "Кейс C · переполнение: что было в блоке 1? Если контекст обрезан — скажи об этом прямо.",
    );
  await settle(page, 900);
  await page.locator(".agent-workshop--solo .agent-send-btn").click();
  await waitAgentAssistant(page, { minChars: 5, timeout: 180_000 });
  await page.waitForFunction(
    () => {
      const trunc = document.querySelector(".agent-token-trunc");
      if (trunc) return true;
      const meters = [...document.querySelectorAll(".agent-token-meter")];
      const last = meters[meters.length - 1];
      return last && /←|обрезан/i.test(last.textContent || "");
    },
    { timeout: 60_000 },
  );
  await pauseOn(page.locator(".agent-token-meter").last(), 5500);
  await settle(page, 2000);
}

async function challenge09(page) {
  acceptDialogs(page);
  await page.goto(BASE + "/?shell=agents", { waitUntil: "networkidle", timeout: 90_000 });
  await bumpReadability(page, 1.1);
  await settle(page, 1600);

  await page.getByRole("heading", { name: /^Агенты$/i }).waitFor({ timeout: 30_000 });
  await page.getByRole("button", { name: /Один агент/i }).click();
  await settle(page, 900);

  await ensurePersona(page, {
    name: "Компрессия",
    system:
      "Ты ассистент с памятью фактов. Отвечай коротко (1–3 предложения). " +
      "Если спрашивают имя или язык — используй факты из диалога или сводки.",
    temperature: "0.2",
    maxTokens: "120",
  });
  await pauseOn(page.locator(".agent-builder").first(), 2000);

  const clearBtn = page.getByRole("button", { name: /Очистить лог/i });
  if ((await clearBtn.count()) > 0) {
    await clearBtn.first().click();
    await settle(page, 800);
  }

  // Ensure compress is OFF for case A
  const compressToggle = page.locator(".agent-compress-toggle input[type=checkbox]");
  await compressToggle.waitFor({ timeout: 15_000 });
  if (await compressToggle.isChecked()) {
    await compressToggle.uncheck();
    await settle(page, 400);
  }
  await pauseOn(page.locator(".agent-compress-toggle"), 2200);

  const facts = [
    "Меня зовут Артем.",
    "Любимый язык — Python.",
    "Работаю в AIChallenge.",
    "Любимый цвет — синий.",
    "Живу у моря.",
    "Пью зелёный чай.",
  ];

  console.log("09: A without compress…");
  for (let i = 0; i < facts.length; i++) {
    await sendSoloAndWait(
      page,
      `Кейс A · факт ${i + 1}: запомни «${facts[i]}». Подтверди «ок».`,
      { minChars: 2, timeout: 180_000 },
    );
    await pauseOn(page.locator(".agent-token-meter").last(), 2200);
  }

  await sendSoloAndWait(
    page,
    "Кейс A · recall без сжатия. Две строки:\nИмя: <имя>\nЯзык: <язык>",
    { minChars: 8, timeout: 180_000 },
  );
  await pauseOn(page.locator(".agent-log-line--assistant").last(), 4500);
  await pauseOn(page.locator(".agent-token-meter").last(), 3500);

  console.log("09: B enable compress + new dialog…");
  await clearBtn.first().click();
  await settle(page, 1000);
  if (!(await compressToggle.isChecked())) {
    await compressToggle.check();
    await settle(page, 400);
  }
  // Demo-friendly thresholds so summary appears after ~6 facts
  const recentInput = page.locator(".agent-compose-tools label").filter({ hasText: /^recent$/i }).locator("input");
  const everyInput = page.locator(".agent-compose-tools label").filter({ hasText: /^every$/i }).locator("input");
  await recentInput.fill("4");
  await everyInput.fill("6");
  await settle(page, 400);
  await pauseOn(page.locator(".agent-compress-toggle"), 2500);

  for (let i = 0; i < facts.length; i++) {
    await sendSoloAndWait(
      page,
      `Кейс B · факт ${i + 1}: запомни «${facts[i]}». Подтверди «ок».`,
      { minChars: 2, timeout: 180_000 },
    );
    const compressMeter = page.locator(".agent-token-compress").last();
    if ((await compressMeter.count()) > 0) {
      await pauseOn(compressMeter, 2800);
    } else {
      await pauseOn(page.locator(".agent-token-meter").last(), 2000);
    }
  }

  // Wait for summary panel if present
  const summary = page.locator(".agent-summary-panel");
  if ((await summary.count()) > 0) {
    await summary.first().click();
    await settle(page, 600);
    await pauseOn(summary.first(), 4500);
  }

  await sendSoloAndWait(
    page,
    "Кейс B · recall со сжатием. Две строки:\nИмя: <имя>\nЯзык: <язык>",
    { minChars: 8, timeout: 180_000 },
  );
  const last = page.locator(".agent-log-line--assistant").last();
  const text = await last.innerText();
  if (!/артем/i.test(text) || !/python/i.test(text)) {
    throw new Error(`09 B fail — expected Артем+Python in: ${text.slice(0, 240)}`);
  }
  await pauseOn(last, 5000);
  const compressLine = page.locator(".agent-token-compress").last();
  if ((await compressLine.count()) > 0) {
    await pauseOn(compressLine, 4500);
  } else {
    await pauseOn(page.locator(".agent-token-meter").last(), 3500);
  }
  await settle(page, 2000);
}

const out04 = path.join(__dirname, "../04-temperature/challenge-04.webm");
const out05 = path.join(__dirname, "../05-model-tiers/challenge-05.webm");
const out06 = path.join(__dirname, "../06-first-agent/challenge-06.webm");
const out07 = path.join(__dirname, "../07-context-memory/challenge-07.webm");
const out08 = path.join(__dirname, "../08-tokens/challenge-08.webm");
const out09 = path.join(__dirname, "../09-compression/challenge-09.webm");

const ONLY = (process.env.RECORD_ONLY || "04,05,06,07,08,09")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

/** Retry outside withVideo so failed waits do not bloat the take. */
async function recordChallenge(label, outPath, fn, attempts = 2) {
  let last;
  for (let i = 1; i <= attempts; i++) {
    try {
      console.log(`${label}: attempt ${i}/${attempts}`);
      await withVideo(outPath, fn);
      return;
    } catch (err) {
      last = err;
      console.error(`${label}: attempt ${i} failed:`, err?.message || err);
      if (i < attempts) await new Promise((r) => setTimeout(r, 3000));
    }
  }
  throw last;
}

if (ONLY.includes("04")) {
  console.log("Recording challenge 04 against", BASE, "model=", TEMP_MODEL);
  await recordChallenge("04", out04, (page) => challenge04(page));
}
if (ONLY.includes("05")) {
  console.log("Recording challenge 05 against", BASE);
  await recordChallenge("05", out05, (page) => challenge05(page));
}
if (ONLY.includes("06")) {
  console.log("Recording challenge 06 against", BASE);
  await recordChallenge("06", out06, (page) => challenge06(page));
}
if (ONLY.includes("07")) {
  console.log("Recording challenge 07 against", BASE);
  await recordChallenge("07", out07, (page) => challenge07(page));
}
if (ONLY.includes("08")) {
  console.log("Recording challenge 08 against", BASE);
  await recordChallenge("08", out08, (page) => challenge08(page));
}
if (ONLY.includes("09")) {
  console.log("Recording challenge 09 against", BASE);
  await recordChallenge("09", out09, (page) => challenge09(page));
}
console.log("done");
