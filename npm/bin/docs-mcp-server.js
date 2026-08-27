#!/usr/bin/env node
"use strict";

const { spawn, execSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

const HOME = os.homedir();
const STATE_DIR = path.join(HOME, ".fathom-mcp");
const VENV_DIR = path.join(STATE_DIR, "venv");
const SRC_DIR = path.join(STATE_DIR, "src");
const MARKER = path.join(VENV_DIR, ".setup-done");

function log(msg) { process.stderr.write(`fathom: ${msg}\n`); }

function findPython() {
  const candidates = ["python3.14", "python3.13", "python3.12", "python3"];
  for (const bin of candidates) {
    try {
      const out = execSync(`${bin} -c "import sys; print(sys.version_info[:2])"`, { encoding: "utf8" }).trim();
      const [major, minor] = out.replace(/[()]/g, "").split(",").map(Number);
      if (major >= 3 && minor >= 12) return bin;
    } catch {}
  }
  return null;
}

function copySource() {
  const bundled = path.join(__dirname, "..", "python");
  fs.mkdirSync(SRC_DIR, { recursive: true });
  execSync(`cp -a "${bundled}/." "${SRC_DIR}/"`, { stdio: "inherit" });
}

function createVenv(python) {
  fs.mkdirSync(STATE_DIR, { recursive: true });
  log("creating virtual environment...");
  execSync(`${python} -m venv "${VENV_DIR}"`, { stdio: "inherit" });
}

function installDeps() {
  const pip = path.join(VENV_DIR, "bin", "pip");
  log("installing dependencies... this may take a few minutes on first run");
  execSync(`${pip} install --quiet --upgrade pip`, { stdio: "inherit" });
  execSync(`${pip} install --quiet "${SRC_DIR}[local]"`, { stdio: "inherit" });
  const playwright = path.join(VENV_DIR, "bin", "playwright");
  if (fs.existsSync(playwright)) {
    log("installing chromium for web crawler...");
    execSync(`${playwright} install --with-deps chromium 2>/dev/null || true`, { stdio: "inherit" });
  }
  fs.writeFileSync(MARKER, new Date().toISOString());
  log("setup complete");
}

function ensureSetup() {
  if (fs.existsSync(MARKER)) return;
  const python = findPython();
  if (!python) {
    log("error: Python 3.12+ not found. Install Python and try again.");
    log("  https://www.python.org/downloads/");
    process.exit(1);
  }
  log(`first-time setup — using ${python}`);
  createVenv(python);
  copySource();
  installDeps();
}

function ensureConfig() {
  const envFile = path.join(STATE_DIR, ".env");
  if (!fs.existsSync(envFile)) {
    fs.mkdirSync(STATE_DIR, { recursive: true });
    fs.writeFileSync(envFile, [
      "# fathom-mcp configuration",
      "# https://github.com/yourname/fathom-mcp#configuration",
      "",
      "LLM_API_KEY=your-key-here",
      "LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai",
      "LLM_MODEL=gemini-3.6-flash",
      "DATABASE_URL=postgresql://docs_mcp:docs_mcp@localhost:5432/docs_mcp",
      "",
      "# Local embedding model (requires GPU for best performance)",
      "# local_embedding_model=sentence-transformers/all-MiniLM-L6-v2",
    ].join("\n"));
    log(`created config template at ${envFile}`);
    log("edit this file with your API keys before starting the server");
  }
}

function run() {
  ensureSetup();
  ensureConfig();
  const python = path.join(VENV_DIR, "bin", "python");
  const useApi = process.argv.includes("--api");
  const mod = useApi ? "docs_mcp.api" : "docs_mcp.server";
  const child = spawn(python, ["-m", mod], {
    cwd: SRC_DIR,
    stdio: ["inherit", "inherit", "inherit"],
    env: { ...process.env },
  });
  child.on("exit", (code) => process.exit(code ?? 1));
  process.on("SIGINT", () => child.kill("SIGINT"));
  process.on("SIGTERM", () => child.kill("SIGTERM"));
}

run();
