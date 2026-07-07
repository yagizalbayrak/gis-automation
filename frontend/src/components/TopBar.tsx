import { Settings2, Waypoints } from "lucide-react";

interface TopBarProps {
  aiConfigured: boolean;
  aiModel: string | null;
  onToggleSettings: () => void;
  settingsOpen: boolean;
}

export function TopBar({ aiConfigured, aiModel, onToggleSettings, settingsOpen }: TopBarProps) {
  return (
    <div className="pointer-events-auto flex items-center gap-3 rounded-2xl border border-border bg-panel/80 px-4 py-2.5 shadow-xl shadow-black/30 backdrop-blur-2xl">
      <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent/15 text-accent">
        <Waypoints className="h-4.5 w-4.5" />
      </div>
      <div className="leading-tight">
        <div className="text-[13px] font-semibold tracking-tight text-text">
          Autonomous GIS Workbench
        </div>
        <div className="text-[10.5px] text-muted">
          Natural-language geospatial automation
        </div>
      </div>

      <div className="mx-1 h-6 w-px bg-border" />

      <div
        className={`hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-[10.5px] font-medium sm:flex ${
          aiConfigured ? "bg-ok/10 text-ok" : "bg-warn/10 text-warn"
        }`}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${aiConfigured ? "bg-ok" : "bg-warn"}`} />
        {aiConfigured ? aiModel : "AI not configured"}
      </div>

      <button
        type="button"
        onClick={onToggleSettings}
        aria-pressed={settingsOpen}
        title="AI model settings"
        className={`ml-auto flex h-8 w-8 items-center justify-center rounded-xl border transition-colors ${
          settingsOpen
            ? "border-accent/50 bg-accent/15 text-accent"
            : "border-border text-muted hover:border-accent/40 hover:text-accent"
        }`}
      >
        <Settings2 className="h-4 w-4" />
      </button>
    </div>
  );
}
