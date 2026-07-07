import { Lightbulb } from "lucide-react";
import { Card } from "./ui/Card";
import type { Assumption, ReportLang } from "../lib/types";

export function AssumptionsCard({
  assumptions,
  lang,
}: {
  assumptions: Assumption[];
  lang: ReportLang;
}) {
  if (!assumptions.length) return null;
  return (
    <Card title="Assumptions" icon={<Lightbulb className="h-3.5 w-3.5" />}>
      <ul className="flex flex-col gap-1.5">
        {assumptions.map((assumption, index) => (
          <li key={`${assumption.param}-${index}`} className="text-[12.5px] leading-relaxed text-muted">
            {assumption.text?.[lang] || assumption.text?.en || `Assumed: ${assumption.param} = ${assumption.value}`}
          </li>
        ))}
      </ul>
    </Card>
  );
}
