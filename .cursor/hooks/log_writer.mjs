import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, "../..");
const JSONL_PATH = path.join(PROJECT_ROOT, "logs", "ai-engineering-log.jsonl");
const MARKDOWN_PATH = path.join(PROJECT_ROOT, "AI_ENGINEERING_LOG.md");
const SESSION_STATE_PATH = path.join(__dirname, ".session_state.json");
const MAX_TEXT_LENGTH = 500;

const REDACTION_PATTERNS = [
  [/sk-[a-zA-Z0-9]{20,}/g, "sk-[REDACTED]"],
  [/Bearer\s+[A-Za-z0-9\-._~+/]+=*/gi, "Bearer [REDACTED]"],
  [/(password|passwd|secret|token|api_key|apikey)\s*=\s*\S+/gi, "$1=[REDACTED]"],
  [/(password|passwd|secret|token|api_key|apikey)\s*:\s*\S+/gi, "$1: [REDACTED]"],
];

function utcNowIso() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, (m) => m.slice(0, 4) + "Z");
}

function generateEventId() {
  const now = new Date();
  const pad = (n, w = 2) => String(n).padStart(w, "0");
  return `evt_${now.getUTCFullYear()}${pad(now.getUTCMonth() + 1)}${pad(now.getUTCDate())}_${pad(now.getUTCHours())}${pad(now.getUTCMinutes())}${pad(now.getUTCSeconds())}_${pad(now.getUTCMilliseconds(), 3)}000`;
}

function truncateText(text, limit = MAX_TEXT_LENGTH) {
  const trimmed = String(text || "").trim();
  if (trimmed.length <= limit) return trimmed;
  return trimmed.slice(0, limit - 3) + "...";
}

function redactSecrets(text) {
  let result = String(text || "");
  for (const [pattern, replacement] of REDACTION_PATTERNS) {
    result = result.replace(pattern, replacement);
  }
  return result;
}

function ensureLogDir() {
  fs.mkdirSync(path.dirname(JSONL_PATH), { recursive: true });
}

function readAllEvents() {
  if (!fs.existsSync(JSONL_PATH)) return [];
  return fs
    .readFileSync(JSONL_PATH, "utf8")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

function appendJsonlLine(line) {
  ensureLogDir();
  fs.appendFileSync(JSONL_PATH, line + "\n", "utf8");
}

function loadSessionState() {
  if (!fs.existsSync(SESSION_STATE_PATH)) return {};
  try {
    return JSON.parse(fs.readFileSync(SESSION_STATE_PATH, "utf8"));
  } catch {
    return {};
  }
}

function saveSessionState(state) {
  fs.writeFileSync(SESSION_STATE_PATH, JSON.stringify(state, null, 2), "utf8");
}

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
    if (d.match_count !== undefined && d.match_count !== null) lines.push(`- **Results:** ${d.match_count} matches`);
  } else if (event.event_type === "read") {
    if (d.file_path) lines.push(`- **File:** \`${d.file_path}\``);
    if (d.line_range) lines.push(`- **Lines:** ${d.line_range}`);
  } else if (event.event_type === "edit") {
    if (d.file_path) lines.push(`- **File:** \`${d.file_path}\``);
    if (d.operation) lines.push(`- **Operation:** ${d.operation}`);
  } else if (event.event_type === "shell") {
    if (d.command) lines.push(`- **Command:** \`${d.command}\``);
    if (d.exit_code !== undefined && d.exit_code !== null) lines.push(`- **Exit code:** ${d.exit_code}`);
  } else if (event.event_type === "prompt") {
    if (d.message) lines.push(`- **User:** ${d.message}`);
  } else if (event.event_type === "response") {
    if (d.summary) lines.push(`- **Agent:** ${d.summary}`);
  } else if (event.event_type === "task") {
    if (d.subagent_type) lines.push(`- **Subagent:** ${d.subagent_type}`);
    if (d.description) lines.push(`- **Task:** ${d.description}`);
  } else if (event.event_type === "mcp") {
    if (d.server) lines.push(`- **Server:** ${d.server}`);
    if (d.tool_name) lines.push(`- **Tool:** ${d.tool_name}`);
  } else if (event.event_type === "session_start") {
    if (d.project_root) lines.push(`- **Project:** \`${d.project_root}\``);
  } else if (event.event_type === "session_end") {
    if (d.duration_seconds !== undefined && d.duration_seconds !== null) lines.push(`- **Duration:** ${d.duration_seconds}s`);
    if (d.total_events !== undefined) lines.push(`- **Events this session:** ${d.total_events}`);
  }

  return lines.join("\n");
}

function generateMarkdownSummary() {
  const events = readAllEvents();
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
      const date = eventDateLabel(event.timestamp);
      (byDate[date] ||= []).push(event);
    }
    for (const date of Object.keys(byDate).sort().reverse()) {
      lines.push(`## ${date}`, "");
      for (const event of byDate[date]) {
        lines.push(formatEventMarkdown(event), "");
      }
    }
  }

  const counts = {};
  for (const event of events) counts[event.event_type] = (counts[event.event_type] || 0) + 1;

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
    `| Responses | ${counts.response || 0} |`,
    `| Tasks | ${counts.task || 0} |`,
    `| MCP calls | ${counts.mcp || 0} |`,
    ""
  );

  fs.writeFileSync(MARKDOWN_PATH, lines.join("\n"), "utf8");
}

function appendEvent(event) {
  appendJsonlLine(JSON.stringify(event));
  generateMarkdownSummary();
}

function readStdinJson() {
  const raw = fs.readFileSync(0, "utf8").replace(/^\uFEFF/, "");
  if (!raw.trim()) return {};
  return JSON.parse(raw);
}

function getSessionId(payload) {
  for (const key of ["conversation_id", "session_id", "chat_id", "thread_id"]) {
    if (payload[key]) return String(payload[key]);
  }
  return "unknown";
}

function getToolName(payload) {
  for (const key of ["tool_name", "toolName", "name", "tool"]) {
    if (typeof payload[key] === "string" && payload[key]) return payload[key];
  }
  return payload?.tool?.name || "";
}

function getToolInput(payload) {
  for (const key of ["tool_input", "toolInput", "input", "arguments"]) {
    if (payload[key] && typeof payload[key] === "object") return payload[key];
  }
  return payload?.tool?.input && typeof payload.tool.input === "object" ? payload.tool.input : {};
}

function getToolOutput(payload) {
  for (const key of ["tool_output", "toolOutput", "output", "result"]) {
    if (key in payload) return payload[key];
  }
  return payload?.tool?.output;
}

function countGrepMatches(output) {
  if (output == null) return null;
  const text = typeof output === "string" ? output : JSON.stringify(output);
  if (!text || text.includes("No matches found")) return 0;
  const matches = text.match(/^[^\n]+:\d+:/gm);
  return matches ? matches.length : null;
}

function buildSearchEvent(payload, tool, toolInput) {
  const output = getToolOutput(payload);
  if (tool === "WebSearch") {
    const query = String(toolInput.search_term || toolInput.query || "");
    return {
      event_type: "search",
      summary: `Web search for '${truncateText(query, 80)}'`,
      details: { tool, query },
    };
  }
  if (tool === "Glob") {
    const pattern = String(toolInput.glob_pattern || toolInput.pattern || "");
    const dir = String(toolInput.target_directory || toolInput.path || ".");
    const matchCount = typeof output === "string" ? output.split("\n").filter((l) => l.trim()).length : null;
    return {
      event_type: "search",
      summary: `Searched files matching '${truncateText(pattern, 80)}'`,
      details: { tool, query: pattern, path: dir, match_count: matchCount },
    };
  }
  const query = String(toolInput.pattern || toolInput.query || "");
  const dir = String(toolInput.path || ".");
  return {
    event_type: "search",
    summary: `Searched codebase for '${truncateText(query, 80)}'`,
    details: { tool, query, path: dir, match_count: countGrepMatches(output) },
  };
}

function buildToolUseEvent(payload) {
  const tool = getToolName(payload);
  if (!tool) return null;
  const toolInput = getToolInput(payload);

  if (["Grep", "WebSearch", "Glob"].includes(tool)) {
    return buildSearchEvent(payload, tool, toolInput);
  }
  if (tool === "Read") {
    const filePath = String(toolInput.path || toolInput.file_path || "unknown");
    const offset = toolInput.offset;
    const limit = toolInput.limit;
    const lineRange = offset != null || limit != null ? `${offset || 1}-${limit || "end"}` : null;
    return { event_type: "read", summary: `Read file '${filePath}'`, details: { file_path: filePath, line_range: lineRange } };
  }
  if (["Write", "StrReplace", "Delete"].includes(tool)) {
    const filePath = String(toolInput.path || toolInput.file_path || "unknown");
    const operation = tool === "Delete" ? "delete" : tool === "Write" ? "create" : "update";
    return { event_type: "edit", summary: `${operation[0].toUpperCase()}${operation.slice(1)} file '${filePath}'`, details: { file_path: filePath, operation, tool } };
  }
  if (tool === "Shell") {
    const command = redactSecrets(String(toolInput.command || ""));
    const output = getToolOutput(payload);
    const exitCode = output && typeof output === "object" ? output.exit_code ?? output.exitCode : null;
    return { event_type: "shell", summary: `Ran shell command: ${truncateText(command, 80)}`, details: { command: truncateText(command, 200), exit_code: exitCode } };
  }
  if (tool === "Task") {
    const description = String(toolInput.description || toolInput.prompt || "subagent task");
    const subagentType = String(toolInput.subagent_type || toolInput.subagentType || "unknown");
    return { event_type: "task", summary: `Started subagent task: ${truncateText(description, 80)}`, details: { subagent_type: subagentType, description: truncateText(description, 200) } };
  }
  if (tool.startsWith("MCP:") || tool.toLowerCase().includes("mcp")) {
    const server = String(toolInput.server || "unknown");
    const toolName = String(toolInput.toolName || toolInput.tool_name || tool);
    return { event_type: "mcp", summary: `MCP call: ${server}/${toolName}`, details: { server, tool_name: toolName } };
  }
  return { event_type: "tool", summary: `Tool call: ${tool}`, details: { tool } };
}

function makeEvent(payload, partial) {
  return {
    id: generateEventId(),
    timestamp: utcNowIso(),
    session_id: getSessionId(payload),
    actor: partial.actor || "agent",
    ...partial,
  };
}

const handlers = {
  session_start(payload) {
    const sessionId = getSessionId(payload);
    saveSessionState({ session_id: sessionId, started_at: utcNowIso(), event_count: 0 });
    appendEvent(makeEvent(payload, {
      event_type: "session_start",
      summary: "AI engineering session started",
      details: { project_root: PROJECT_ROOT },
    }));
  },
  prompt(payload) {
    const message = truncateText(redactSecrets(String(payload.prompt || payload.message || payload.text || "")));
    if (!message) return;
    appendEvent(makeEvent(payload, { event_type: "prompt", actor: "user", summary: `User prompt: ${truncateText(message, 80)}`, details: { message } }));
  },
  tool_use(payload) {
    const partial = buildToolUseEvent(payload);
    if (partial) appendEvent(makeEvent(payload, partial));
  },
  response(payload) {
    const summary = truncateText(redactSecrets(String(payload.response || payload.text || payload.message || payload.content || "")), 200);
    if (!summary) return;
    appendEvent(makeEvent(payload, { event_type: "response", summary: `Agent response: ${truncateText(summary, 80)}`, details: { summary } }));
  },
  session_end(payload) {
    const state = loadSessionState();
    let durationSeconds = null;
    if (state.started_at) {
      durationSeconds = Math.floor((Date.now() - new Date(state.started_at).getTime()) / 1000);
    }
    appendEvent(makeEvent(payload, {
      event_type: "session_end",
      summary: "AI engineering session ended",
      details: { duration_seconds: durationSeconds, total_events: state.event_count || 0 },
    }));
    saveSessionState({});
  },
};

async function main() {
  const command = process.argv[2];
  if (!command || !handlers[command]) process.exit(0);
  try {
    const payload = readStdinJson();
    handlers[command](payload);
  } catch (err) {
    console.error(err);
  }
  process.exit(0);
}

main();
