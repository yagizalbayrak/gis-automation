import { useCallback, useEffect, useState } from "react";
import { getLlmSettings, saveLlmSettings, testLlmSettings } from "../lib/api";
import type { LlmSettingsResponse, LlmTestResponse, ProviderPreset } from "../lib/types";

export const CUSTOM_MODEL = "__custom__";

export function useLlmSettings() {
  const [providers, setProviders] = useState<Record<string, ProviderPreset>>({});
  const [provider, setProvider] = useState("gemini");
  const [model, setModel] = useState("");
  const [customModel, setCustomModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiBase, setApiBase] = useState("");
  const [keyPlaceholder, setKeyPlaceholder] = useState("paste your API key");
  const [configured, setConfigured] = useState(false);
  const [configuredModel, setConfiguredModel] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ ok: boolean; message: string } | null>(null);
  const [testing, setTesting] = useState(false);

  const applySettings = useCallback((settings: LlmSettingsResponse) => {
    setProviders(settings.providers);
    setConfigured(settings.configured);
    setConfiguredModel(settings.model);
    const nextProvider = settings.provider || "gemini";
    setProvider(nextProvider);

    const models = settings.providers[nextProvider]?.models || [];
    if (settings.model && models.includes(settings.model)) {
      setModel(settings.model);
    } else if (settings.model) {
      setModel(CUSTOM_MODEL);
      setCustomModel(settings.model);
    } else {
      setModel(models[0] || CUSTOM_MODEL);
    }
    if (settings.api_base) setApiBase(settings.api_base);
    if (settings.api_key_masked) {
      setKeyPlaceholder(`saved ${settings.api_key_masked} - paste to replace`);
    }
  }, []);

  useEffect(() => {
    getLlmSettings().then(applySettings).catch(() => {});
  }, [applySettings]);

  const modelsForProvider = providers[provider]?.models ?? [];
  const showApiBase = provider === "custom";
  const selectedModelId = model === CUSTOM_MODEL ? customModel.trim() : model;

  const changeProvider = useCallback(
    (nextProvider: string) => {
      setProvider(nextProvider);
      const models = providers[nextProvider]?.models ?? [];
      setModel(models[0] || CUSTOM_MODEL);
      const hint = providers[nextProvider]?.key_hint;
      if (hint) setKeyPlaceholder((current) => (current.startsWith("saved") ? current : hint));
    },
    [providers],
  );

  const save = useCallback(
    async (options: { silent?: boolean } = {}): Promise<boolean> => {
      const finalModel = selectedModelId;
      if (!finalModel) {
        setFeedback({ ok: false, message: "Choose or enter a model id first." });
        return false;
      }
      const settings = await saveLlmSettings({
        provider,
        model: finalModel,
        api_base: apiBase.trim() || null,
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
      });
      applySettings(settings);
      setApiKey("");
      if (!options.silent) {
        setFeedback({
          ok: true,
          message: `Saved: ${settings.model}${
            settings.api_key_masked ? " with API key" : " (no key yet)"
          }.`,
        });
      }
      return true;
    },
    [apiBase, apiKey, applySettings, provider, selectedModelId],
  );

  const test = useCallback(async () => {
    setTesting(true);
    try {
      // Whatever is currently in the form is what the user means to test -
      // save it first so Test never silently runs against a stale key.
      setFeedback({ ok: true, message: "Saving settings..." });
      const saved = await save({ silent: true });
      if (!saved) return;

      setFeedback({ ok: true, message: "Testing connection..." });
      const result: LlmTestResponse = await testLlmSettings();
      setFeedback({
        ok: result.ok,
        message: result.ok
          ? `${result.model} answered in ${result.latency_ms} ms. ${result.message}`
          : result.message,
      });
    } finally {
      setTesting(false);
    }
  }, [save]);

  return {
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
    configured,
    configuredModel,
    feedback,
    testing,
    save,
    test,
  };
}
