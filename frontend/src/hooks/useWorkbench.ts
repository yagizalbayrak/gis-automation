import { useCallback, useEffect, useRef, useState } from "react";
import { createTask, getReport, getTask, traceEventsUrl } from "../lib/api";
import type { ReportLang, TaskResponse, TraceEvent } from "../lib/types";

const TERMINAL_STATUSES = new Set(["unmatched", "needs_input", "succeeded", "failed"]);

export function useWorkbench() {
  const [text, setText] = useState("");
  const [task, setTask] = useState<TaskResponse | null>(null);
  const [trace, setTrace] = useState<TraceEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [reportLang, setReportLang] = useState<ReportLang>("en");
  const [report, setReport] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const closeStream = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
  }, []);

  useEffect(() => closeStream, [closeStream]);

  const loadReport = useCallback(async (taskId: string, lang: ReportLang) => {
    try {
      const payload = await getReport(taskId, lang);
      setReport(payload.report);
    } catch {
      setReport(null);
    }
  }, []);

  useEffect(() => {
    if (task?.status === "succeeded" && task.task_id) {
      loadReport(task.task_id, reportLang);
    }
    // reportLang changes should only refetch once a task has succeeded -
    // re-running loadReport for every task change is intentional here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportLang]);

  const streamTrace = useCallback(
    (taskId: string) => {
      closeStream();
      const source = new EventSource(traceEventsUrl(taskId));
      eventSourceRef.current = source;

      source.onmessage = (event) => {
        const parsed = JSON.parse(event.data) as TraceEvent;
        setTrace((previous) => [...previous, parsed]);
      };
      source.addEventListener("done", async () => {
        closeStream();
        const latest = await getTask(taskId);
        setTask(latest);
        if (latest.status === "succeeded") {
          await loadReport(taskId, reportLang);
        }
        setRunning(false);
      });
      source.onerror = () => {
        closeStream();
        setRunning(false);
      };
    },
    [closeStream, loadReport, reportLang],
  );

  const submit = useCallback(
    async (params: Record<string, unknown> = {}) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      setTask(null);
      setTrace([]);
      setReport(null);
      setRunning(true);

      const created = await createTask(trimmed, params);
      setTask(created);
      if (created.status === "running") {
        streamTrace(created.task_id);
      } else {
        setRunning(false);
      }
    },
    [text, streamTrace],
  );

  return {
    text,
    setText,
    task,
    trace,
    running,
    reportLang,
    setReportLang,
    report,
    submit,
    isTerminal: task ? TERMINAL_STATUSES.has(task.status) : false,
  };
}
