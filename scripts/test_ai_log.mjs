#!/usr/bin/env node
/**
 * Manual test for AI Engineering Log — simulates Cursor hook payloads.
 * Usage: node scripts/test_ai_log.mjs
 */

import { execSync } from "child_process";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const JSONL = path.join(ROOT, "logs", "ai-engineering-log.jsonl");
const WRITER = path.join(ROOT, ".cursor", "hooks", "log_writer.mjs");

function countLines() {
  if (!fs.existsSync(JSONL)) return 0;
  return fs.readFileSync(JSONL, "utf8").split("\n").filter(Boolean).length;
}

function runHook(command, payload) {
  execSync(`node "${WRITER}" ${command}`, {
    input: JSON.stringify(payload),
    cwd: ROOT,
    stdio: ["pipe", "pipe", "pipe"],
    encoding: "utf8",
  });
}

const before = countLines();
console.log(`Events before test: ${before}`);

const tests = [
  {
    name: "User prompt",
    command: "prompt",
    payload: {
      conversation_id: "manual-test-session",
      prompt: "now lets test if this is logged or not",
    },
  },
  {
    name: "Grep search",
    command: "tool_use",
    payload: {
      conversation_id: "manual-test-session",
      tool_name: "Grep",
      tool_input: { pattern: "log_writer", path: ROOT },
      tool_output: "README.md:18:...",
    },
  },
  {
    name: "File read",
    command: "tool_use",
    payload: {
      conversation_id: "manual-test-session",
      tool_name: "Read",
      tool_input: { path: "README.md" },
    },
  },
];

for (const test of tests) {
  runHook(test.command, test.payload);
  console.log(`  + logged: ${test.name}`);
}

const after = countLines();
console.log(`Events after test:  ${after}`);
console.log(`New entries:        ${after - before}`);

if (after > before) {
  console.log("\nPASS — Log writer works. Latest entries:");
  const lines = fs.readFileSync(JSONL, "utf8").split("\n").filter(Boolean);
  for (const line of lines.slice(-3)) {
    const e = JSON.parse(line);
    console.log(`  [${e.event_type}] ${e.summary}`);
  }
} else {
  console.log("\nFAIL — No new entries written.");
  process.exit(1);
}

console.log("\nOpen AI_ENGINEERING_LOG.md to see the readable summary.");
