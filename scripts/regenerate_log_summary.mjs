import { existsSync, readFileSync, writeFileSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, "..");
const JSONL_PATH = path.join(PROJECT_ROOT, "logs", "ai-engineering-log.jsonl");
const MARKDOWN_PATH = path.join(PROJECT_ROOT, "AI_ENGINEERING_LOG.md");

function eventTimeLabel(timestamp) {
  try {
    return new Date(timestamp).toISOString().slice(11, 16);
  } catch {
    return timestamp;
  }
}

function eventDateLabel(timestamp) {
  try {
    return new Date(timestamp).toISOString().slice(0, 10);
  } catch {
    return "Unknown";
  }
}

function formatEventMarkdown(event) {
  const timeLabel = eventTimeLabel(event.timestamp);
  const title = event.event_type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const lines = [`### ${timeLabel} — ${title}`, `- **Summary:** ${event.summary}`];
  const d = event.details || {};

  if (event.event_type === "search") {
    if (d.tool) lines.push(`- **Tool:** ${d.tool}`);
    if (d.query) lines.push(`- **Query:** \`${d.query}\``);
    if (d.path) lines.push(`- **Path:** \`${d.path}\``);
    if (d.match_count != null) lines.push(`- **Results:** ${d.match_count} matches`);
  } else if (event.event_type === "read" && d.file_path) {
    lines.push(`- **File:** \`${d.file_path}\``);
  } else if (event.event_type === "edit" && d.file_path) {
    lines.push(`- **File:** \`${d.file_path}\``);
  } else if (event.event_type === "shell" && d.command) {
    lines.push(`- **Command:** \`${d.command}\``);
  } else if (event.event_type === "prompt" && d.message) {
    lines.push(`- **User:** ${d.message}`);
  }

  return lines.join("\n");
}

const events = existsSync(JSONL_PATH)
  ? readFileSync(JSONL_PATH, "utf8")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line))
  : [];

const now = new Date().toISOString().replace("T", " ").replace(/\.\d+Z$/, " UTC");
const lines = [
  "# AI Engineering Log",
  "",
  "> Auto-generated from `logs/ai-engineering-log.jsonl`. Do not edit manually.",
  `> Last updated: ${now}`,
  "",
];

if (!events.length) {
  lines.push("_No events recorded yet._");
} else {
  const byDate = {};
  for (const event of events) {
    (byDate[eventDateLabel(event.timestamp)] ||= []).push(event);
  }
  for (const date of Object.keys(byDate).sort().reverse()) {
    lines.push(`## ${date}`, "");
    for (const event of byDate[date]) {
      lines.push(formatEventMarkdown(event), "");
    }
  }
}

const counts = {};
for (const event of events) {
  counts[event.event_type] = (counts[event.event_type] || 0) + 1;
}

lines.push(
  "---",
  "",
  "## Statistics",
  "",
  "| Metric | Count |",
  "|--------|-------|",
  `| Total events | ${events.length} |`,
  `| Searches | ${counts.search || 0} |`,
  `| Reads | ${counts.read || 0} |`,
  `| Edits | ${counts.edit || 0} |`,
  `| Shell commands | ${counts.shell || 0} |`,
  `| Prompts | ${counts.prompt || 0} |`,
  ""
);

writeFileSync(MARKDOWN_PATH, lines.join("\n"), "utf8");
console.log("Regenerated AI_ENGINEERING_LOG.md");
