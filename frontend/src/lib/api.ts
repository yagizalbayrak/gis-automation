import type {
  Catalog,
  LlmSettingsResponse,
  LlmTestResponse,
  ReportLang,
  ReportResponse,
  TaskResponse,
} from "./types";

async function asJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export async function createTask(
  text: string,
  params: Record<string, unknown> = {},
): Promise<TaskResponse> {
  const response = await fetch("/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, params }),
  });
  return asJson<TaskResponse>(response);
}

export async function getTask(taskId: string): Promise<TaskResponse> {
  return asJson<TaskResponse>(await fetch(`/tasks/${taskId}`));
}

export async function getReport(
  taskId: string,
  lang: ReportLang,
): Promise<ReportResponse> {
  return asJson<ReportResponse>(
    await fetch(`/tasks/${taskId}/report?lang=${lang}`),
  );
}

export function traceEventsUrl(taskId: string): string {
  return `/tasks/${taskId}/events`;
}

export interface LayerPreview {
  name: string;
  source_srid: string | null;
  display_srid: string;
  feature_count: number;
  feature_collection: GeoJSON.FeatureCollection;
}

export async function getNamedLayer(
  taskId: string,
  outputName: string,
): Promise<LayerPreview | null> {
  const response = await fetch(`/tasks/${taskId}/layers/${outputName}`);
  if (!response.ok) return null;
  return (await response.json()) as LayerPreview;
}

export async function getWorkspaceLayer(
  taskId: string,
  layerId: string,
): Promise<LayerPreview | null> {
  const response = await fetch(`/tasks/${taskId}/workspace/${layerId}`);
  if (!response.ok) return null;
  return (await response.json()) as LayerPreview;
}

export async function getCatalog(): Promise<Catalog> {
  return asJson<Catalog>(await fetch("/catalog"));
}

export async function uploadFile(
  file: File,
): Promise<{ path: string; filename: string; size_bytes: number }> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/uploads", { method: "POST", body: form });
  return asJson(response);
}

export async function getLlmSettings(): Promise<LlmSettingsResponse> {
  return asJson<LlmSettingsResponse>(await fetch("/settings/llm"));
}

export interface LlmSettingsPayload {
  provider: string;
  model: string;
  api_key?: string | null;
  api_base?: string | null;
}

export async function saveLlmSettings(
  payload: LlmSettingsPayload,
): Promise<LlmSettingsResponse> {
  const response = await fetch("/settings/llm", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return asJson<LlmSettingsResponse>(response);
}

export async function testLlmSettings(): Promise<LlmTestResponse> {
  return asJson<LlmTestResponse>(
    await fetch("/settings/llm/test", { method: "POST" }),
  );
}
