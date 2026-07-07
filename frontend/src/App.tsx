import { useState } from "react";
import { MapView } from "./components/MapView";
import { TopBar } from "./components/TopBar";
import { SettingsPanel } from "./components/SettingsPanel";
import { TaskInput } from "./components/TaskInput";
import { StatusChip } from "./components/ui/StatusChip";
import { UnderstoodCard } from "./components/UnderstoodCard";
import { PlanCard } from "./components/PlanCard";
import { AssumptionsCard } from "./components/AssumptionsCard";
import { QuestionsCard } from "./components/QuestionsCard";
import { ErrorCard } from "./components/ErrorCard";
import { TraceCard } from "./components/TraceCard";
import { OutputsCard } from "./components/OutputsCard";
import { ReportCard } from "./components/ReportCard";
import { useWorkbench } from "./hooks/useWorkbench";
import { useLlmSettings } from "./hooks/useLlmSettings";

export default function App() {
  const workbench = useWorkbench();
  const llm = useLlmSettings();
  const [settingsOpen, setSettingsOpen] = useState(false);

  const { task } = workbench;

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-bg font-sans text-text">
      <div className="absolute inset-0">
        <MapView
          taskId={task?.task_id ?? null}
          status={task?.status}
          trace={workbench.trace}
          outputs={task?.outputs ?? {}}
        />
      </div>

      <div className="pointer-events-none absolute inset-0 flex flex-col gap-3 p-4">
        <TopBar
          aiConfigured={llm.configured}
          aiModel={llm.configuredModel}
          settingsOpen={settingsOpen}
          onToggleSettings={() => setSettingsOpen((value) => !value)}
        />

        <div className="flex min-h-0 flex-1 gap-3">
          <aside className="scroll-thin pointer-events-auto flex w-[400px] shrink-0 flex-col gap-3 overflow-y-auto rounded-2xl border border-border bg-panel/75 p-4 shadow-2xl shadow-black/40 backdrop-blur-2xl">
            <SettingsPanel open={settingsOpen} settings={llm} />

            <TaskInput
              text={workbench.text}
              setText={workbench.setText}
              onRun={() => void workbench.submit({})}
              running={workbench.running}
            />

            {task && (
              <div className="flex items-center gap-2">
                <StatusChip status={task.status} />
                <span className="truncate font-mono text-[12px] text-muted">
                  {task.workflow}
                  {task.mode === "composed" && <span className="ml-1 text-accent">[composed]</span>}
                </span>
              </div>
            )}

            {task && <UnderstoodCard task={task} />}
            {task && <PlanCard plan={task.plan} />}
            {task && (
              <AssumptionsCard assumptions={task.assumptions} lang={workbench.reportLang} />
            )}
            {task?.status === "needs_input" && (
              <QuestionsCard
                task={task}
                lang={workbench.reportLang}
                onAnswer={(params) => void workbench.submit(params)}
              />
            )}
            {task?.status === "failed" && task.error && <ErrorCard message={task.error} />}
            {task?.status === "unmatched" && (
              <ErrorCard message="No registered workflow matches this request yet. Try a road fetch/buffer, a quality check on a file, or a CRS conversion." />
            )}

            <TraceCard trace={workbench.trace} />
            {task?.status === "succeeded" && (
              <OutputsCard taskId={task.task_id} outputs={task.outputs} />
            )}
            {workbench.report && (
              <ReportCard
                report={workbench.report}
                lang={workbench.reportLang}
                setLang={workbench.setReportLang}
              />
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}
