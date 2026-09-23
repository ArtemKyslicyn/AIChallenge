/**
 * Record the local Stand Pulse CLI (real stdio MCP calls) as a terminal video.
 */
import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "../..");
const CLIENT = path.resolve(ROOT, "../stand-pulse");
const MCP_SRC = path.join(ROOT, "apps/mcp/src");
const OUT_WEBM = path.join(__dirname, "../17-mcp-tool/stand-pulse-cli.webm");
const CLIENT_WEBM = path.join(CLIENT, "demo.webm");

function runPulse(args, extraEnv = {}) {
  const dataDir = extraEnv.MCP_DATA_DIR;
  const env = {
    ...process.env,
    AICHALLENGE_MCP_SRC: MCP_SRC,
    MCP_TRANSPORT: "stdio",
    ...extraEnv,
  };
  if (dataDir) env.MCP_DATA_DIR = dataDir;
  const result = spawnSync("uv", ["run", "pulse", "--stdio", ...args], {
    cwd: CLIENT,
    env,
    encoding: "utf8",
    timeout: 45_000,
  });
  const stdout = (result.stdout || "").trim();
  const stderr = (result.stderr || "").trim();
  const body = [stdout, stderr && result.status !== 0 ? stderr : ""]
    .filter(Boolean)
    .join("\n");
  return body || `(exit ${result.status})`;
}

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

const HTML = `<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<title>stand-pulse CLI</title>
<style>
  html, body { margin: 0; height: 100%; background: #0b1220; }
  .term {
    box-sizing: border-box;
    height: 100%;
    padding: 28px 32px 36px;
    font: 18px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace;
    color: #e7eefc;
  }
  .bar { color: #8fb4ff; font-weight: 700; margin-bottom: 18px; letter-spacing: 0.02em; }
  .cmd { color: #7dffb3; white-space: pre-wrap; }
  .out { color: #d5deee; white-space: pre-wrap; margin: 0 0 22px; }
  .prompt { color: #6b7c99; }
</style>
</head>
<body>
  <div class="term">
    <div class="bar">stand-pulse · local MCP client · stdio</div>
    <div id="log"></div>
  </div>
</body>
</html>`;

async function typeLine(page, text, delay = 28) {
  for (const ch of text) {
    await page.evaluate((c) => {
      const el = document.getElementById("log");
      el.lastElementChild.textContent += c;
    }, ch);
    await page.waitForTimeout(delay);
  }
}

async function main() {
  const sync = spawnSync("uv", ["sync"], { cwd: CLIENT, encoding: "utf8" });
  if (sync.status !== 0) {
    console.error(sync.stderr || sync.stdout);
    throw new Error("uv sync failed in stand-pulse");
  }

  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "pulse-cli-"));
  const scenes = [
    {
      cmd: "pulse --stdio list",
      out: runPulse(["list"], { MCP_DATA_DIR: dataDir, STAND_API_URL: "http://127.0.0.1:9" }),
    },
    {
      cmd: "pulse --stdio watch",
      out: runPulse(["watch"], { MCP_DATA_DIR: dataDir, STAND_API_URL: "http://127.0.0.1:9" }),
    },
    {
      cmd: "pulse --stdio watch   # стенд снова жив",
      out: runPulse(["watch"], {
        MCP_DATA_DIR: dataDir,
        STAND_API_URL: process.env.STAND_API_URL || "http://127.0.0.1:8000",
      }),
    },
    {
      cmd: "pulse --stdio schedule --every 60 --note night-watch",
      out: runPulse(["schedule", "--every", "60", "--note", "night-watch"], {
        MCP_DATA_DIR: dataDir,
        STAND_API_URL: process.env.STAND_API_URL || "http://127.0.0.1:8000",
      }),
    },
  ];

  fs.mkdirSync(path.dirname(OUT_WEBM), { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: { dir: path.dirname(OUT_WEBM), size: { width: 1440, height: 900 } },
  });
  const page = await context.newPage();
  await page.setContent(HTML);
  await page.waitForTimeout(600);

  for (const scene of scenes) {
    await page.evaluate(() => {
      const log = document.getElementById("log");
      const p = document.createElement("div");
      p.className = "cmd";
      p.innerHTML = '<span class="prompt">$ </span>';
      log.appendChild(p);
    });
    await typeLine(page, scene.cmd);
    await page.waitForTimeout(350);
    await page.evaluate((text) => {
      const pre = document.createElement("pre");
      pre.className = "out";
      pre.textContent = text;
      document.getElementById("log").appendChild(pre);
    }, scene.out);
    await page.waitForTimeout(2200);
  }
  await page.waitForTimeout(1600);
  const video = page.video();
  await page.close();
  const tmp = await video.path();
  await context.close();
  await browser.close();
  fs.copyFileSync(tmp, OUT_WEBM);
  fs.copyFileSync(tmp, CLIENT_WEBM);
  try {
    fs.unlinkSync(tmp);
  } catch {
    /* ignore */
  }
  console.log("wrote", OUT_WEBM);
  toMp4(OUT_WEBM);
  toMp4(CLIENT_WEBM);
}

await main();
