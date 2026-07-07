import { CircleHelp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Card } from "./ui/Card";
import { useCatalog } from "../hooks/useCatalog";
import type { ReportLang, TaskResponse } from "../lib/types";

interface Field {
  name: string;
  label: string;
  kind: string;
  recommended?: unknown;
}

interface QuestionsCardProps {
  task: TaskResponse;
  lang: ReportLang;
  onAnswer: (params: Record<string, unknown>) => void;
}

export function QuestionsCard({ task, lang, onAnswer }: QuestionsCardProps) {
  const { catalog, ensureLoaded } = useCatalog();
  const [values, setValues] = useState<Record<string, string>>({});
  const useStructured = task.questions.length > 0;

  useEffect(() => {
    if (!useStructured) void ensureLoaded();
  }, [useStructured, ensureLoaded]);

  useEffect(() => {
    const defaults: Record<string, string> = {};
    for (const question of task.questions) {
      if (question.default_if_skipped !== null && question.default_if_skipped !== undefined) {
        defaults[question.param] = String(question.default_if_skipped);
      }
    }
    setValues(defaults);
  }, [task.questions]);

  const workflow = catalog?.workflows.find((w) => w.name === task.workflow);

  const fields: Field[] = useMemo(() => {
    if (useStructured) {
      return task.questions.map((question) => ({
        name: question.param,
        label: question.text[lang] || question.text.en,
        kind: question.kind,
        recommended: question.options.find((option) => option.recommended)?.value,
      }));
    }
    return task.missing_params.map((name) => {
      const meta = workflow?.params.find((p) => p.name === name);
      return {
        name,
        label: `${name} - ${meta?.description || meta?.kind || ""}`,
        kind: meta?.kind || "string",
      };
    });
  }, [useStructured, task.questions, task.missing_params, workflow, lang]);

  const submit = () => {
    const params: Record<string, unknown> = {};
    for (const field of fields) {
      const raw = values[field.name]?.trim();
      if (!raw) continue;
      params[field.name] = field.kind === "float" || field.kind === "int" ? Number(raw) : raw;
    }
    onAnswer(params);
  };

  return (
    <Card title="Needs your input" icon={<CircleHelp className="h-3.5 w-3.5" />}>
      <div className="flex flex-col gap-3">
        {fields.map((field) => (
          <label key={field.name} className="flex flex-col gap-1 text-[12.5px] text-muted">
            <span>
              {field.label}
              {field.recommended !== undefined && (
                <span className="ml-1.5 text-accent">
                  (recommended: {String(field.recommended)})
                </span>
              )}
            </span>
            <input
              value={values[field.name] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))}
              placeholder={field.kind === "float" || field.kind === "int" ? "e.g. 25" : ""}
              className="rounded-lg border border-border bg-bg-elevated px-2.5 py-1.5 text-[13px] text-text focus:border-accent/50 focus:outline-none"
            />
          </label>
        ))}
        <button
          type="button"
          onClick={submit}
          className="rounded-lg bg-accent py-2 text-[13px] font-semibold text-bg transition hover:brightness-110 active:scale-[0.98]"
        >
          Answer &amp; run
        </button>
      </div>
    </Card>
  );
}
