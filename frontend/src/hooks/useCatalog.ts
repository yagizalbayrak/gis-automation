import { useCallback, useState } from "react";
import { getCatalog } from "../lib/api";
import type { Catalog } from "../lib/types";

export function useCatalog() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);

  const ensureLoaded = useCallback(async () => {
    if (catalog) return catalog;
    const loaded = await getCatalog();
    setCatalog(loaded);
    return loaded;
  }, [catalog]);

  return { catalog, ensureLoaded };
}
