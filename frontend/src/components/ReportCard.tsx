import { FileText } from "lucide-react";
import { Card } from "./ui/Card";
import type { ReportLang } from "../lib/types";

interface ReportCardProps {
  report: string;
  lang: ReportLang;
  setLang: (lang: ReportLang) => void;
}

export function ReportCard({ report, lang, setLang }: ReportCardProps) {
  return (
    <Card
      title="Report"
      icon={<FileText className="h-3.5 w-3.5" />}
      right={
        <div className="flex gap-1">
          {(["en", "tr"] as ReportLang[]).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setLang(option)}
              className={`rounded-md border px-1.5 py-0.5 text-[10px] font-bold uppercase transition ${
                lang === option
                  ? "border-accent/50 text-accent"
                  : "border-border text-muted hover:text-text"
              }`}
            >
              {option}
            </button>
          ))}
        </div>
      }
    >
      <pre className="scroll-thin max-h-96 overflow-y-auto whitespace-pre-wrap break-words font-mono text-[11.5px] leading-relaxed text-text">
        {report}
      </pre>
    </Card>
  );
}
