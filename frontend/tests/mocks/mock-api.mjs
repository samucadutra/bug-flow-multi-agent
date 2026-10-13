// Dependency-free stand-in for the BugFlow F09 API, used by tests and browser checks.
// Start with `npm run mock:api`. Options: MOCK_API_PORT (default 8100), MOCK_API_SCENARIO.
// Control interface: GET /_control/requests, POST /_control/reset, POST /_control/scenario.
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const fixturesDir = path.resolve(here, "..", "fixtures");
const fixture = (name) => JSON.parse(readFileSync(path.join(fixturesDir, name), "utf8"));

const API = "/api/v1";
const SCENARIOS = new Set([
  "populated",
  "empty",
  "slow",
  "unavailable",
  "enums-unavailable",
  "runs-error",
  "custom-labels",
  "stats-changes",
  "validation-error",
  "bad-gateway",
  "no-sse",
  "sse-drop",
]);
const UNAVAILABLE = {
  error: { code: "service_unavailable", message: "Database is unavailable", details: [] },
};
const KNOWN_BUG_IDS = new Set(Array.from({ length: 20 }, (_, i) => i + 1));
const ORIGIN_PATTERN = /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/;
const SLOW_DELAY_MS = 1500;
const DROP_AFTER_EVENTS = 2;

function envelope(code, message, details = []) {
  return { error: { code, message, details } };
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Events of one run as [{atMs, type, ...payload}] sorted by time. */
function liveEvents() {
  const script = fixture("run-8-live-script.json");
  const base = script.run;
  const events = [];
  let logId = 800;
  const stepIds = new Map();
  for (const entry of script.timeline) {
    if (entry.kind === "step") {
      const id = stepIds.get(entry.position) ?? 80 + entry.position;
      stepIds.set(entry.position, id);
      events.push({
        atMs: entry.at_ms,
        type: "step",
        step: {
          id,
          run_id: base.id,
          position: entry.position,
          agent_key: script.agent_keys[entry.position - 1],
          status: entry.status,
          input: { bug_id: base.bug_id },
          output: entry.status === "succeeded" ? { summary: "done" } : null,
          error: null,
          started_at: base.started_at,
          duration_ms: entry.status === "succeeded" ? 400 : null,
        },
      });
    } else if (entry.kind === "log") {
      logId += 1;
      events.push({
        atMs: entry.at_ms,
        type: "log",
        log: {
          id: logId,
          run_id: base.id,
          logged_at: base.started_at,
          level: entry.level,
          message: entry.message,
        },
      });
    } else {
      const finished = entry.status === "succeeded";
      events.push({
        atMs: entry.at_ms,
        type: "run",
        run: {
          id: base.id,
          type: base.type,
          bug_id: base.bug_id,
          status: entry.status,
          progress_done: entry.progress_done,
          progress_total: base.progress_total,
          error: null,
          started_at: base.started_at,
          finished_at: finished ? "2026-10-12T13:00:02Z" : null,
        },
      });
    }
  }
  return events;
}

function finishedEvents() {
  const data = fixture("run-7-finished.json");
  return [
    ...data.steps.map((step) => ({ atMs: 0, type: "step", step })),
    ...data.logs.map((log) => ({ atMs: 0, type: "log", log })),
    { atMs: 0, type: "run", run: data.run },
  ];
}

function stateAt(events, elapsedMs, runId) {
  const steps = new Map();
  const logs = [];
  let run = null;
  for (const event of events) {
    if (event.atMs > elapsedMs) break;
    if (event.type === "step") steps.set(event.step.position, event.step);
    else if (event.type === "log") logs.push(event.log);
    else run = event.run;
  }
  return {
    run: run ?? { ...fixture("run-8-live-script.json").run, id: runId },
    steps: [...steps.values()].sort((a, b) => a.position - b.position),
    logs,
  };
}

export function createMockApi({ port = 0, scenario = "populated" } = {}) {
  let current = scenario;
  let records = [];
  let liveStart = null;
  const openStreams = new Set();

  const setScenario = (name) => {
    if (!SCENARIOS.has(name)) return false;
    current = name;
    return true;
  };

  const liveElapsed = () => {
    if (liveStart === null) liveStart = Date.now();
    return Date.now() - liveStart;
  };

  function json(res, status, body, headers = {}) {
    const text = JSON.stringify(body);
    res.writeHead(status, {
      "Content-Type": "application/json",
      "Content-Length": Buffer.byteLength(text),
      ...headers,
    });
    res.end(text);
  }

  function readBody(req) {
    return new Promise((resolve) => {
      const chunks = [];
      req.on("data", (chunk) => chunks.push(chunk));
      req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    });
  }

  function runList(url) {
    const limit = Number(url.searchParams.get("limit") ?? 10);
    const type = url.searchParams.get("type");
    const status = url.searchParams.get("status");
    let items = fixture("runs-recent.json").items;
    if (type) items = items.filter((run) => run.type === type);
    if (status) items = items.filter((run) => run.status === status);
    return { items: items.slice(0, limit) };
  }

  function bugRead(id) {
    return {
      id,
      title: `Sample bug ${id}`,
      description: "Sample description",
      reproduction_steps: "1. Open the page",
      system_version: "1.0.0",
      environment: "production",
      reporting_team: "qa",
      status: "open",
      opened_at: "2026-10-01T09:00:00Z",
      updated_at: "2026-10-01T09:00:00Z",
      component: null,
      severity: null,
    };
  }

  function sendStream(req, res, runId, headers) {
    const events = runId === 7 ? finishedEvents() : liveEvents();
    const drop = current === "sse-drop" && runId === 8;
    res.writeHead(200, {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache",
      ...headers,
    });
    const startedAt = runId === 8 ? liveStart ?? (liveStart = Date.now()) : Date.now();
    const timers = [];
    let sent = 0;
    const close = () => {
      timers.forEach(clearTimeout);
      openStreams.delete(close);
      if (!res.writableEnded) res.end();
    };
    openStreams.add(close);
    req.on("close", close);
    events.forEach((event, index) => {
      const send = () => {
        if (res.writableEnded) return;
        if (drop && sent >= DROP_AFTER_EVENTS) {
          close();
          return;
        }
        sent += 1;
        const payload = { type: event.type, cursor: String(index + 1), ...pick(event) };
        res.write(`id: ${index + 1}\nevent: ${event.type}\ndata: ${JSON.stringify(payload)}\n\n`);
        const last = index === events.length - 1;
        if (last) close();
      };
      const delay = Math.max(0, startedAt + event.atMs - Date.now());
      if (delay === 0) send();
      else timers.push(setTimeout(send, delay));
    });
  }

  function pick(event) {
    if (event.type === "step") return { step: event.step };
    if (event.type === "log") return { log: event.log };
    return { run: event.run };
  }

  async function route(req, res, url, bodyText, corsHeaders) {
    const method = req.method;
    const p = url.pathname;
    const sub = p.startsWith(API) ? p.slice(API.length) : null;
    if (sub === null) return json(res, 404, envelope("not_found", "Not found"), corsHeaders);

    if (current === "unavailable") return json(res, 503, UNAVAILABLE, corsHeaders);
    if (current === "slow") await sleep(SLOW_DELAY_MS);

    if (method === "GET" && sub === "/health") {
      const ok = { ok: true, message: "ok" };
      return json(res, 200, { ok: true, database: ok, vector_search: ok, llm: ok }, corsHeaders);
    }
    if (method === "GET" && sub === "/meta/enums") {
      if (current === "enums-unavailable") return json(res, 503, UNAVAILABLE, corsHeaders);
      const name = current === "custom-labels" ? "enums-custom-labels.json" : "enums.json";
      return json(res, 200, fixture(name), corsHeaders);
    }
    if (method === "GET" && sub === "/stats") {
      if (current === "bad-gateway") {
        res.writeHead(502, { "Content-Type": "text/plain", ...corsHeaders });
        return res.end("Bad gateway");
      }
      const name = current === "empty" ? "stats-empty.json" : "stats-populated.json";
      return json(res, 200, fixture(name), corsHeaders);
    }
    if (method === "GET" && sub === "/runs") {
      if (current === "runs-error") {
        return json(res, 500, envelope("internal_error", "Internal server error"), corsHeaders);
      }
      if (current === "empty") return json(res, 200, { items: [] }, corsHeaders);
      return json(res, 200, runList(url), corsHeaders);
    }
    let match = /^\/runs\/(\d+)\/events$/.exec(sub);
    if (method === "GET" && match) {
      const id = Number(match[1]);
      if (current === "no-sse" || (id !== 7 && id !== 8)) {
        return json(res, 404, envelope("not_found", `Run ${id} not found`), corsHeaders);
      }
      return sendStream(req, res, id, corsHeaders);
    }
    match = /^\/runs\/(\d+)$/.exec(sub);
    if (method === "GET" && match) {
      const id = Number(match[1]);
      if (id === 7) return json(res, 200, fixture("run-7-finished.json"), corsHeaders);
      if (id === 8) {
        return json(res, 200, stateAt(liveEvents(), liveElapsed(), 8), corsHeaders);
      }
      return json(res, 404, envelope("not_found", `Run ${id} not found`), corsHeaders);
    }
    if (method === "GET" && sub === "/bugs") {
      const page = Number(url.searchParams.get("page") ?? 1);
      const pageSize = Number(url.searchParams.get("page_size") ?? 20);
      const items = [...KNOWN_BUG_IDS].map(bugRead);
      const start = (page - 1) * pageSize;
      const body = { items: items.slice(start, start + pageSize), total: items.length, page, page_size: pageSize };
      return json(res, 200, body, corsHeaders);
    }
    if (method === "POST" && sub === "/bugs") {
      if (current === "validation-error") {
        const details = [{ field: "title", message: "must be at most 120 characters" }];
        return json(res, 422, envelope("validation_error", "Invalid request", details), corsHeaders);
      }
      let fields = {};
      try {
        fields = JSON.parse(bodyText || "{}");
      } catch {
        fields = {};
      }
      return json(res, 201, { ...bugRead(21), ...fields }, corsHeaders);
    }
    match = /^\/bugs\/(\d+)(\/(similar|runs|report|reopen))?$/.exec(sub);
    if (match) {
      const id = Number(match[1]);
      const part = match[3];
      if (!KNOWN_BUG_IDS.has(id)) {
        return json(res, 404, envelope("not_found", `Bug ${id} not found`), corsHeaders);
      }
      if (method === "GET" && !part) {
        const results = { component: null, severity: null, analysis: null, plan: null, report: null };
        return json(res, 200, { ...bugRead(id), results, latest_run: null }, corsHeaders);
      }
      if (method === "PATCH" && !part) {
        let fields = {};
        try {
          fields = JSON.parse(bodyText || "{}");
        } catch {
          fields = {};
        }
        return json(res, 200, { ...bugRead(id), ...fields }, corsHeaders);
      }
      if (method === "POST" && part === "reopen") {
        return json(res, 200, { ...bugRead(id), status: "open" }, corsHeaders);
      }
      if (method === "GET" && part === "similar") return json(res, 200, { items: [] }, corsHeaders);
      if (method === "GET" && part === "runs") return json(res, 200, { items: [] }, corsHeaders);
      if (method === "GET" && part === "report") {
        const format = url.searchParams.get("format") ?? "json";
        if (format === "md") {
          res.writeHead(200, { "Content-Type": "text/markdown", ...corsHeaders });
          return res.end("# Report");
        }
        if (format === "html") {
          res.writeHead(200, { "Content-Type": "text/html", ...corsHeaders });
          return res.end("<h1>Report</h1>");
        }
        return json(res, 200, { bug_id: id, markdown: "# Report", html: "<h1>Report</h1>" }, corsHeaders);
      }
    }
    if (method === "GET" && sub === "/search") {
      return json(res, 200, { items: [], hint: "" }, corsHeaders);
    }
    if (method === "POST" && sub === "/admin/db/init") {
      return json(res, 200, { applied_revisions: [], messages: ["Database is up to date"] }, corsHeaders);
    }
    if (method === "POST" && sub === "/admin/db/reset") {
      return json(res, 200, { applied_revisions: [], messages: ["Database reset"] }, corsHeaders);
    }
    if (
      method === "POST" &&
      (sub === "/admin/db/seed" || sub === "/admin/index" || sub === "/triage-runs")
    ) {
      return json(res, 202, { run_ids: [1] }, corsHeaders);
    }
    return json(res, 404, envelope("not_found", "Not found"), corsHeaders);
  }

  async function handle(req, res) {
    const url = new URL(req.url ?? "/", "http://127.0.0.1");
    const origin = req.headers.origin;
    const corsHeaders = {};
    if (origin && ORIGIN_PATTERN.test(origin)) {
      corsHeaders["Access-Control-Allow-Origin"] = origin;
      corsHeaders["Vary"] = "Origin";
    }
    if (req.method === "OPTIONS") {
      res.writeHead(204, {
        ...corsHeaders,
        "Access-Control-Allow-Methods": "GET, POST, PATCH, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Last-Event-ID",
      });
      return res.end();
    }
    const bodyText = await readBody(req);
    if (url.pathname.startsWith("/_control/")) {
      const control = url.pathname.slice("/_control/".length);
      if (control === "requests" && req.method === "GET") {
        return json(res, 200, { scenario: current, requests: records }, corsHeaders);
      }
      if (control === "reset" && req.method === "POST") {
        records = [];
        liveStart = null;
        openStreams.forEach((close) => close());
        current = "populated";
        return json(res, 200, { ok: true }, corsHeaders);
      }
      if (control === "scenario" && req.method === "POST") {
        let name = url.searchParams.get("name");
        if (!name) {
          try {
            name = JSON.parse(bodyText || "{}").name;
          } catch {
            name = null;
          }
        }
        if (!name || !setScenario(name)) {
          return json(res, 400, envelope("unknown_scenario", "Unknown scenario"), corsHeaders);
        }
        return json(res, 200, { scenario: current }, corsHeaders);
      }
      return json(res, 404, envelope("not_found", "Not found"), corsHeaders);
    }
    let body = null;
    if (bodyText) {
      try {
        body = JSON.parse(bodyText);
      } catch {
        body = bodyText;
      }
    }
    records.push({
      method: req.method,
      path: url.pathname,
      query: Object.fromEntries(url.searchParams),
      search: url.search,
      contentType: req.headers["content-type"] ?? null,
      body,
    });
    return route(req, res, url, bodyText, corsHeaders);
  }

  const server = createServer((req, res) => {
    handle(req, res).catch(() => {
      if (!res.headersSent) res.writeHead(500);
      res.end();
    });
  });

  return {
    server,
    get scenario() {
      return current;
    },
    start() {
      return new Promise((resolve) => {
        server.listen(port, "127.0.0.1", () => resolve(server.address().port));
      });
    },
    stop() {
      openStreams.forEach((close) => close());
      server.closeAllConnections?.();
      return new Promise((resolve) => server.close(() => resolve()));
    },
  };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.MOCK_API_PORT ?? 8100);
  const scenario = process.env.MOCK_API_SCENARIO ?? "populated";
  const api = createMockApi({ port, scenario });
  const actual = await api.start();
  console.log(`listening http://127.0.0.1:${actual}`);
}
