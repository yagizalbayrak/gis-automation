import { CheckCircle2, CircleSlash, HelpCircle, Loader2, XCircle } from "lucide-react";
import type { TaskStatus } from "../../lib/types";

const CONFIG: Record<
  TaskStatus,
  { label: string; classes: string; icon: React.ComponentType<{ className?: string }> }
> = {
  running: {
    label: "running",
    classes: "border-cyan/40 text-cyan shadow-[0_0_0_1px] shadow-cyan/10",
    icon: Loader2,
  },
  succeeded: {
    label: "succeeded",
    classes: "border-ok/40 text-ok",
    icon: CheckCircle2,
  },
  failed: {
    label: "failed",
    classes: "border-fail/40 text-fail",
    icon: XCircle,
  },
  needs_input: {
    label: "needs input",
    classes: "border-warn/40 text-warn",
    icon: HelpCircle,
  },
  unmatched: {
    label: "unmatched",
    classes: "border-muted-2/60 text-muted",
    icon: CircleSlash,
  },
};

export function StatusChip({ status }: { status: TaskStatus }) {
  const { label, classes, icon: Icon } = CONFIG[status];
  return (
    <span
      className={`relative inline-flex items-center gap-1.5 rounded-full border bg-white/[0.03] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${classes}`}
    >
      {status === "running" && (
        <span className="absolute -inset-px animate-pulse-ring rounded-full" />
      )}
      <Icon className={`h-3 w-3 ${status === "running" ? "animate-spin" : ""}`} />
      {label}
    </span>
  );
}
