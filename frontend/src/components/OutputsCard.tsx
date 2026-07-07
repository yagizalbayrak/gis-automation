import { Layers } from "lucide-react";
import { useEffect, useState } from "react";
import { Card } from "./ui/Card";
import { getNamedLayer } from "../lib/api";
import { FALLBACK_COLORS, NAMED_LAYER_COLORS } from "../lib/mapLayers";

interface OutputSummary {
  name: string;
  color: string;
  featureCount: number;
  sourceSrid: string | null;
}

export function OutputsCard({ taskId, outputs }: { taskId: string; outputs: Record<string, string> }) {
  const [summaries, setSummaries] = useState<OutputSummary[]>([]);

  useEffect(() => {
    let cancelled = false;
    let colorIndex = 0;
    (async () => {
      const results: OutputSummary[] = [];
      for (const name of Object.keys(outputs)) {
        const layer = await getNamedLayer(taskId, name);
        if (!layer) continue;
        results.push({
          name,
          color: NAMED_LAYER_COLORS[name] || FALLBACK_COLORS[colorIndex++ % FALLBACK_COLORS.length],
          featureCount: layer.feature_count,
          sourceSrid: layer.source_srid,
        });
      }
      if (!cancelled) setSummaries(results);
    })();
    return () => {
      cancelled = true;
    };
  }, [taskId, outputs]);

  if (!Object.keys(outputs).length) return null;

  return (
    <Card title="Outputs" icon={<Layers className="h-3.5 w-3.5" />}>
      <ul className="flex flex-col gap-1.5">
        {summaries.map((summary) => (
          <li key={summary.name} className="flex items-center gap-2 text-[13px]">
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-[3px]"
              style={{ background: summary.color }}
            />
            <span className="font-medium text-text">{summary.name}</span>
            <span className="ml-auto shrink-0 text-[11.5px] text-muted">
              {summary.featureCount} features &middot; source {summary.sourceSrid || "?"}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
