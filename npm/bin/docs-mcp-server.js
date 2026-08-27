#!/usr/bin/env node
"use strict";

const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

function findProjectRoot() {
  // Walk up from this script to find pyproject.toml
  let dir = path.resolve(__dirname, "..", "..");
  for (let i = 0; i < 10; i++) {
    if (fs.existsSync(path.join(dir, "pyproject.toml"))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  // Fallback: try common locations
  const home = process.env.HOME || "";
  const candidates = [
    path.join(home, "Documents", "projects", "mcp-project"),
    path.join(home, "mcp-project"),
  ];
  for (const c of candidates) {
    if (fs.existsSync(path.join(c, "pyproject.toml"))) return c;
  }
  return null;
}

function findPython(projectRoot) {
  const venvPy = path.join(projectRoot, ".venv", "bin", "python");
  if (fs.existsSync(venvPy)) return venvPy;
  return "python3";
}

const root = findProjectRoot();
if (!root) {
  console.error("docs-mcp-server: could not find project root (pyproject.toml)");
  console.error("Set DOCS_RAG_HOME env var to the project directory.");
  process.exit(1);
}

const python = findPython(root);
const child = spawn(python, ["-m", "docs_mcp.server"], {
  cwd: root,
  stdio: ["inherit", "inherit", "inherit"],
  env: { ...process.env },
});

child.on("exit", (code) => process.exit(code ?? 1));
process.on("SIGINT", () => child.kill("SIGINT"));
process.on("SIGTERM", () => child.kill("SIGTERM"));
