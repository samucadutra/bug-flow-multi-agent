/** Hand-written mirror of the F09 response and request models. */

export interface FieldError {
  field: string;
  message: string;
}

export interface ErrorEnvelope {
  error: { code: string; message: string; details: FieldError[] | unknown[] };
}

export interface CheckResult {
  ok: boolean;
  message: string;
}

export interface Health {
  ok: boolean;
  database: CheckResult;
  vector_search: CheckResult;
  llm: CheckResult;
}

export interface EnumValue {
  code: string;
  label: string;
  definition: string | null;
}

export interface EnumEntry {
  name: string;
  values: EnumValue[];
}

export interface EnumsResponse {
  enums: EnumEntry[];
}

export interface Stats {
  total: number;
  by_status: Record<string, number>;
  by_component: Record<string, number>;
  by_severity: Record<string, number>;
}

export interface Bug {
  id: number;
  title: string;
  description: string;
  reproduction_steps: string;
  system_version: string;
  environment: string;
  reporting_team: string;
  status: string;
  opened_at: string;
  updated_at: string;
  component: string | null;
  severity: string | null;
}

export interface BugPage {
  items: Bug[];
  total: number;
  page: number;
  page_size: number;
}

export interface BugResults {
  component: { component: string; justification: string } | null;
  severity: { severity: string; justification: string; user_impact: string } | null;
  analysis: {
    root_cause: string;
    technical_impact: string;
    debugging_approach: string[];
    proposed_solution: string;
    side_effects: string[];
    referenced_similar_bug_ids: number[];
  } | null;
  plan: {
    resolution_status: string;
    assigned_team: string;
    assignee_profile: Record<string, unknown>;
    target_days: number;
    priority: string;
    notes: string;
  } | null;
  report: {
    executive_summary: string;
    key_takeaways: string[];
    next_steps: string[];
    has_markdown: boolean;
    has_html: boolean;
  } | null;
}

export interface BugDetail extends Bug {
  results: BugResults;
  latest_run: Run | null;
}

export interface BugCreate {
  title: string;
  description: string;
  reproduction_steps: string;
  system_version: string;
  environment: string;
  reporting_team: string;
}

export type BugUpdate = Partial<BugCreate>;

export interface BugListQuery {
  status?: string;
  component?: string;
  severity?: string;
  environment?: string;
  reporting_team?: string;
  search?: string;
  sort_by?: string;
  sort_dir?: string;
  page?: number;
  page_size?: number;
}

export interface SimilarBug {
  bug_id: number;
  title: string;
  status: string;
  score: number;
}

export interface SimilarResponse {
  items: SimilarBug[];
}

export interface SearchResponse {
  items: SimilarBug[];
  hint: string;
}

export interface ReportJson {
  bug_id: number;
  markdown: string;
  html: string;
}

export type ReportFormat = "json" | "md" | "html";

export interface Run {
  id: number;
  type: string;
  bug_id: number | null;
  status: string;
  progress_done: number;
  progress_total: number;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface RunStep {
  id: number;
  run_id: number;
  position: number;
  agent_key: string;
  status: string;
  input: unknown;
  output: unknown;
  error: string | null;
  started_at: string | null;
  duration_ms: number | null;
}

export interface RunLog {
  id: number;
  run_id: number;
  logged_at: string;
  level: string;
  message: string;
}

export interface RunDetail {
  run: Run;
  steps: RunStep[];
  logs: RunLog[];
}

export interface RunList {
  items: Run[];
}

export interface RunListQuery {
  type?: string;
  status?: string;
  limit?: number;
}

export interface RunIds {
  run_ids: number[];
}

export interface InitResult {
  applied_revisions: string[];
  messages: string[];
}

export type TriageTarget = { bug_id: number } | { all: true };

/** Server-sent frames of `/runs/{id}/events`. */
export type RunEvent =
  | { type: "step"; cursor: string; step: RunStep }
  | { type: "log"; cursor: string; log: RunLog }
  | { type: "run"; cursor: string; run: Run };
