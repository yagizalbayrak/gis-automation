import { AnimatePresence, motion } from "motion/react";
import { CUSTOM_MODEL, type useLlmSettings } from "../hooks/useLlmSettings";

interface SettingsPanelProps {
  open: boolean;
  settings: ReturnType<typeof useLlmSettings>;
}

export function SettingsPanel({ open, settings }: SettingsPanelProps) {
  const {
    providers,
    provider,
    changeProvider,
    model,
    setModel,
    customModel,
    setCustomModel,
    modelsForProvider,
    showApiBase,
    apiBase,
    setApiBase,
    apiKey,
    setApiKey,
    keyPlaceholder,
    feedback,
    testing,
    save,
    test,
  } = settings;

  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
        >
          <div className="rounded-2xl border border-border bg-white/[0.02] p-4 backdrop-blur-xl">
            <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-muted">
              AI model connection
            </h2>
            <div className="grid grid-cols-[86px_1fr] items-center gap-x-3 gap-y-2.5">
              <label className="text-[12px] text-muted">Provider</label>
              <select
                value={provider}
                onChange={(e) => changeProvider(e.target.value)}
                className="rounded-lg border border-border bg-bg-elevated px-2.5 py-1.5 text-[13px] text-text focus:border-accent/50 focus:outline-none"
              >
                {Object.entries(providers).map(([id, meta]) => (
                  <option key={id} value={id}>
                    {meta.label}
                  </option>
                ))}
              </select>

              <label className="text-[12px] text-muted">Model</label>
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="rounded-lg border border-border bg-bg-elevated px-2.5 py-1.5 text-[13px] text-text focus:border-accent/50 focus:outline-none"
              >
                {modelsForProvider.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
                <option value={CUSTOM_MODEL}>custom model id...</option>
              </select>

              {model === CUSTOM_MODEL && (
                <>
                  <label className="text-[12px] text-muted">Model id</label>
                  <input
                    value={customModel}
                    onChange={(e) => setCustomModel(e.target.value)}
                    placeholder="any LiteLLM model id, e.g. gemini/gemini-2.5-flash"
                    className="rounded-lg border border-border bg-bg-elevated px-2.5 py-1.5 text-[13px] text-text placeholder:text-muted-2 focus:border-accent/50 focus:outline-none"
                  />
                </>
              )}

              <label className="text-[12px] text-muted">API key</label>
              <input
                type="password"
                autoComplete="off"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={keyPlaceholder}
                className="rounded-lg border border-border bg-bg-elevated px-2.5 py-1.5 text-[13px] text-text placeholder:text-muted-2 focus:border-accent/50 focus:outline-none"
              />

              {showApiBase && (
                <>
                  <label className="text-[12px] text-muted">API base URL</label>
                  <input
                    value={apiBase}
                    onChange={(e) => setApiBase(e.target.value)}
                    placeholder="optional custom endpoint"
                    className="rounded-lg border border-border bg-bg-elevated px-2.5 py-1.5 text-[13px] text-text placeholder:text-muted-2 focus:border-accent/50 focus:outline-none"
                  />
                </>
              )}
            </div>

            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={() => save()}
                className="rounded-lg bg-accent px-3.5 py-1.5 text-[12.5px] font-semibold text-bg transition hover:brightness-110 active:scale-[0.98]"
              >
                Save
              </button>
              <button
                type="button"
                onClick={() => test()}
                disabled={testing}
                className="rounded-lg border border-border px-3.5 py-1.5 text-[12.5px] font-semibold text-text transition hover:border-accent/40 hover:text-accent disabled:cursor-wait disabled:opacity-50"
              >
                Test connection
              </button>
            </div>

            {feedback && (
              <p
                className={`mt-2.5 text-[12px] leading-relaxed ${
                  feedback.ok ? "text-ok" : "text-fail"
                }`}
              >
                {feedback.message}
              </p>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
