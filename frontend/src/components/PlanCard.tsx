import { Workflow } from "lucide-react";
import { Card } from "./ui/Card";
import type { PlanStep } from "../lib/types";

export function PlanCard({ plan }: { plan: PlanStep[] }) {
  if (!plan.length) return null;
  return (
    <Card title="Composed plan" icon={<Workflow className="h-3.5 w-3.5" />}>
      <ol className="flex flex-col gap-1.5">
        {plan.map((step, index) => (
          <li
            key={step.id}
            className="rounded-lg border-l-2 border-cyan/50 bg-bg-elevated/60 px-2.5 py-1.5 font-mono text-[11.5px] leading-relaxed"
          >
            <span className="text-muted-2">{index + 1}.</span>{" "}
            <span className="font-semibold text-text">{step.id}</span>{" "}
            <span className="text-cyan">{step.tool}</span>
            <div className="mt-0.5 truncate text-muted">{JSON.stringify(step.params)}</div>
          </li>
        ))}
      </ol>
    </Card>
  );
}
