export function summarizeDetail(detail: Record<string, unknown> | undefined): string {
  if (!detail) return "";
  if (typeof detail.message === "string") return detail.message;
  if (typeof detail.error === "string") return detail.error;
  if (typeof detail.crs === "string") return `input=${String(detail.input)} crs=${detail.crs}`;
  const compact = JSON.stringify(detail);
  return compact.length > 160 ? `${compact.slice(0, 157)}...` : compact;
}

const PHASE_BORDER: Record<string, string> = {
  guard_passed: "border-ok/50",
  guard_failed: "border-fail/50",
  tool_failed: "border-fail/50",
  workflow_failed: "border-fail/50",
  tool_started: "border-cyan/50",
  tool_finished: "border-ok/50",
  workflow_started: "border-accent/50",
  workflow_finished: "border-accent/50",
};

export function phaseBorderClass(phase: string): string {
  return PHASE_BORDER[phase] ?? "border-border-strong";
}
