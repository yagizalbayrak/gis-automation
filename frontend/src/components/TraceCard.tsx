import { motion } from "motion/react";
import { ListTree } from "lucide-react";
import { useEffect, useRef } from "react";
import { Card } from "./ui/Card";
import { phaseBorderClass, summarizeDetail } from "../lib/traceFormat";
import type { TraceEvent } from "../lib/types";

export function TraceCard({ trace }: { trace: TraceEvent[] }) {
  const listRef = useRef<HTMLOListElement | null>(null);

  useEffect(() => {
    listRef.current?.lastElementChild?.scrollIntoView({ block: "nearest" });
  }, [trace.length]);

  if (!trace.length) return null;

  return (
    <Card title="Process trace" icon={<ListTree className="h-3.5 w-3.5" />}>
      <ol ref={listRef} className="scroll-thin flex max-h-72 flex-col gap-1 overflow-y-auto">
        {trace.map((event, index) => {
          const stepId = event.detail?.step_id;
          return (
            <motion.li
              key={index}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.25 }}
              className={`rounded-lg border-l-2 bg-bg-elevated/60 px-2.5 py-1.5 font-mono text-[11px] leading-relaxed ${phaseBorderClass(
                event.phase,
              )}`}
            >
              <span className="font-semibold text-text">{event.phase}</span>
              <span className="text-muted-2"> &middot; </span>
              <span className="text-cyan">{event.subject}</span>
              {typeof stepId === "string" && (
                <span className="ml-1.5 rounded border border-border px-1 py-0 text-[9.5px] text-muted">
                  {stepId}
                </span>
              )}
              {summarizeDetail(event.detail) && (
                <div className="mt-0.5 break-words text-muted">
                  {summarizeDetail(event.detail)}
                </div>
              )}
            </motion.li>
          );
        })}
      </ol>
    </Card>
  );
}
