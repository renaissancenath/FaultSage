import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";

export function useApi<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  // biome-ignore lint/correctness/useExhaustiveDependencies: explicit deps list from callers
  useEffect(() => {
    if (!path) return;
    let live = true;
    setLoading(true);
    api<T>(path)
      .then((d) => {
        if (live) {
          setData(d);
          setError(null);
        }
      })
      .catch((e: unknown) => live && setError(e))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [path, tick, ...deps]);
  return { data, error, loading, reload, setData };
}
