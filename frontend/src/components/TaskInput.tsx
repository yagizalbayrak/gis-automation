import { CornerDownLeft, Play } from "lucide-react";

const EXAMPLES = [
  {
    label: "Street buffer (TR)",
    text: 'Kutahya\'daki "Ataturk Caddesi" icin 25 m buffer uygula',
  },
  {
    label: "Rental site search (TR)",
    text: "Kutahya Evliya Celebi Mahallesi'nde okula 500 m, ana yollara 250 m mesafede kiralik ev icin uygun alanlari bul",
  },
  {
    label: "Fetch roads (TR)",
    text: "Kutahya'daki tum yollari haritaya cek",
  },
];

interface TaskInputProps {
  text: string;
  setText: (value: string) => void;
  onRun: () => void;
  running: boolean;
}

export function TaskInput({ text, setText, onRun, running }: TaskInputProps) {
  return (
    <div className="flex flex-col gap-2.5">
      <div className="group relative rounded-2xl border border-border bg-bg-elevated/80 transition-colors focus-within:border-accent/50">
        <textarea
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) onRun();
          }}
          placeholder='e.g. Kutahya&#39;daki "Ataturk Caddesi" icin 25 m buffer uygula'
          className="w-full resize-y rounded-2xl bg-transparent px-4 py-3 text-[13.5px] text-text placeholder:text-muted-2 focus:outline-none"
        />
        <span className="pointer-events-none absolute bottom-2.5 right-3 flex items-center gap-1 text-[10px] text-muted-2">
          <kbd className="rounded border border-border px-1 py-0.5 font-mono">Ctrl/Cmd</kbd>
          <CornerDownLeft className="h-3 w-3" />
        </span>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {EXAMPLES.map((example) => (
          <button
            key={example.label}
            type="button"
            onClick={() => setText(example.text)}
            className="rounded-full border border-border bg-white/[0.02] px-2.5 py-1 text-[11px] font-medium text-muted transition hover:border-accent/40 hover:text-accent"
          >
            {example.label}
          </button>
        ))}
      </div>

      <button
        type="button"
        onClick={onRun}
        disabled={running || !text.trim()}
        className="flex items-center justify-center gap-2 rounded-xl bg-accent py-2.5 text-[13.5px] font-semibold text-bg transition hover:brightness-110 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-45"
      >
        <Play className="h-4 w-4" fill="currentColor" />
        Run
      </button>
    </div>
  );
}
