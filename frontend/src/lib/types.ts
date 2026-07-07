// Mirrors ageo.interface.api.schemas / clarifier.py / trace.py. Kept
// deliberately loose (most fields optional-safe) since the backend is the
// source of truth and re-validates everything - the UI only needs to
// render what it's given.

export type TaskStatus =
  | "unmatched"
  | "needs_input"
  | "running"
  | "succeeded"
  | "failed";

export interface QuestionOption {
  value: unknown;
  label: { en: string; tr: string };
  recommended: boolean;
}

export type QuestionType =
  | "parameter"
  | "risk_confirmation"
  | "clarification"
  | "preference";
export type Severity = "critical" | "material" | "cosmetic";

export interface PendingQuestion {
  question_id: string;
  question_type: QuestionType;
  severity: Severity;
  param: string;
  kind: string;
  reason: string;
  text: { en: string; tr: string };
  options: QuestionOption[];
  blocking: boolean;
  default_if_skipped: unknown;
}

export interface Assumption {
  param: string;
  value: unknown;
  source: "spec_default" | "composer_recommended";
  reason: string;
  text: { en: string; tr: string };
}

export interface PlanStep {
  id: string;
  tool: string;
  params: Record<string, unknown>;
}

export interface TaskResponse {
  task_id: string;
  status: TaskStatus;
  text: string;
  workflow: string | null;
  mode: "registered" | "composed";
  plan: PlanStep[];
  params: Record<string, unknown>;
  missing_params: string[];
  questions: PendingQuestion[];
  assumptions: Assumption[];
  explanation: string;
  outputs: Record<string, string>;
  results: Record<string, unknown>;
  error: string | null;
}

export type TracePhase =
  | "tool_started"
  | "guard_passed"
  | "guard_failed"
  | "tool_finished"
  | "tool_failed"
  | "workflow_started"
  | "workflow_finished"
  | "workflow_failed";

export interface TraceEvent {
  phase: TracePhase;
  subject: string;
  detail: Record<string, unknown>;
  timestamp: number;
}

export interface LayerResponse {
  name: string;
  source_srid: string | null;
  display_srid: string;
  feature_count: number;
  feature_collection: GeoJSON.FeatureCollection;
}

export interface WorkflowCatalogParam {
  name: string;
  kind: string;
  description: string;
  required: boolean;
  default: unknown;
}

export interface WorkflowCatalogEntry {
  name: string;
  summary: string;
  nl_patterns: string[];
  params: WorkflowCatalogParam[];
}

export interface ToolCatalogEntry {
  name: string;
  summary: string;
  input_schema: unknown;
  output_schema: unknown;
  crs_requirements: Record<string, string>;
  failure_modes: string[];
}

export interface Catalog {
  workflows: WorkflowCatalogEntry[];
  tools: ToolCatalogEntry[];
}

export interface ProviderPreset {
  label: string;
  models: string[];
  key_hint?: string;
}

export interface LlmSettingsResponse {
  configured: boolean;
  provider: string | null;
  model: string | null;
  api_key_masked: string | null;
  api_base: string | null;
  providers: Record<string, ProviderPreset>;
}

export interface LlmTestResponse {
  ok: boolean;
  model: string | null;
  latency_ms: number | null;
  message: string;
}

export interface ReportResponse {
  task_id: string;
  lang: string;
  depth: string;
  report: string;
}

export type ReportLang = "en" | "tr";
