import { ScanSearch } from "lucide-react";
import { Card } from "./ui/Card";
import type { TaskResponse } from "../lib/types";

export function UnderstoodCard({ task }: { task: TaskResponse }) {
  return (
    <Card title="Understood" icon={<ScanSearch className="h-3.5 w-3.5" />}>
      <div className="flex flex-col gap-2 text-[13px] leading-relaxed">
        <Row label="request" value={task.text} />
        {task.workflow && <Row label="workflow" value={task.workflow} mono />}
        {Object.keys(task.params).length > 0 && (
          <Row label="parameters" value={JSON.stringify(task.params)} mono />
        )}
        {task.explanation && <Row label="planner" value={task.explanation} />}
      </div>
    </Card>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex gap-2.5">
      <span className="w-[72px] shrink-0 text-muted">{label}</span>
      <span className={`break-words ${mono ? "font-mono text-[12px] text-cyan" : "text-text"}`}>
        {value}
      </span>
    </div>
  );
}
